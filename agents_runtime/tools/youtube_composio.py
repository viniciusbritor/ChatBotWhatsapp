"""YouTube tools via Composio MCP."""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def _composio_call(tool_slug: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from composio import Composio
        client = Composio(api_key=os.getenv("COMPOSIO_API_KEY", ""))
        result = client.actions.execute(tool_slug, arguments)
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
