"""Prefetch module — pre-load Google data for faster agent responses.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).

Fallback: returns None on any error (pipeline continues without cache).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PREFETCH_TIMEOUT_SEC = 4.0


async def prefetch_for_agent(
    phone: str,
    instance: str,
    agent_type: str,
    text: str = "",
) -> Optional[str]:
    """Prefetch Calendar/Email/Drive data.

    Returns str with formatted data, or None if prefetch fails.
    Pipeline continues regardless — prefetch is optional cache.
    """
    try:
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
    except asyncio.TimeoutError:
        logger.warning("prefetch_timeout agent=%s", agent_type)
    except Exception as exc:
        logger.warning("prefetch_failed agent=%s error=%s", agent_type, exc)
    return None
