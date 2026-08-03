"""Executor module — load and run a DeepSeek agent.

Used by: ALL pipelines (calendar, email, doc, jennifer).
Essential dependency — if this breaks, all pipelines fail.

Includes emergency reload (_load_all) if agent not found on first try.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def run_agent(
    agent_id: str,
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
    *,
    prefetch: Optional[str] = None,
    prefetch_label: str = "",
    tone_guide: str = "",
) -> Dict[str, Any]:
    """Carrega e executa um agente DeepSeek.

    Args:
        agent_id: ID do agente no Firestore (ex: "manager-calendar").
        text: Texto da mensagem do usuário (com PII mascarado).
        payload: Payload original da mensagem.
        extra: Dicionário extra do payload.
        prefetch: Dados pré-carregados para injetar no system_prompt.
        prefetch_label: Label para os dados pré-carregados (ex: "CALENDARIO").
        tone_guide: Guia de tom para adicionar ao system_prompt.

    Returns:
        {"reply": str, "delay_ms": int, "presence": str, "metadata": {...}}
    """
    try:
        from agent_loader import get_agent
        from orchestrator import (
            _execute_agent,
            _has_real_data,
        )

        agent = get_agent(agent_id)
        if not agent or not agent.get("enabled", True):
            from agent_loader import _load_all

            try:
                _load_all()
                agent = get_agent(agent_id)
            except Exception:
                pass

        if not agent or not agent.get("enabled", True):
            logger.warning("agent_not_found agent=%s", agent_id)
            return {
                "reply": f"Desculpe, o agente {agent_id} está indisponível no momento.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": agent_id, "error": "agent_not_found"},
            }

        agent_copy = dict(agent)

        if prefetch and _has_real_data(prefetch):
            from core.masker import mask_pii

            safe_prefetch = mask_pii(prefetch)
            agent_copy["system_prompt"] = (
                agent_copy.get("system_prompt", "")
                + f"\n\n[DADOS PRE-CARREGADOS DO {prefetch_label}]\n{safe_prefetch}\n\n"
                + (tone_guide or "")
                + "NAO chame ferramentas — os dados ja estao prontos."
            )
            agent_copy["tools"] = []

        return await _execute_agent(agent_copy, text, payload, extra)

    except Exception as exc:
        logger.error("run_agent_failed agent=%s error=%s", agent_id, exc)
        return {
            "reply": "Desculpe, ocorreu um erro ao processar sua solicitação.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": agent_id, "error": str(exc)[:200]},
        }
