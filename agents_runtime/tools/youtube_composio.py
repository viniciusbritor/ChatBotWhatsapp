"""YouTube tools via Composio SDK (helper compartilhado).

GUARDRAIL §0.8 (17/08/2026): refatorado para usar `composio_call` de
`tools._composio_common` que extrai o data real corretamente.
"""
import logging
from typing import Any, Dict

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def search_videos(query: str, max_results: int = 5, **kwargs) -> Dict[str, Any]:
    """Busca videos no YouTube."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "YOUTUBE_SEARCH_YOU_TUBE",
        {"q": query[:500], "maxResults": max_results},
        user_id=user_id,
    )


async def get_video_details(video_ids: list, **kwargs) -> Dict[str, Any]:
    """Retorna detalhes de videos por IDs."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "YOUTUBE_GET_VIDEO_DETAILS_BATCH",
        {"id": video_ids[:50]},
        user_id=user_id,
    )