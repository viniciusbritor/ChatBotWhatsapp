import os
import re
from typing import Any, Dict, List, Tuple

import httpx

from core.secrets import get_secret


class EvolutionDeliveryError(RuntimeError):
    pass


def _config() -> Tuple[str, str]:
    base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
    if not api_key:
        raise EvolutionDeliveryError("evolution_api_key_not_configured")
    return base_url, api_key


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


async def mark_messages_read(
    instance: str,
    remote_jid: str,
    message_ids: List[str],
    *,
    from_me: bool = False,
) -> Dict[str, Any]:
    """Mark inbound messages as read on Evolution.

    Evolution v2 expects the ``markMessagesAsRead`` endpoint with a
    ``readMessages`` array. Failures are logged and surfaced to the caller;
    the webhook does not block on them.
    """
    if not instance or not remote_jid or not message_ids:
        raise EvolutionDeliveryError("invalid_mark_read_request")
    base_url, api_key = _config()
    payload = {
        "readMessages": [
            {"id": message_id, "fromMe": from_me, "remoteJid": remote_jid}
            for message_id in message_ids
            if message_id
        ]
    }
    async with httpx.AsyncClient(timeout=_request_timeout(10)) as client:
        response = await client.post(
            f"{base_url}/chat/markMessagesAsRead/{instance}",
            json=payload,
            headers={"apikey": api_key, "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise EvolutionDeliveryError(f"evolution_mark_http_{response.status_code}")
    try:
        return response.json()
    except ValueError:
        return {"status": "accepted"}


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
