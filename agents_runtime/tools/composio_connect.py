"""Composio Platform connection manager — Connect Links + status."""
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
COMPOSIO_BASE = "https://backend.composio.dev/api/v3.1"


def _get_api_key() -> str:
    global _CACHED_KEY
    if _CACHED_KEY:
        return _CACHED_KEY
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{_PROJECT}/secrets/COMPOSIO_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        _CACHED_KEY = response.payload.data.decode("utf-8-sig").strip()
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Composio key load failed: %s", exc)
        return ""


def _client():
    from composio import Composio
    return Composio(api_key=_get_api_key())


async def get_status(user_id: str) -> Dict[str, Any]:
    c = _client()
    try:
        configs = c.auth_configs.list()
        accts = c.connected_accounts.list(user_ids=[user_id])
    except Exception as exc:
        return {"error": str(exc)[:200], "apps": {}}
    connected_slugs = {a.toolkit.slug: getattr(a, "id", str(a)) for a in accts.items}
    apps = {}
    for cfg in configs.items:
        slug = cfg.toolkit.slug
        apps[slug] = {
            "toolkit": slug,
            "name": cfg.name,
            "auth_config_id": getattr(cfg, "id", ""),
            "connected": slug in connected_slugs,
        }
    return {"phone": user_id, "apps": apps, "total": len(apps)}


async def connect_all(user_id: str) -> Dict[str, Any]:
    c = _client()
    session = c.create(user_id=user_id)
    try:
        accts = c.connected_accounts.list(user_ids=[user_id])
    except Exception:
        accts = type("_", (), {"items": []})()
    connected_slugs = {a.toolkit.slug for a in accts.items}
    configs = c.auth_configs.list()
    links = []
    already = 0
    for cfg in configs.items:
        slug = cfg.toolkit.slug
        if slug in connected_slugs:
            already += 1
            links.append({"toolkit": slug, "status": "connected", "connect_url": None})
        else:
            try:
                req = session.authorize(toolkit=slug)
                links.append({
                    "toolkit": slug,
                    "status": "pending",
                    "connect_url": req.redirect_url if hasattr(req, "redirect_url") else None,
                    "auth_config_id": getattr(cfg, "id", ""),
                })
            except Exception as exc:
                links.append({"toolkit": slug, "status": "error", "error": str(exc)[:100]})
    return {
        "phone": user_id,
        "links": links,
        "already_connected": already,
        "pending_connection": len(links) - already,
        "total": len(links),
    }


async def authorize_owner(user_id: str) -> Dict[str, Any]:
    return await connect_all(user_id)
