import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Tuple

import httpx

from core.secrets import get_secret


logger = logging.getLogger(__name__)


class EvolutionDeliveryError(RuntimeError):
    pass


def _config() -> Tuple[str, str]:
    base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
    if not api_key:
        raise EvolutionDeliveryError("evolution_api_key_not_configured")
    logger.debug(
        "evolution_client base_url=%s token_prefix=%s token_len=%d",
        base_url,
        api_key[:4],
        len(api_key),
    )
    return base_url, api_key


def _resolve_instance_name() -> str:
    """Resolve the Evolution instance name case-sensitively.

    The runtime is configured with ``INSTANCE=jennifer`` but the actual
    instance on the Evolution server is ``Jennifer``. The Evolution API
    rejects case mismatches with 404. We fetch the instance list once
    and return the canonical casing.
    """
    desired = (os.getenv("INSTANCE") or "jennifer").strip()
    if not desired:
        return desired
    try:
        api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
        if not api_key:
            return desired
        base_url, _ = _config()
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{base_url}/instance/fetchInstances",
                headers={"apikey": api_key},
            )
            if response.status_code >= 400:
                return desired
            payload = response.json() or []
        for entry in payload:
            name = (entry.get("name") or "").strip()
            if name.lower() == desired.lower():
                if name != desired:
                    logger.info(
                        "evolution_instance_case_corrected desired=%s actual=%s",
                        desired,
                        name,
                    )
                return name
    except Exception as exc:  # noqa: BLE001
        logger.warning("evolution_instance_resolve_failed error=%s", exc)
    return desired


def _target(phone: str, remote_jid: str = "") -> str:
    if remote_jid.endswith("@g.us"):
        return remote_jid
    normalized = re.sub(r"\D", "", phone)
    if not normalized:
        raise EvolutionDeliveryError("invalid_destination")
    return normalized


def _request_timeout(default: float = 30.0) -> httpx.Timeout:
    try:
        return httpx.Timeout(float(os.getenv("EVO_HTTP_TIMEOUT", str(default))))
    except ValueError:
        return httpx.Timeout(default)


