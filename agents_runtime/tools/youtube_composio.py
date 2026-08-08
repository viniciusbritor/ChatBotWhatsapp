"""YouTube tools via Composio API (HTTP direto, mesmo header do MCP)."""
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

_YOUTUBE_ACCOUNT = os.getenv("COMPOSIO_YOUTUBE_ACCOUNT", "youtube_begall-sozin")
_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
_BASE_URL = "https://backend.composio.dev/api/v3"


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
        logger.info("COMPOSIO_API_KEY loaded from SecretManager: %d chars", len(_CACHED_KEY))
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY from Secret Manager: %s", exc)
        return ""


async def _api_call(tool_slug: str, arguments: Dict[str, Any], connected_account_id: str) -> Dict[str, Any]:
    key = _get_api_key()
    if not key:
        return {"error": "composio_api_key_missing"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/tools/{tool_slug}/execute",
                headers={
                    "x-consumer-api-key": key,
                    "Content-Type": "application/json",
                },
                json={
                    "arguments": arguments,
                    "connected_account_id": connected_account_id,
                },
            )
            if resp.status_code >= 400:
                logger.warning("Composio HTTP %d: %s tool=%s", resp.status_code, resp.text[:200], tool_slug)
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
            return data.get("data", data)
    except Exception as exc:
        logger.warning("Composio HTTP call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def search_videos(query: str, max_results: int = 5) -> Dict[str, Any]:
    return await _api_call("YOUTUBE_SEARCH_YOU_TUBE", {
        "query": query[:500],
        "max_results": max_results,
    }, _YOUTUBE_ACCOUNT)


async def get_video_details(video_ids: list) -> Dict[str, Any]:
    return await _api_call("YOUTUBE_GET_VIDEO_DETAILS_BATCH", {
        "video_ids": video_ids[:50],
    }, _YOUTUBE_ACCOUNT)
