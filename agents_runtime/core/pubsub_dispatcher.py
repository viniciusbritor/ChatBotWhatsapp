"""Ledger-driven dispatcher for ``/pubsub/push``.

The handler ensures exactly-once orchestrator execution by delegating the
idempotency decision to the Firestore ledger. The previous in-memory dedupe is
kept only as an early-return optimisation; the ledger remains authoritative.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from core.message_ledger import (
    claim,
    is_terminal,
    lease_alive,
    mark_delivered,
    mark_failed,
    mark_response,
    register_or_load,
    release_lease,
    renew_lease,
    resolve_message_id,
)

logger = logging.getLogger(__name__)


class TransientProcessingError(RuntimeError):
    """Raised for retryable infrastructure failures (OOM, timeouts)."""


def _parse_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, dict) and "data" in payload and isinstance(payload.get("data"), str):
        try:
            return json.loads(payload["data"])
        except json.JSONDecodeError:
            return payload
    return payload


async def dispatch_with_ledger(
    payload: Dict[str, Any],
    handler: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    envelope = _parse_envelope(payload)
    resolve_message_id(envelope)
    message_id = envelope.get("message_id") or envelope.get("request_id") or ""

    if not message_id:
        logger.warning("pubsub_dispatch_dropped reason=missing_message_id")
        return {"status": "dropped", "reason": "missing_message_id"}

    snapshot = register_or_load(message_id, envelope)
    if snapshot and is_terminal(snapshot):
        logger.info(
            "pubsub_dispatch_duplicate message_id=%s state=%s",
            message_id,
            snapshot.get("state"),
        )
        return {
            "status": "duplicate",
            "message_id": message_id,
            "ledger_state": snapshot.get("state"),
        }

    claim_snapshot = claim(message_id)
    if not claim_snapshot:
        if snapshot and lease_alive(snapshot):
            logger.info(
                "pubsub_dispatch_lease_busy message_id=%s state=%s",
                message_id,
                snapshot.get("state"),
            )
            return {
                "status": "lease_busy",
                "message_id": message_id,
            }
        claim_snapshot = snapshot or {}

    renew_task: Optional[asyncio.Task] = None
    stop_event = asyncio.Event()

    async def _renew_loop() -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                renew_lease(message_id)

    try:
        renew_task = asyncio.create_task(_renew_loop())
        result = await handler(envelope)
        if isinstance(result, dict):
            mark_response(message_id, result)
        return result
    except TransientProcessingError as exc:
        release_lease(message_id)
        mark_failed(message_id, f"transient:{exc}", terminal=False)
        logger.warning("pubsub_dispatch_transient message_id=%s error=%s", message_id, exc)
        raise
    except Exception as exc:  # noqa: BLE001
        mark_failed(message_id, f"terminal:{type(exc).__name__}:{exc}", terminal=True)
        logger.error(
            "pubsub_dispatch_failed message_id=%s error_type=%s",
            message_id,
            type(exc).__name__,
        )
        return {
            "status": "failed_terminal",
            "message_id": message_id,
            "error": str(exc),
        }
    finally:
        if renew_task is not None:
            stop_event.set()
            try:
                await asyncio.wait_for(renew_task, timeout=1)
            except asyncio.TimeoutError:
                renew_task.cancel()


def record_delivery(message_id: str, *, success: bool, error: str = "", attempts: int = 1) -> None:
    """Record the result of an Evolution delivery attempt."""
    mark_delivered(message_id, delivery_attempts=attempts, error="" if success else error)
