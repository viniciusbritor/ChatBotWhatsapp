"""In-process rate limiter (F4d.9).

Token-bucket-lite per phone: keeps a sliding 60s window of timestamps
and refuses when more than ``RATE_LIMIT_PER_MIN`` events land in
that window.

The limiter is per-process. With ``min-instances=0`` and
``max-instances=5`` on Cloud Run, traffic can be split across 5
replicas — each replica has its own bucket. That is acceptable
defense-in-depth: at worst, a malicious user gets 5x the budget,
not unlimited.

For stricter limits, swap to Redis (``core.rate_limit_redis``) later.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
WINDOW_SECONDS = 60

_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def is_rate_limited(phone: str) -> Tuple[bool, int]:
    """Return (rate_limited, remaining_in_window).

    ``rate_limited`` is True when the phone has already sent
    ``MAX_PER_MINUTE`` messages in the last 60s and the next one
    would exceed the budget.
    """
    if not phone:
        return False, MAX_PER_MINUTE
    now = time.time()
    with _lock:
        bucket = _buckets[phone]
        cutoff = now - WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= MAX_PER_MINUTE:
            return True, 0
        bucket.append(now)
        remaining = max(0, MAX_PER_MINUTE - len(bucket))
        return False, remaining


def reset(phone: Optional[str] = None) -> None:
    """Reset a single phone or every bucket. Used in tests."""
    with _lock:
        if phone is None:
            _buckets.clear()
        else:
            _buckets.pop(phone, None)


__all__ = ["is_rate_limited", "reset", "MAX_PER_MINUTE", "WINDOW_SECONDS"]
