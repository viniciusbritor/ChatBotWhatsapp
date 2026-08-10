"""Evolution API admin client — instancias, QR code, webhook.

Endpoints de gestao da Evolution API (server manager):
- POST /instance/create — criar instancia WhatsApp
- GET  /instance/connect/{name} — obter QR code (base64)
- GET  /instance/connectionState/{name} — estado da conexao
- POST /webhook/set/{name} — configurar webhook
- GET  /instance/fetchInstances — listar instancias
- DELETE /instance/{name} — remover instancia
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)


def _config() -> tuple[str, str]:
    base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY") or ""
    return base_url, api_key


def _headers(api_key: str) -> Dict[str, str]:
    return {"apikey": api_key, "Content-Type": "application/json"}


async def fetch_instances() -> List[Dict[str, Any]]:
    """Lista todas as instancias da Evolution API."""
    base_url, api_key = _config()
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{base_url}/instance/fetchInstances",
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            logger.warning("evolution_admin_fetch_instances http=%s", response.status_code)
            return []
        payload = response.json() or []
        return payload if isinstance(payload, list) else []
    except Exception as exc:
        logger.warning("evolution_admin_fetch_instances error=%s", exc)
        return []


async def get_connection_state(instance: str) -> Dict[str, Any]:
    """Retorna o estado de conexao de uma instancia: {'instance': ..., 'state': 'open'|'connecting'|'close'}."""
    base_url, api_key = _config()
    if not api_key or not instance:
        return {"instance": instance, "state": "unknown"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{base_url}/instance/connectionState/{instance}",
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            return {"instance": instance, "state": "unknown", "http": response.status_code}
        data = response.json() or {}
        return {
            "instance": instance,
            "state": data.get("instance", {}).get("state") if isinstance(data.get("instance"), dict) else data.get("state", "unknown"),
            "raw": data,
        }
    except Exception as exc:
        logger.warning("evolution_admin_connection_state error=%s", exc)
        return {"instance": instance, "state": "unknown", "error": str(exc)[:120]}


async def create_instance(
    instance_name: str,
    webhook_url: str = "",
    *,
    qrcode: bool = True,
    reject_call: bool = True,
    msg_call: str = "Desculpe, nao atendo ligacoes. Envie uma mensagem!",
) -> Dict[str, Any]:
    """Cria uma instancia WhatsApp na Evolution API espelhando a config da Jennifer.

    Schema real do POST /instance/create (v2.x):
    {"instanceName": str, "integration": "WHATSAPP-BAILEYS", "qrcode": bool, ...}
    Webhook NAO vai no create — configurar via set_webhook() depois.
    """
    base_url, api_key = _config()
    if not api_key:
        return {"error": "evolution_api_key_not_configured"}
    if not instance_name:
        return {"error": "instance_name_required"}

    payload: Dict[str, Any] = {
        "instanceName": instance_name,
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": qrcode,
        "reject_call": reject_call,
        "msg_call": msg_call,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{base_url}/instance/create",
                json=payload,
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            logger.warning("evolution_admin_create_instance http=%s body=%s", response.status_code, response.text[:300])
            return {"error": f"evolution_create_failed http={response.status_code}", "detail": response.text[:300]}
        data = response.json() or {}
        result: Dict[str, Any] = {"created": True, "instance": instance_name, "data": data}
        if webhook_url:
            hook = await set_webhook(instance_name, webhook_url)
            result["webhook"] = hook
        return result
    except Exception as exc:
        logger.warning("evolution_admin_create_instance error=%s", exc)
        return {"error": str(exc)[:200]}


async def get_qr_code(instance: str) -> Dict[str, Any]:
    """Gera o QR code de conexao para a instancia. Retorna base64 do PNG."""
    base_url, api_key = _config()
    if not api_key or not instance:
        return {"error": "missing_instance_or_key"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base_url}/instance/connect/{instance}",
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            return {"error": f"evolution_qr_failed http={response.status_code}", "detail": response.text[:300]}
        data = response.json() or {}
        return {"instance": instance, "qr_base64": data.get("base64", ""), "code": data.get("code", ""), "data": data}
    except Exception as exc:
        logger.warning("evolution_admin_get_qr error=%s", exc)
        return {"error": str(exc)[:200]}


async def set_webhook(instance: str, webhook_url: str) -> Dict[str, Any]:
    """Configura o webhook de uma instancia (schema v2.x: {webhook: {url, enabled, events}})."""
    base_url, api_key = _config()
    if not api_key or not instance or not webhook_url:
        return {"error": "instance_e_webhook_obrigatorios"}
    try:
        payload = {
            "webhook": {
                "url": webhook_url,
                "enabled": True,
                "events": ["MESSAGES_UPSERT"],
            }
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{base_url}/webhook/set/{instance}",
                json=payload,
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            return {"error": f"evolution_webhook_failed http={response.status_code}", "detail": response.text[:300]}
        return {"set": True, "instance": instance, "webhook_url": webhook_url}
    except Exception as exc:
        logger.warning("evolution_admin_set_webhook error=%s", exc)
        return {"error": str(exc)[:200]}


async def delete_instance(instance: str) -> Dict[str, Any]:
    """Remove uma instancia WhatsApp da Evolution API (endpoint v2.x: DELETE /instance/delete/{name})."""
    base_url, api_key = _config()
    if not api_key or not instance:
        return {"error": "instance_e_key_obrigatorios"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.delete(
                f"{base_url}/instance/delete/{instance}",
                headers=_headers(api_key),
            )
        if response.status_code >= 400:
            return {"error": f"evolution_delete_failed http={response.status_code}", "detail": response.text[:300]}
        return {"deleted": True, "instance": instance}
    except Exception as exc:
        logger.warning("evolution_admin_delete_instance error=%s", exc)
        return {"error": str(exc)[:200]}
