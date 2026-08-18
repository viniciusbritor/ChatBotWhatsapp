"""Executor module — load and run a DeepSeek agent.

Used by: ALL pipelines (calendar, email, doc, jennifer).
Essential dependency — if this breaks, all pipelines fail.

Includes emergency reload (_load_all) if agent not found on first try.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


async def run_agent(
    agent_id: str,
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
    *,
    prefetch: Optional[Union[str, Dict[str, Any]]] = None,
    prefetch_label: str = "",
    tone_guide: str = "",
) -> Dict[str, Any]:
    """Carrega e executa um agente DeepSeek.

    Args:
        agent_id: ID do agente no Firestore (ex: "manager-calendar").
        text: Texto da mensagem do usuário (com PII mascarado).
        payload: Payload original da mensagem.
        extra: Dicionário extra do payload.
        prefetch: ``str`` (legado) ou ``{"text": str, "tabular": dict|None}``
            retornado por ``pipelines._prefetch.prefetch_for_agent``.
        prefetch_label: Label para os dados pré-carregados (ex: "CALENDARIO").
        tone_guide: Guia de tom para adicionar ao system_prompt.

    Returns:
        {"reply": str, "delay_ms": int, "presence": str, "metadata": {...}}
        O ``metadata.tabular`` é populado quando ``prefetch["tabular"]`` vem
        com dados — habilita o auto-image mesmo quando o agente roda com
        ``tools: []`` (caminho de prefetch).
    """
    try:
        from agent_loader import resolve_agent_for_instance
        from orchestrator import (
            _execute_agent,
            _has_real_data,
        )

        instance = str(payload.get("instance", "") or extra.get("instance", ""))
        agent = resolve_agent_for_instance(instance, agent_id)
        if not agent or not agent.get("enabled", True):
            from agent_loader import _load_all

            try:
                _load_all()
                agent = resolve_agent_for_instance(instance, agent_id)
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

        # Normaliza prefetch para dict {text, tabular} - mantém compat com str.
        if isinstance(prefetch, str):
            prefetch_data: Dict[str, Any] = {"text": prefetch, "tabular": None}
        elif isinstance(prefetch, dict):
            prefetch_data = prefetch
        else:
            prefetch_data = {"text": None, "tabular": None}

        prefetch_text = prefetch_data.get("text")
        if prefetch_text and _has_real_data(prefetch_text):
            from core.masker import mask_pii

            safe_prefetch = mask_pii(prefetch_text)
            agent_copy["system_prompt"] = (
                agent_copy.get("system_prompt", "")
                + f"\n\n[DADOS PRE-CARREGADOS DO {prefetch_label}]\n{safe_prefetch}\n\n"
                + (tone_guide or "")
                + "Voce PODE chamar ferramentas se precisar criar, atualizar ou modificar algo."
            )
            # NAO zerar agent_copy["tools"] - o LLM precisa poder chamar
            # calendar.create_event, gmail.send_message, etc. mesmo com prefetch.
            # O prefetch so injeta dados no system_prompt como contexto.

        result = await _execute_agent(agent_copy, text, payload, extra)

        # Anexa payload tabular no metadata para o auto-image (mesmo com tools=[]).
        tabular = prefetch_data.get("tabular")
        if isinstance(tabular, dict) and tabular.get("rows"):
            result.setdefault("metadata", {})["tabular"] = tabular

        return result

    except Exception as exc:
        logger.error("run_agent_failed agent=%s error=%s", agent_id, exc)
        return {
            "reply": "Desculpe, ocorreu um erro ao processar sua solicitação.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": agent_id, "error": str(exc)[:200]},
        }
