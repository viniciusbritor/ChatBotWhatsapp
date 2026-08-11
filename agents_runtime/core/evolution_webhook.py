"""Evolution API webhook payload extraction.

Parses the raw HTTP body posted by Evolution API and returns a normalized
envelope ready to be published to Pub/Sub.

Supported event:
- MESSAGES_UPSERT (lowercase `messages.upsert` also accepted)

Extracts:
- text from conversation, extendedTextMessage
- audio: has_audio, audio_mimetype, audio_ptt, audio_url
- pushName (sender display name)
- phone (digits before @)
- remote_jid (full)
- message_id (Evolution key.id)
- instance
- is_group (@g.us suffix)
- was_mentioned (grupo: @Jennifer no contextInfo.mentionedJid)

Filters out:
- fromMe echoes
- @broadcast lists
- empty phone/instance
- events other than messages.upsert
- mensagens de GRUPO sem @Jennifer quando o JID do bot e conhecido
  (mencao explicita); se mentionedJid vier vazio/ausente, processa
  normalmente (compatibilidade com clientes sem suporte a mencao).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EVOLUTION_BASE_URL = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br")

VALID_EVENTS = {"MESSAGES_UPSERT", "messages.upsert", "messages.update"}

_BOT_JID_CACHE: Dict[str, tuple] = {}
_BOT_JID_TTL_SEC = 300


class EvolutionWebhookError(Exception):
    """Raised when the webhook payload cannot be processed."""


def _resolve_bot_jid(instance: str) -> str:
    """Resolve o JID do bot (Jennifer) para a instancia.

    O numero do bot e o owner_phone da conta Evolution (whatsapp_accounts).
    Cache in-process de 300s para evitar round-trip Firestore por mensagem.
    Retorna "" se nao resolver (nesse caso, nenhum filtro de mencao e aplicado).
    """
    if not instance:
        return ""
    cached = _BOT_JID_CACHE.get(instance)
    if cached and cached[1] > time.time() - _BOT_JID_TTL_SEC:
        return cached[0]
    bot_jid = ""
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return ""
        db = firestore.Client(project=project)
        for doc in db.collection("whatsapp_accounts").stream():
            data = doc.to_dict() or {}
            if (data.get("instance") or "").lower() == str(instance).lower():
                owner = str(data.get("owner_phone") or "")
                digits = "".join(c for c in owner if c.isdigit())
                if digits:
                    bot_jid = f"{digits}@s.whatsapp.net"
                break
    except Exception as exc:
        logger.debug("resolve_bot_jid_failed instance=%s exc=%s", instance, exc)
    _BOT_JID_CACHE[instance] = (bot_jid, time.time())
    return bot_jid


def _extract_mentioned_jids(message: Dict[str, Any]) -> List[str]:
    """Extrai JIDs mencionados de uma mensagem (contextInfo.mentionedJid).

    Baileys/Evolution coloca a lista em:
    - message.extendedTextMessage.contextInfo.mentionedJid
    - message.conversation.contextInfo (raramente presente)
    - message.documentMessage.contextInfo (caption com @mention)
    """
    mentioned: List[str] = []
    for node_name in ("extendedTextMessage", "conversation", "documentMessage", "audioMessage"):
        node = message.get(node_name)
        if isinstance(node, dict):
            ctx = node.get("contextInfo")
            if isinstance(ctx, dict):
                jids = ctx.get("mentionedJid")
                if isinstance(jids, list):
                    mentioned.extend(str(j) for j in jids if isinstance(j, str))
    return mentioned


def extract_envelope(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return normalized envelope or None when the payload should be ignored.

    Returns None for: non-message events, fromMe echoes, broadcast lists,
    missing phone/instance, unsupported message types (image, video, sticker,
    document, contact, location without text).
    """
    if not isinstance(payload, dict):
        return None

    event = payload.get("event") or payload.get("type") or ""
    if event not in VALID_EVENTS:
        return None

    instance = payload.get("instance") or ""
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return None

    message = data.get("message") or {}
    key = data.get("key") or {}

    if key.get("fromMe"):
        return None

    remote_jid = str(key.get("remoteJid") or message.get("from") or "")
    if not remote_jid:
        return None

    if "@broadcast" in remote_jid:
        return None

    is_group = "@g.us" in remote_jid
    participant_jid = str(key.get("participant") or message.get("participant") or "")

    # Em GRUPO, o phone vem do participant (user individual). Em PRIVADO,
    # do remoteJid. Fallback para remoteJid se participant ausente.
    if is_group and participant_jid and "@" in participant_jid:
        phone = participant_jid.split("@", 1)[0]
        phone_source = "participant"
    else:
        phone = remote_jid.split("@", 1)[0]
        phone_source = "remote_jid"
    if not phone or not phone[0].isdigit():
        return None

    message_id = str(key.get("id") or message.get("id") or "")
    sender_name = str(data.get("pushName") or "")

    text = ""
    extra: Dict[str, Any] = {
        "is_group": is_group,
        "raw_message_type": str(data.get("messageType") or ""),
        "phone_source": phone_source,
    }

    if "conversation" in message and isinstance(message["conversation"], str):
        text = message["conversation"]
    elif "extendedTextMessage" in message and isinstance(message["extendedTextMessage"], dict):
        text = str(message["extendedTextMessage"].get("text") or "")
    elif "audioMessage" in message and isinstance(message["audioMessage"], dict):
        audio_msg = message["audioMessage"]
        extra["has_audio"] = True
        extra["audio_mimetype"] = str(audio_msg.get("mimetype") or "audio/ogg")
        extra["audio_ptt"] = bool(audio_msg.get("ptt", False))
        if message_id:
            extra["audio_url"] = (
                f"{EVOLUTION_BASE_URL.rstrip('/')}/chat/getMedia/{instance}"
                f"?messageId={message_id}"
            )
        text = "[audio]"
    elif "documentMessage" in message and isinstance(message["documentMessage"], dict):
        doc_msg = message["documentMessage"]
        extra["has_document"] = True
        extra["doc_mimetype"] = str(doc_msg.get("mimetype") or "application/octet-stream")
        extra["doc_file_name"] = str(doc_msg.get("fileName") or "document")
        # Evolution v2.3.7 pode enviar fileLength como dict (proto Long
        # do WhatsApp Baileys: {low: N, high: M, unsigned: bool}) ou como
        # int/str. Normalizar para int.
        raw_length = doc_msg.get("fileLength")
        if isinstance(raw_length, dict):
            # proto Long: low + high * 2**32
            raw_length = raw_length.get("low", 0) + raw_length.get("high", 0) * (2 ** 32)
        elif raw_length is None:
            raw_length = 0
        try:
            extra["doc_file_length"] = int(raw_length)
        except (TypeError, ValueError):
            extra["doc_file_length"] = 0
        extra["doc_caption"] = str(doc_msg.get("caption") or "")
        extra["doc_url"] = str(doc_msg.get("url") or "")
        extra["doc_direct_path"] = str(doc_msg.get("directPath") or "")
        if doc_msg.get("base64"):
            try:
                extra["doc_base64"] = str(doc_msg["base64"])
            except Exception:
                pass
        text = (doc_msg.get("caption") or doc_msg.get("fileName") or "").strip()
    elif "imageMessage" in message or "videoMessage" in message:
        return None
    else:
        return None

    if not instance:
        return None

    # ========================
    # FILTRO DE MENCAO EM GRUPO (11/08/2026 — agressivo)
    # Jennifer so responde em grupo quando @mencionada explicitamente.
    # Se mentionedJid vier vazio OU nao contiver o bot, a mensagem e
    # IGNORADA. Conversa 1:1 nao e afetada.
    # ========================
    was_mentioned = False
    if is_group:
        bot_jid = _resolve_bot_jid(instance)
        mentioned_jids = _extract_mentioned_jids(message)
        was_mentioned = bool(bot_jid) and bot_jid in mentioned_jids
        if not was_mentioned:
            logger.info(
                "webhook_group_mention_skipped instance=%s group=%s phone=%s mentioned=%s bot_jid=%s",
                instance, remote_jid.split("@", 1)[0], phone, mentioned_jids[:5], bot_jid,
            )
            return None
    extra["was_mentioned"] = was_mentioned

    from core.message_ledger import deterministic_request_id

    request_id = message_id or deterministic_request_id(
        instance, remote_jid, str(data.get("messageTimestamp") or "")
    )
    return {
        "request_id": request_id,
        "instance": instance,
        "phone": phone,
        "remote_jid": remote_jid,
        "message_id": message_id or request_id,
        "sender_name": sender_name or "user",
        "text": text,
        "extra": extra,
    }


def extract_message_id(payload: Dict[str, Any]) -> Optional[str]:
    """Extract just the message id (used for idempotency checks)."""
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return None
    key = data.get("key") or {}
    message = data.get("message") or {}
    return str(key.get("id") or message.get("id") or "") or None
