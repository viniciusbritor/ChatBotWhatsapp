"""YouTube tools via Composio SDK."""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_YOUTUBE_ACCOUNT = os.getenv("COMPOSIO_YOUTUBE_ACCOUNT", "youtube_begall-sozin")
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
        logger.info("COMPOSIO_API_KEY loaded from SecretManager: %d chars, starts with %s", len(_CACHED_KEY), _CACHED_KEY[:7])
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
            connected_account_id=_YOUTUBE_ACCOUNT,
        )
        return result.get("data", result)
    except ImportError:
        logger.warning("Composio SDK not installed")
        return {"error": "composio_sdk_missing"}
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def search_videos(query: str, max_results: int = 5) -> Dict[str, Any]:
    return await _composio_call("YOUTUBE_SEARCH_YOU_TUBE", {
        "query": query[:500],
        "max_results": max_results,
    })


async def get_video_details(video_ids: list) -> Dict[str, Any]:
    return await _composio_call("YOUTUBE_GET_VIDEO_DETAILS_BATCH", {
        "video_ids": video_ids[:50],
    })
