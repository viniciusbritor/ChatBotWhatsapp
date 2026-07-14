"""Web search tools - Serper.dev + URL fetch with L1/L2 cache."""
import os
import time
import hashlib
import json
import logging
from typing import Optional, Dict, Any
import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"
CACHE_TTL_SECONDS = 24 * 3600
L1_CACHE: Dict[str, Dict[str, Any]] = {}
FIRESTORE_COLLECTION = "web_cache"


def _hash_query(query: str) -> str:
    """Stable hash for cache key."""
    return hashlib.sha256(query.lower().strip().encode("utf-8")).hexdigest()[:32]


def _get_l1_cache(query_hash: str) -> Optional[Dict[str, Any]]:
    """L1 in-memory cache lookup."""
    if query_hash in L1_CACHE:
        entry = L1_CACHE[query_hash]
        if time.time() - entry["ts"] < CACHE_TTL_SECONDS:
            logger.debug(f"L1 cache hit: {query_hash}")
            return entry["data"]
        else:
            del L1_CACHE[query_hash]
    return None


def _set_l1_cache(query_hash: str, data: Dict[str, Any]):
    """Store in L1 cache."""
    L1_CACHE[query_hash] = {"data": data, "ts": time.time()}
    if len(L1_CACHE) > 1000:
        oldest = min(L1_CACHE.keys(), key=lambda k: L1_CACHE[k]["ts"])
        del L1_CACHE[oldest]


def _get_l2_cache(query_hash: str) -> Optional[Dict[str, Any]]:
    """L2 Firestore cache lookup."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        db = firestore.Client(project=project)
        doc = db.collection(FIRESTORE_COLLECTION).document(query_hash).get()
        if doc.exists:
            data = doc.to_dict()
            if data and time.time() - data.get("ts", 0) < CACHE_TTL_SECONDS:
                logger.debug(f"L2 cache hit: {query_hash}")
                _set_l1_cache(query_hash, data["data"])
                return data["data"]
    except Exception as e:
        logger.warning(f"L2 cache read error: {e}")
    return None


def _set_l2_cache(query_hash: str, query: str, data: Dict[str, Any]):
    """Store in L2 Firestore cache."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return
        db = firestore.Client(project=project)
        db.collection(FIRESTORE_COLLECTION).document(query_hash).set({
            "query": query,
            "data": data,
            "ts": time.time(),
        })
    except Exception as e:
        logger.warning(f"L2 cache write error: {e}")


async def serper_search(query: str, num: int = 10) -> Dict[str, Any]:
    """Search the web via Serper.dev with L1+L2 cache.

    Args:
        query: Search query
        num: Number of results (max 100)

    Returns:
        {"results": [...], "query": str, "cached": bool}
    """
    query_hash = _hash_query(query)

    cached = _get_l1_cache(query_hash) or _get_l2_cache(query_hash)
    if cached:
        return {"results": cached, "query": query, "cached": True}

    api_key = get_secret("SERPER_API_KEY")
    if not api_key:
        return {"results": [], "query": query, "error": "SERPER_API_KEY not configured"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": min(num, 100)},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "position": item.get("position"),
            })

        _set_l1_cache(query_hash, results)
        _set_l2_cache(query_hash, query, results)
        return {"results": results, "query": query, "cached": False}
    except httpx.HTTPError as e:
        logger.error(f"Serper search error: {e}")
        return {"results": [], "query": query, "error": str(e)}


async def fetch_url(url: str, timeout: int = 30) -> Dict[str, Any]:
    """Fetch a URL and return its content.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        {"content": str, "status_code": int, "url": str}
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 agents_runtime"})
            return {
                "content": resp.text[:50000],
                "status_code": resp.status_code,
                "url": str(resp.url),
            }
    except httpx.HTTPError as e:
        logger.error(f"fetch_url error for {url}: {e}")
        return {"content": "", "status_code": 0, "url": url, "error": str(e)}