"""Prefetch module — pre-load Google data for faster agent responses.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).

Fallback: retry once on failure (Firestore cold start), then return None.
Pipeline continues regardless — prefetch is optional cache.

Retorna um dict ``{"text": str, "tabular": {...} | None}`` para que o
executor possa injetar o ``text`` no system_prompt e anexar o payload
tabular ao ``metadata`` da resposta (habilitando o auto-image mesmo
quando o LLM roda com ``tools: []``).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

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


def _build_tabular(agent_type: str, prefetch_text: str) -> Optional[Dict[str, Any]]:
    """Parse o JSON retornado por ``_prefetch_*`` e constroi o payload tabular.

    Os ``_prefetch_*`` fazem ``json.dumps(<lista estruturada>)``. Aqui
    fazemos o caminho inverso e delegamos a ``core.tabular.build_from_agent_type``.
    """
    try:
        raw = json.loads(prefetch_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, list):
        return None
    from core.tabular import build_from_agent_type
    return build_from_agent_type(agent_type, raw)


async def prefetch_for_agent(
    phone: str,
    instance: str,
    agent_type: str,
    text: str = "",
) -> Optional[Dict[str, Any]]:
    """Prefetch Calendar/Email/Drive data com retry para cold start.

    Retorna ``{"text": str, "tabular": dict | None}`` ou ``None`` se
    o prefetch falhar. O ``text`` é injetado no system_prompt pelo
    executor; o ``tabular`` é anexado ao ``metadata`` para o
    ``_detect_tabular_payload`` montar o PNG.
    """
    for attempt in range(2):
        try:
            result = await _prefetch_call(agent_type, phone, instance, text)
            if result is not None:
                return {"text": result, "tabular": _build_tabular(agent_type, result)}
        except asyncio.TimeoutError:
            logger.warning("prefetch_timeout agent=%s attempt=%d", agent_type, attempt + 1)
        except Exception as exc:
            logger.warning("prefetch_failed agent=%s attempt=%d error=%s", agent_type, attempt + 1, exc)
        if attempt == 0:
            logger.info("prefetch_retry agent=%s delay=%s", agent_type, PREFETCH_RETRY_DELAY_SEC)
            await asyncio.sleep(PREFETCH_RETRY_DELAY_SEC)
    return None
