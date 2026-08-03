"""Jennifer pipeline — fallback para conversa geral.

Sempre da match (fallback). Sem guard OAuth, sem prefetch.
Usa o agente jennifer do Firestore (Flash, sem tools Google).

A intimidade (nickname consent) e tratada pelo orquestrador
via _setup_nickname_consent ANTES de chamar este pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def detect(text: str) -> bool:
    """Fallback: sempre True. E o ultimo pipeline na ordem de routing."""
    return True


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._executor import run_agent

    return await run_agent(
        "jennifer",
        text,
        payload,
        extra,
    )