async def send_text(
    instance: str,
    phone: str,
    text: str,
    delay_ms: int = 0,
    presence: str = "composing",
    remote_jid: str = "",
) -> Dict[str, Any]:
    if not instance or not text:
        raise EvolutionDeliveryError("invalid_message")
    base_url, api_key = _config()
    instance = _resolve_instance_name() if instance.lower() == (os.getenv("INSTANCE") or "jennifer").lower() else instance
    logger.debug("evolution_send_text instance=%s phone=%s", instance, phone)
    async with httpx.AsyncClient(timeout=_request_timeout(30)) as client:
        response = await client.post(
            f"{base_url}/message/sendText/{instance}",
            json={
                "number": _target(phone, remote_jid),
                "text": text,
                "delay": max(0, min(int(delay_ms), 15000)),
                "presence": presence,
            },
            headers={"apikey": api_key, "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise EvolutionDeliveryError(f"evolution_http_{response.status_code}")
    try:
        return response.json()
    except ValueError:
        return {"status": "accepted"}


async def send_presence(
    instance: str,
    phone: str,
    presence: str = "composing",
    *,
    remote_jid: str = "",
) -> Dict[str, Any]:
    """Send a presence update (composing/paused) via Evolution API."""
    base_url, api_key = _config()
    instance = _resolve_instance_name() if instance.lower() == (os.getenv("INSTANCE") or "jennifer").lower() else instance
    try:
        async with httpx.AsyncClient(timeout=_request_timeout(5)) as client:
            response = await client.post(
                f"{base_url}/chat/sendPresence/{instance}",
                json={
                    "number": _target(phone, remote_jid),
                    "presence": presence,
                },
                headers={"apikey": api_key, "Content-Type": "application/json"},
            )
        if response.status_code < 400:
            return {"status": "ok", "presence": presence}
        return {"status": "error", "http": response.status_code}
    except Exception as exc:
        logger.warning("send_presence_failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


async def send_image(
    instance: str,
    phone: str,
    image_bytes: bytes,
    *,
    filename: str = "report.png",
    caption: str = "",
    mime_type: str = "image/png",
    delay_ms: int = 0,
    presence: str = "composing",
    remote_jid: str = "",
) -> Dict[str, Any]:
    """Send an image attachment to WhatsApp via Evolution API.

    Uses multipart/form-data on POST /message/sendImage/{instance}.
    The image preview is shown inline by WhatsApp clients; the bot
    can pair this with ``send_text`` for a caption, or pass an
    explicit ``caption`` to inline a short description.

    Args:
        instance: WhatsApp instance name (e.g. ``Jennifer``).
        phone: E.164 phone number of the recipient (without +).
        image_bytes: PNG/JPEG bytes to attach.
        filename: filename shown in the WhatsApp media message.
        caption: short text rendered under the image (optional).
        mime_type: ``image/png`` (default) or ``image/jpeg``.
        delay_ms: presence delay (typing indicator duration).
        presence: presence hint (``composing``/``paused``).
        remote_jid: explicit remote JID; otherwise ``_target`` builds it.

    Returns:
        API response dict, or ``{"status": "accepted"}`` on success
        when the response body is empty.
    """
    if not instance or not image_bytes:
        raise EvolutionDeliveryError("invalid_message")
    base_url, api_key = _config()
    instance = _resolve_instance_name() if instance.lower() == (os.getenv("INSTANCE") or "jennifer").lower() else instance
    logger.debug("evolution_send_image instance=%s phone=%s bytes=%d", instance, phone, len(image_bytes))
    files = {
        "file": (filename, image_bytes, mime_type),
    }
    data = {
        "number": _target(phone, remote_jid),
        "delay": max(0, min(int(delay_ms), 15000)),
        "presence": presence,
    }
    if caption:
        data["caption"] = caption[:1024]
    async with httpx.AsyncClient(timeout=_request_timeout(30)) as client:
        response = await client.post(
            f"{base_url}/message/sendImage/{instance}",
            data=data,
            files=files,
            headers={"apikey": api_key},
        )
    if response.status_code >= 400:
        raise EvolutionDeliveryError(
            f"evolution_http_{response.status_code}: {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError:
        return {"status": "accepted"}


async def mark_messages_read(
    instance: str,
    remote_jid: str,
    message_ids: List[str],
    *,
    from_me: bool = False,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Mark inbound messages as read on Evolution.

    Retries up to max_retries with exponential backoff (1s, 2s, 4s).
    """
    if not instance or not remote_jid or not message_ids:
        raise EvolutionDeliveryError("invalid_mark_read_request")
    base_url, api_key = _config()
    instance = _resolve_instance_name() if instance.lower() == (os.getenv("INSTANCE") or "jennifer").lower() else instance
    payload = {
        "readMessages": [
            {"id": message_id, "fromMe": from_me, "remoteJid": remote_jid}
            for message_id in message_ids
            if message_id
        ]
    }
    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=_request_timeout(10)) as client:
                response = await client.post(
                    f"{base_url}/chat/markMessageAsRead/{instance}",
                    json=payload,
                    headers={"apikey": api_key, "Content-Type": "application/json"},
                )
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError:
                    return {"status": "accepted"}
            last_error = f"http_{response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < max_retries - 1:
            await asyncio.sleep(1 * (2 ** attempt))
    raise EvolutionDeliveryError(f"evolution_mark_read_failed after {max_retries} retries: {last_error}")


async def fetch_instance_phones(instance: str) -> List[str]:
    """Return the WhatsApp numbers currently connected to the instance."""
    if not instance:
        return []
    base_url, api_key = _config()
    async with httpx.AsyncClient(timeout=_request_timeout(10)) as client:
        response = await client.get(
            f"{base_url}/instance/connectionState/{instance}",
            headers={"apikey": api_key},
        )
    if response.status_code >= 400:
        return []
    try:
        body = response.json()
    except ValueError:
        return []
    instance_block = body.get("instance") or {}
    owner_jid = instance_block.get("ownerJid") or instance_block.get("wid") or ""
    if not owner_jid:
        return []
    digits = re.sub(r"\D", "", owner_jid.split("@", 1)[0])
    return [digits] if digits else []


async def get_base64_from_media_message(
    instance: str,
    message_id: str,
    remote_jid: str = "",
) -> Dict[str, Any]:
    """Fetch media (audio, image, document) as base64 via Evolution API v2.3.7.

    Endpoint: POST /chat/getBase64FromMediaMessage/{instance}
    Body: {message: {key: {id, remoteJid}}}
    Returns: {base64, mimetype, fileName, mediaType, ...}
    """
    if not instance or not message_id:
        raise EvolutionDeliveryError("invalid_get_base64_request")
    base_url, api_key = _config()
    instance = _resolve_instance_name() if instance.lower() == (os.getenv("INSTANCE") or "jennifer").lower() else instance
    payload = {
        "message": {
            "key": {
                "id": message_id,
                "remoteJid": remote_jid,
            }
        },
        "convertToMp4": False,
    }
    async with httpx.AsyncClient(timeout=_request_timeout(60)) as client:
        response = await client.post(
            f"{base_url}/chat/getBase64FromMediaMessage/{instance}",
            json=payload,
            headers={"apikey": api_key, "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise EvolutionDeliveryError(
            f"evolution_get_base64_http_{response.status_code}"
        )
    try:
        return response.json()
    except ValueError:
        return {"status": "accepted"}


async def instance_supports_v2(instance: str) -> bool:
    """Probe Evolution to detect whether the v2 endpoints are available."""
    if not instance:
        return False
    base_url, api_key = _config()
    async with httpx.AsyncClient(timeout=_request_timeout(5)) as client:
        try:
            response = await client.get(
                f"{base_url}/instance/fetchInstances",
                headers={"apikey": api_key},
            )
        except Exception:  # noqa: BLE001
            return False
    if response.status_code >= 400:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("name") == instance:
                return True
    if isinstance(data, dict):
        return instance in data
    return False
