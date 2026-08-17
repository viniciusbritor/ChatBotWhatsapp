"""Rate limiter por toolkit - protecao contra abuso de tools dinamic-discovery.

GUARDRAIL (17/08/2026): limita uso de tools auto-descobertas para
mitigar abuso (flood, prompt injection, etc). Limite padrao: 100 calls/hora/user.
"""
import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Deque, Dict

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT_PER_HOUR = 100
_window_seconds = 3600


class ToolkitRateLimiter:
    """Rate limiter in-memory por (toolkit_slug, phone) com janela deslizante."""

    def __init__(self, limit_per_hour: int = _DEFAULT_LIMIT_PER_HOUR):
        self._limit = limit_per_hour
        self._calls: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, toolkit_slug: str, phone: str) -> bool:
        """Retorna True se a chamada e permitida, False se excedeu limite."""
        key = f"{toolkit_slug}:{phone}"
        now = time.time()
        with self._lock:
            calls = self._calls[key]
            # Limpar chamadas antigas
            while calls and calls[0] < now - _window_seconds:
                calls.popleft()
            if len(calls) >= self._limit:
                logger.warning(
                    "toolkit_rate_limit_exceeded toolkit=%s phone=%s count=%d limit=%d",
                    toolkit_slug, phone, len(calls), self._limit,
                    extra={
                        "event_name": "toolkit_rate_limit_exceeded",
                        "toolkit": toolkit_slug,
                        "phone": phone,
                        "count": len(calls),
                        "limit": self._limit,
                    },
                )
                return False
            calls.append(now)
            return True

    def get_count(self, toolkit_slug: str, phone: str) -> int:
        """Retorna numero de chamadas na janela atual."""
        key = f"{toolkit_slug}:{phone}"
        now = time.time()
        with self._lock:
            calls = self._calls[key]
            while calls and calls[0] < now - _window_seconds:
                calls.popleft()
            return len(calls)

    def reset(self, toolkit_slug: str, phone: str):
        """Reseta contadores para um toolkit+user (usado apos bloqueio)."""
        key = f"{toolkit_slug}:{phone}"
        with self._lock:
            self._calls.pop(key, None)


# Singleton global
toolkit_rate_limiter = ToolkitRateLimiter()