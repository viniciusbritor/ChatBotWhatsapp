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

Filters out:
- fromMe echoes
- @broadcast lists
- empty phone/instance
- events other than messages.upsert
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

EVOLUTION_BASE_URL = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br")

VALID_EVENTS = {"MESSAGES_UPSERT", "messages.upsert", "messages.update"}


class EvolutionWebhookError(Exception):
    """Raised when the webhook payload cannot be processed."""


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

    phone = remote_jid.split("@", 1)[0]
    if not phone or not phone[0].isdigit():
        return None

    message_id = str(key.get("id") or message.get("id") or "")
    sender_name = str(data.get("pushName") or "")

    is_group = "@g.us" in remote_jid

    text = ""
    extra: Dict[str, Any] = {
        "is_group": is_group,
        "raw_message_type": str(data.get("messageType") or ""),
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
        extra["doc_file_length"] = int(doc_msg.get("fileLength") or 0)
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
