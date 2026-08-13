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

from core.secrets import get_secret  # noqa: E402

VALID_EVENTS = {"MESSAGES_UPSERT", "messages.upsert", "messages.update"}

_BOT_JID_CACHE: Dict[str, tuple] = {}
_BOT_JID_TTL_SEC = 300


class EvolutionWebhookError(Exception):
    """Raised when the webhook payload cannot be processed."""


def _resolve_bot_jid(instance: str) -> str:
    """Resolve o JID (phone-number form) do bot para a instancia.

    Fonte primaria: Evolution API ``/instance/fetchInstances`` -> campo
    ``ownerJid`` (ex: ``5511917389901@s.whatsapp.net``). O ``owner_phone``
    do Firestore e o telefone do OWNER (quem controla o bot), que nao e
    necessariamente o numero do bot. Fonte secundaria (fallback): Firestore.

    Cache in-process de 300s para evitar round-trip por mensagem.
    Retorna "" se nao resolver (nesse caso, nenhum filtro de mencao e aplicado).
    """
    if not instance:
        return ""
    cached = _BOT_JID_CACHE.get(instance)
    if cached and cached[1] > time.time() - _BOT_JID_TTL_SEC:
        return cached[0]
    bot_jid = ""
    try:
        bot_jid = _fetch_owner_jid_from_evolution(instance)
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolve_bot_jid_evolution_failed instance=%s exc=%s", instance, exc)
    if not bot_jid:
        bot_jid = _fetch_owner_jid_from_firestore(instance)
    _BOT_JID_CACHE[instance] = (bot_jid, time.time())
    return bot_jid


def _fetch_owner_jid_from_evolution(instance: str) -> str:
    """Consulta a Evolution API para descobrir o ownerJid do bot (PN form)."""
    import httpx

    base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
    if not api_key:
        return ""
    response = httpx.get(
        f"{base_url}/instance/fetchInstances",
        headers={"apikey": api_key},
        timeout=5.0,
    )
    if response.status_code >= 400:
        return ""
    payload = response.json() or []
    for entry in payload if isinstance(payload, list) else []:
        name = (entry.get("name") or "").strip()
        if name.lower() == str(instance).lower():
            owner_jid = str(entry.get("ownerJid") or "")
            if owner_jid and "@" in owner_jid:
                logger.info(
                    "resolve_bot_jid_from_evolution instance=%s ownerJid=%s",
                    instance, owner_jid,
                )
                return owner_jid
    return ""


def _fetch_owner_jid_from_firestore(instance: str) -> str:
    """Fallback legado: owner_phone do whatsapp_accounts como JID do bot."""
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
                return f"{digits}@s.whatsapp.net"
    return ""


