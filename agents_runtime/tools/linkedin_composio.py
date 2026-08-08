"""LinkedIn tools via Composio SDK."""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LINKEDIN_ACCOUNT = os.getenv("COMPOSIO_LINKEDIN_ACCOUNT", "linkedin_struma-torula")
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
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY from Secret Manager: %s", exc)
        return ""


async def _composio_call(tool_slug: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from composio import Composio
        client = Composio(api_key=_get_api_key())
        result = client.tools.execute(
            slug=tool_slug,
            arguments=arguments,
            connected_account_id=_LINKEDIN_ACCOUNT,
        )
        return result.get("data", result)
    except ImportError:
        logger.warning("Composio SDK not installed")
        return {"error": "composio_sdk_missing"}
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def create_post(
    text: str,
    visibility: str = "PUBLIC",
    images: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return await _composio_call("LINKEDIN_CREATE_LINKED_IN_POST", {
        "text": text[:3000],
        "visibility": visibility,
        "images": images or [],
    })


async def read_post(post_id: str) -> Dict[str, Any]:
    return await _composio_call("LINKEDIN_GET_POST_CONTENT", {"post_id": post_id})


async def my_profile() -> Dict[str, Any]:
    return await _composio_call("LINKEDIN_GET_MY_INFO", {})


async def create_article(text: str, title: str = "") -> Dict[str, Any]:
    return await _composio_call("LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE", {
        "text": text[:3000],
        "title": title[:200],
    })
