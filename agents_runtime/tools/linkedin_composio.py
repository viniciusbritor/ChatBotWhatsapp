"""LinkedIn tools via Composio SDK + Secret Manager."""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


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
        logger.info("COMPOSIO_API_KEY loaded: %d chars", len(_CACHED_KEY))
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY: %s", exc)
        return (os.getenv("COMPOSIO_API_KEY", "") or "").strip()


async def _composio_call(tool_slug: str, arguments: Dict[str, Any], user_id: str = "") -> Dict[str, Any]:
    try:
        from composio import Composio
        from tools._composio_common import TOOLKIT_VERSIONS
        client = Composio(api_key=_get_api_key(), toolkit_versions=TOOLKIT_VERSIONS)
        result = client.tools.execute(slug=tool_slug, arguments=arguments, user_id=user_id)
        return result.get("data", result)
    except ImportError:
        return {"error": "composio_sdk_missing"}
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


_AUTHOR_URN_CACHE: Dict[str, str] = {}


async def _resolve_author_urn(user_id: str) -> str:
    cached = _AUTHOR_URN_CACHE.get(user_id)
    if cached:
        return cached
    profile = await my_profile(phone=user_id)
    person_id = profile.get("id") if isinstance(profile, dict) else None
    if person_id:
        urn = f"urn:li:person:{person_id}"
        _AUTHOR_URN_CACHE[user_id] = urn
        return urn
    return ""


async def create_post(text: str, visibility: str = "PUBLIC", images: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    author = await _resolve_author_urn(user_id)
    if not author:
        return {"error": "linkedin_author_urn_resolution_failed"}
    return await _composio_call("LINKEDIN_CREATE_LINKED_IN_POST", {
        "author": author, "commentary": text[:3000], "visibility": visibility, "images": images or [],
    }, user_id=user_id)


async def read_post(post_id: str, **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("LINKEDIN_GET_POST_CONTENT", {"post_id": post_id}, user_id=user_id)


async def my_profile(**kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("LINKEDIN_GET_MY_INFO", {}, user_id=user_id)


async def create_article(text: str, title: str = "", url: str = "", **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    author = await _resolve_author_urn(user_id)
    if not author:
        return {"error": "linkedin_author_urn_resolution_failed"}
    if url:
        share = {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "originalUrl": url[:500],
                    "title": {"text": title[:200] or text[:100]},
                    "status": "READY",
                }],
            }
        }
    else:
        share = {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
                "media": [],
            }
        }
    return await _composio_call("LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE", {
        "author": author, "visibility": "PUBLIC", "specificContent": share,
    }, user_id=user_id)
