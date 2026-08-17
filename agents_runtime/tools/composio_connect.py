"""Composio Platform connection manager — Connect Links + status."""
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
COMPOSIO_BASE = "https://backend.composio.dev/api/v3.1"

# GUARDRAIL §0.7 (16/08/2026): cache em memoria com TTL 120s por user_id para
# evitar chamada repetida a /connected_accounts a cada render do Portal
# (anteriormente era chamado em cada polling). Reduz custo API Composio ~85%
# durante navegacao normal.
_CACHE_TTL_SEC = 120
_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}  # user_id -> {"ts": float, "data": {...}}


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
    # Cache hit (TTL 120s) - evita bater no Composio a cada polling do Portal.
    cached = _STATUS_CACHE.get(user_id)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL_SEC:
        return cached["data"]
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
    result = {"phone": user_id, "apps": apps, "total": len(apps)}
    _STATUS_CACHE[user_id] = {"ts": time.time(), "data": result}
    return result


def invalidate_status_cache(user_id: Optional[str] = None) -> int:
    """Limpa cache de status. Se user_id=None, limpa tudo."""
    if user_id is None:
        n = len(_STATUS_CACHE)
        _STATUS_CACHE.clear()
        return n
    _STATUS_CACHE.pop(user_id, None)
    return 1


async def connect_all(user_id: str, toolkit: str = "") -> Dict[str, Any]:
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
        if toolkit and slug != toolkit:
            continue
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
