"""Observability hooks (Fase 0 / F4d.12).

Lightweight instrumentation layer that records:
- ``latency_breakdown``: per-stage timings (webhook_received, intent,
  agent_resolved, deepagent_started, tool_called, response_sent).
- ``cost_breakdown``: token usage for DeepSeek chat completions and
  OpenAI embeddings.
- Structured logs that emit one ``observability_event`` per stage.

The hook is opt-in via the ``OBSERVABILITY_ENABLED`` env var (default
``true``). When disabled, every helper is a no-op so the hot path
incurs zero overhead.

Threading: ``current_tracker()`` returns the per-task tracker set via
``set_current_tracker()`` at the top of ``orchestrate``. Inner
functions (``_execute_agent``, ``_execute_deep_agent``, etc.) read
the tracker without threading it through every signature.

The data is attached to ``metadata.latency_breakdown`` on the
orchestration result so callers can ship it to Cloud Logging /
BigQuery later.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


_ENABLED = os.getenv("OBSERVABILITY_ENABLED", "true").lower() != "false"


def is_enabled() -> bool:
    return _ENABLED


def reset() -> None:
    """Reset module state (used in tests)."""
    global _ENABLED
    _ENABLED = os.getenv("OBSERVABILITY_ENABLED", "true").lower() != "false"


_tracker_local = threading.local()


def set_current_tracker(tracker: "LatencyTracker") -> None:
    _tracker_local.tracker = tracker


def current_tracker() -> "LatencyTracker":
    tracker = getattr(_tracker_local, "tracker", None)
    if tracker is None:
        return _ensure_null_tracker()
    return tracker


_NULL_TRACKER = None


def _ensure_null_tracker() -> "LatencyTracker":
    global _NULL_TRACKER
    if _NULL_TRACKER is None:
        _NULL_TRACKER = LatencyTracker(enabled=False)
    return _NULL_TRACKER


def new_tracker() -> "LatencyTracker":
    if not _ENABLED:
        return _ensure_null_tracker()
    return LatencyTracker(enabled=True)


class LatencyTracker:
    """Per-turn latency + cost recorder.

    Usage::

        tracker = new_tracker()
        set_current_tracker(tracker)
        with tracker.stage("webhook_received"):
            ...
        with tracker.stage("intent_detected"):
            ...
        with tracker.stage("deepagent_started"):
            ...
        tracker.add_cost("deepseek_input_tokens", 1200)
        tracker.add_cost("deepseek_output_tokens", 350)
        breakdown = tracker.breakdown()
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._started_at = time.monotonic() if enabled else 0.0
        self._stages: List[Dict[str, Any]] = []
        self._costs: Dict[str, int] = {}
        self._stage_counter = 0

    @contextmanager
    def stage(self, name: str, **extras: Any) -> Iterator[None]:
        if not self._enabled:
            yield
            return
        start = time.monotonic()
        try:
            yield
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            entry: Dict[str, Any] = {
                "stage": name,
                "ms": duration_ms,
                "order": self._stage_counter,
            }
            if extras:
                entry["meta"] = dict(extras)
            self._stages.append(entry)
            self._stage_counter += 1
            logger.info(
                "observability_event",
                extra={
                    "event_name": "observability_stage",
                    "stage": name,
                    "duration_ms": duration_ms,
                    **extras,
                },
            )

    def add_cost(self, key: str, value: int) -> None:
        if not self._enabled or not value:
            return
        self._costs[key] = self._costs.get(key, 0) + int(value)

    def add_costs(self, **kwargs: int) -> None:
        for k, v in kwargs.items():
            self.add_cost(k, v)

    def stages(self) -> List[Dict[str, Any]]:
        return list(self._stages)

    def costs(self) -> Dict[str, int]:
        return dict(self._costs)

    def total_ms(self) -> int:
        if not self._enabled:
            return 0
        return int((time.monotonic() - self._started_at) * 1000)

    def breakdown(self) -> Dict[str, Any]:
        if not self._enabled:
            return {}
        return {
            "total_ms": self.total_ms(),
            "stages": self.stages(),
            "costs": self.costs(),
        }


def attach_to_metadata(
    metadata: Dict[str, Any],
    tracker: "LatencyTracker",
) -> Dict[str, Any]:
    """Merge a tracker's breakdown into an existing metadata dict.

    Returns the same dict for chaining. No-op when observability is
    disabled or when the tracker is empty.
    """
    if not tracker._enabled:
        return metadata
    breakdown = tracker.breakdown()
    if not breakdown:
        return metadata
    metadata["latency_breakdown"] = breakdown
    return metadata


__all__ = [
    "LatencyTracker",
    "new_tracker",
    "set_current_tracker",
    "current_tracker",
    "attach_to_metadata",
    "is_enabled",
    "reset",
]