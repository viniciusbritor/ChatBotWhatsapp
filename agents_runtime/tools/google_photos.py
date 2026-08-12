"""Google Photos Library API tools - 2 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.

ATENCAO: o scope photoslibrary.readonly e RESTRITO pelo Google — em
producao exige verificacao de marca. Em test funciona sem.
"""
import base64
import functools
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
_PHOTOS_API = "https://photoslibrary.googleapis.com/v1"
_photos_services: Dict[str, Any] = {}


def _get_access_token(phone: str) -> str:
    if not phone:
        logger.error("photos_oauth_missing phone=empty")
        raise RuntimeError("phone_required_for_photos_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        logger.error("photos_oauth_missing phone=%s", phone)
        raise RuntimeError("user_google_oauth_required")
    token = getattr(creds, "token", None)
    if not token:
        creds.refresh(httpx.Client())
        token = creds.token
    return token


def _owner_guard(capability: str):
    """Allow only the owner phone to invoke Photos capabilities."""
    from core.owner import deny_if_not_owner, resolve_owner
    from core.owner_guard import check_folder_permission, post_filter_tool_result

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            phone = kwargs.get("phone")
            if not phone and args:
                phone = args[0]
            phone = str(phone or "")
            instance = str(kwargs.get("instance", "") or kwargs.get("_instance", ""))
            resolution = resolve_owner(instance, fallback_phone=phone)
            denial = deny_if_not_owner(resolution, phone, capability)
            if denial is not None:
                return denial
            fp_denial = check_folder_permission(phone, capability, kwargs)
            if fp_denial is not None:
                return fp_denial
            result = await func(*args, **kwargs)
            return await post_filter_tool_result(phone, capability, result, kwargs)
        return wrapper
    return decorator


async def _api(method: str, endpoint: str, phone: str, json_body: Optional[Dict] = None) -> Dict[str, Any]:
    token = _get_access_token(phone)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.request(method, f"{_PHOTOS_API}/{endpoint}", headers=headers, json=json_body)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("photos api failed exc=%s", exc)
        return {"error": str(exc)[:200]}


@_owner_guard("photos.read")
async def search_photos(phone: str, query: str = "", max_results: int = 5) -> Dict[str, Any]:
    """Busca fotos do usuário (por texto na pesquisa opcional)."""
    body: Dict[str, Any] = {"pageSize": max(1, min(max_results, 50))}
    if query:
        body["filters"] = {"contentFilter": {"includedContentCategories": []}}
        body["query"] = query
    data = await _api("POST", "mediaItems:search", phone, body)
    if "error" in data:
        return data
    items = data.get("mediaItems", [])
    return {
        "photos": [
            {
                "id": it.get("id"),
                "filename": it.get("filename", ""),
                "mimeType": it.get("mimeType", ""),
                "baseUrl": it.get("baseUrl", ""),
                "mediaMetadata": it.get("mediaMetadata", {}),
            }
            for it in items
        ],
        "count": len(items),
    }


@_owner_guard("photos.read")
async def get_photo_base64(phone: str, media_id: str, max_size: int = 800) -> Dict[str, Any]:
    """Retorna uma foto em base64 (para enviar no WhatsApp)."""
    data = await _api("GET", f"mediaItems/{media_id}", phone)
    if "error" in data:
        return data
    base_url = data.get("baseUrl", "")
    if not base_url:
        return {"error": "photo_not_found"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{base_url}=w{max_size}-h{max_size}")
            resp.raise_for_status()
        return {
            "filename": data.get("filename", "photo"),
            "mimeType": data.get("mimeType", "image/jpeg"),
            "base64": base64.b64encode(resp.content).decode("ascii"),
            "bytes": len(resp.content),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("photos download failed exc=%s", exc)
        return {"error": str(exc)[:200]}
