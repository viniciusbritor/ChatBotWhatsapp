import os
import re
from typing import Any, Dict

import httpx

from core.secrets import get_secret


class EvolutionDeliveryError(RuntimeError):
    pass


def _config() -> tuple[str, str]:
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
    async with httpx.AsyncClient(timeout=30) as client:
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
