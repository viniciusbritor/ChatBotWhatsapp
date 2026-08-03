"""Prefetch module — pre-load Google data for faster agent responses.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).

Fallback: retry once on failure (Firestore cold start), then return None.
Pipeline continues regardless — prefetch is optional cache.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PREFETCH_TIMEOUT_SEC = 4.0
PREFETCH_RETRY_DELAY_SEC = 3.0


async def _prefetch_call(
    agent_type: str,
    phone: str,
    instance: str,
    text: str = "",
) -> Optional[str]:
    from orchestrator import (
        _prefetch_calendar,
        _prefetch_email,
        _prefetch_drive_multi,
    )

    if agent_type == "calendar":
        return await asyncio.wait_for(
            _prefetch_calendar(phone, instance),
            timeout=PREFETCH_TIMEOUT_SEC,
        )
    elif agent_type == "email":
        return await asyncio.wait_for(
            _prefetch_email(phone, instance),
            timeout=PREFETCH_TIMEOUT_SEC,
        )
    elif agent_type == "drive":
        return await asyncio.wait_for(
            _prefetch_drive_multi(phone, text, instance),
            timeout=PREFETCH_TIMEOUT_SEC,
        )
    return None


async def prefetch_for_agent(
    phone: str,
    instance: str,
    agent_type: str,
    text: str = "",
) -> Optional[str]:
    """Prefetch Calendar/Email/Drive data com retry para cold start.

    Returns str with formatted data, or None if prefetch fails.
    Pipeline continues regardless — prefetch is optional cache.
    """
    for attempt in range(2):
        try:
            result = await _prefetch_call(agent_type, phone, instance, text)
            if result is not None:
                return result
        except asyncio.TimeoutError:
            logger.warning("prefetch_timeout agent=%s attempt=%d", agent_type, attempt + 1)
        except Exception as exc:
            logger.warning("prefetch_failed agent=%s attempt=%d error=%s", agent_type, attempt + 1, exc)
        if attempt == 0:
            logger.info("prefetch_retry agent=%s delay=%s", agent_type, PREFETCH_RETRY_DELAY_SEC)
            await asyncio.sleep(PREFETCH_RETRY_DELAY_SEC)
    return None
