"""YouTube search tool."""
import os, logging, requests
from core.secrets import get_secret

logger = logging.getLogger(__name__)

_YOUTUBE_KEY = None

def _get_key():
    global _YOUTUBE_KEY
    if not _YOUTUBE_KEY:
        _YOUTUBE_KEY = (os.getenv("YOUTUBE_API_KEY") or get_secret("YOUTUBE_API_KEY") or "").strip()
    return _YOUTUBE_KEY


async def search_videos(query: str, max_results: int = 3) -> list:
    """Busca videos no YouTube e retorna titulo, canal e link."""
    key = _get_key()
    if not key:
        return [{"error": "YOUTUBE_API_KEY not configured"}]
    try:
        resp = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "q": query, "type": "video",
            "maxResults": max_results, "key": key, "relevanceLanguage": "pt"
        }, timeout=15)
        data = resp.json()
        results = []
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId", "")
            if not vid:
                continue
            snip = item.get("snippet", {})
            results.append({
                "titulo": snip.get("title", ""),
                "canal": snip.get("channelTitle", ""),
                "url": f"https://youtube.com/watch?v={vid}",
                "descricao": (snip.get("description", "") or "")[:150],
                "publicado_em": snip.get("publishedAt", ""),
            })
        return results
    except Exception as e:
        logger.error(f"youtube search failed: {e}")
        return [{"error": str(e)}]
