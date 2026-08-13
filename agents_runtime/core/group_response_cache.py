"""In-memory response cache for repeated group queries (FinOps Phase 2).

Reduces LLM token consumption and delivers ultra-fast responses (~50ms)
for identical queries within the same group within a 10-minute window (TTL 600s).
"""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional, Tuple

CACHE_TTL_SEC: int = 600
_RESPONSE_CACHE: Dict[str, Tuple[float, str]] = {}


def _make_key(group_id: str, query: str) -> str:
    norm_query = " ".join((query or "").strip().lower().split())
    raw = f"{group_id}:{norm_query}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_group_response(group_id: str, query: str) -> Optional[str]:
    """Retrieve cached response if valid and not expired."""
    if not group_id or not query:
        return None
    key = _make_key(group_id, query)
    entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    timestamp, response = entry
    if time.time() - timestamp >= CACHE_TTL_SEC:
        _RESPONSE_CACHE.pop(key, None)
        return None
    return response


def set_cached_group_response(group_id: str, query: str, response: str) -> None:
    """Store group query response with current timestamp."""
    if not group_id or not query or not response:
        return
    key = _make_key(group_id, query)
    _RESPONSE_CACHE[key] = (time.time(), response)


def clear_group_response_cache() -> None:
    """Clear all cached group responses."""
    _RESPONSE_CACHE.clear()


__all__ = [
    "CACHE_TTL_SEC",
    "get_cached_group_response",
    "set_cached_group_response",
    "clear_group_response_cache",
]