def _resolve_bot_lid(instance: str, remote_jid: str) -> str:
    """Resolve o LID do bot dentro de um grupo (Evolution findGroupInfos).

    O WhatsApp migrou para LID (Linked ID): as mencoes chegam como
    ``75793925419076@lid`` em vez do phone-number. O grupo conhece o
    mapeamento LID <-> phoneNumber nos participantes. Este metodo encontra
    o participante cujo phoneNumber bate com o ownerJid do bot e devolve
    o seu ``id`` (LID form). Cache in-process de 300s por (instance, group).

    Retorna "" quando nao resolver (fallback = filtro legado por PN).
    """
    if not instance or not remote_jid:
        return ""
    cache_key = f"{instance.lower()}|{remote_jid}"
    cached = _BOT_JID_CACHE.get(cache_key)
    if cached and cached[1] > time.time() - _BOT_JID_TTL_SEC:
        return cached[0]
    bot_lid = ""
    try:
        bot_jid = _resolve_bot_jid(instance)
        if not bot_jid:
            return ""
        import httpx

        base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
        api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
        if not api_key:
            return ""
        response = httpx.get(
            f"{base_url}/group/findGroupInfos/{instance}?groupJid={remote_jid}",
            headers={"apikey": api_key},
            timeout=5.0,
        )
        if response.status_code >= 400:
            return ""
        info = response.json() or {}
        participants = info.get("participants") or []
        bot_digits = "".join(c for c in bot_jid.split("@", 1)[0] if c.isdigit())
        for participant in participants:
            pn = str(participant.get("phoneNumber") or "")
            pn_digits = "".join(c for c in pn if c.isdigit())
            if pn_digits and pn_digits == bot_digits:
                lid = str(participant.get("id") or "")
                if lid:
                    bot_lid = lid
                    break
        if bot_lid:
            logger.info(
                "resolve_bot_lid instance=%s group=%s bot_jid=%s bot_lid=%s",
                instance, remote_jid.split("@", 1)[0], bot_jid, bot_lid,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolve_bot_lid_failed instance=%s group=%s exc=%s", instance, remote_jid, exc)
    _BOT_JID_CACHE[cache_key] = (bot_lid, time.time())
    return bot_lid


def _jids_digit_set(jids: List[str]) -> set:
    """Normaliza JIDs para digits puros (agnostico a @s.whatsapp.net/@lid)."""
    out = set()
    for jid in jids:
        digits = "".join(c for c in str(jid) if c.isdigit())
        if digits:
            out.add(digits)
    return out


def _extract_mentioned_jids(message: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> List[str]:
    """Extrai JIDs mencionados de uma mensagem (contextInfo.mentionedJid).

    Baileys/Evolution coloca a lista em:
    - message.extendedTextMessage.contextInfo.mentionedJid
    - message.conversation.contextInfo (raramente presente)
    - message.documentMessage.contextInfo (caption com @mention)
    - message.contextInfo (nivel raiz do message — formato alternativo)
    - data.contextInfo (LID mode: contextInfo fica FORA do message, no data)
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
    ctx = message.get("contextInfo")
    if isinstance(ctx, dict):
        jids = ctx.get("mentionedJid")
        if isinstance(jids, list):
            mentioned.extend(str(j) for j in jids if isinstance(j, str))
    if isinstance(data, dict):
        ctx = data.get("contextInfo")
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
    # LID mode: key.participant vem como "82927262154987@lid" (Linked ID).
    # O phone-number real do remetente fica em key.participantAlt
    # ("5511966830020@s.whatsapp.net"). Preferir participantAlt para que o
    # owner_phone/owner_hash e as facts do user continuem resolvendo.
    participant_alt = str(key.get("participantAlt") or "")

    # Em GRUPO, o phone vem do participant (user individual). Em PRIVADO,
    # do remoteJid. Fallback para remoteJid se participant ausente.
    if is_group and participant_alt and "@" in participant_alt and participant_alt.split("@", 1)[0][0].isdigit():
        phone = participant_alt.split("@", 1)[0]
        phone_source = "participant_alt"
    elif is_group and participant_jid and "@" in participant_jid:
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
        "remote_jid": remote_jid,
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
            extra["audio_message_id"] = message_id
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
    # FILTRO DE MENCAO EM GRUPO (11/08/2026 — agressivo, LID-aware)
    # Jennifer so responde em grupo quando @mencionada explicitamente.
    # O WhatsApp migrou para LID (Linked ID): mentionedJid chega como
    # "75793925419076@lid" enquanto o ownerJid do bot e um phone-number
    # ("5511917389901@s.whatsapp.net"). O match compara por DIGITS puros
    # e tambem resolve o LID do bot no grupo via findGroupInfos.
    # Se mentionedJid vier vazio OU nao conter o bot, a mensagem e
    # IGNORADA. Conversa 1:1 nao e afetada.
    # ========================
    was_mentioned = False
    if is_group:
        bot_jid = _resolve_bot_jid(instance)
        mentioned_jids = _extract_mentioned_jids(message, data)
        was_mentioned = False
        if bot_jid:
            bot_digits = "".join(c for c in bot_jid.split("@", 1)[0] if c.isdigit())
            mentioned_digits = _jids_digit_set(mentioned_jids)
            if bot_digits and bot_digits in mentioned_digits:
                was_mentioned = True
            else:
                bot_lid = _resolve_bot_lid(instance, remote_jid)
                if bot_lid:
                    lid_digits = "".join(c for c in bot_lid.split("@", 1)[0] if c.isdigit())
                    if lid_digits and lid_digits in mentioned_digits:
                        was_mentioned = True
        if not was_mentioned:
            logger.info(
                "webhook_group_mention_skipped instance=%s group=%s phone=%s mentioned=%s bot_jid=%s",
                instance, remote_jid.split("@", 1)[0], phone, mentioned_jids[:5], bot_jid,
            )
            logger.info(
                "webhook_group_raw_payload instance=%s group=%s data_keys=%s message_keys=%s message_preview=%s",
                instance, remote_jid.split("@", 1)[0],
                list(data.keys()) if isinstance(data, dict) else "NOT_DICT",
                list(message.keys()) if isinstance(message, dict) else "NOT_DICT",
                str(message)[:1000],
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
