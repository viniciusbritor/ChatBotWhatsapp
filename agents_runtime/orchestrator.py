"""Orchestrator - routes incoming messages to appropriate agent.

Flow:
1. Receive message from /chat endpoint
2. Detect special cases (audio, groups, morality, learning)
3. Determine orchestrator agent (jennifier)
4. Check if message has keywords/intent for direct delegation
5. Call LLM with orchestrator system_prompt + tools
6. If LLM emits function_call, delegate to manager/specialist
7. Return final response with delay_ms

This is a simplified orchestrator (not full Agno Team) for clarity and testability.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List

from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.escalation import compute_confidence_score, should_escalate
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.commands import detect_command, apply_command
from tool_registry import TOOL_REGISTRY, get_tool
from agent_loader import get_agent, get_skill, list_skills
from core.audit import log_action

logger = logging.getLogger(__name__)

GROSS_KEYWORDS = [
    "puta", "merda", "caralho", "fdp", "porra", "cu", "cuzão", "cuzão",
    "buceta", "viado", "bicha", "desgraça",
    "foder", "fode", "piranha", "vagabunda", "puto",
    "merda", "bosta", "porcaria", "desgraçado",
]
ASSAULT_KEYWORDS = [
    "assedio", "abuso", "estupro", "violencia", "agressao",
    "ameaça", "ameaca", "chantagem",
]
CORRECTION_KEYWORDS = [
    "na verdade", "não é assim", "nao e assim", "errado", "errada",
    "meu nome e", "meu nome é", "na verdade meu nome",
]


def _detect_intent(text: str) -> Dict[str, Any]:
    """Detect special intents in user message."""
    text_lower = text.lower()
    return {
        "is_gross": any(kw in text_lower for kw in GROSS_KEYWORDS),
        "is_assault_related": any(kw in text_lower for kw in ASSAULT_KEYWORDS),
        "is_correction": any(kw in text_lower for kw in CORRECTION_KEYWORDS),
    }


def _build_skills_section(skill_ids: List[str]) -> str:
    """Build skills content section for system prompt."""
    if not skill_ids:
        return ""
    parts = ["\n\n# Skills ativas:"]
    for sid in skill_ids:
        skill = get_skill(sid)
        if skill and skill.get("enabled", True):
            parts.append(f"\n## {skill['name']}\n{skill.get('content', '')}")
    return "\n".join(parts)


def _select_orchestrator_agent(instance: str) -> Optional[str]:
    """Select which orchestrator agent to use for this instance."""
    for agent_id, agent in _iter_agents():
        if agent.get("role") == "orchestrator" and agent.get("enabled", True):
            if instance in agent.get("instances", []) or not agent.get("instances"):
                return agent_id
    return None


def _iter_agents():
    """Helper to iterate over agents cache (avoids circular import)."""
    from agent_loader import _agents_cache
    for agent_id, agent in _agents_cache.items():
        yield agent_id, agent


def _resolve_agent_for_intent(intent: Dict[str, Any], instance: str) -> Optional[str]:
    """Resolve which specialist agent should handle this intent."""
    if intent["is_gross"] or intent["is_assault_related"]:
        return "agent-morality"
    if intent["is_correction"]:
        return "agent-learning"
    return None


async def orchestrate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Main orchestration entry point.

    Args:
        payload: {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": "oi",
            "sender_name": "Vinicius",
            "extra": {...}
        }

    Returns:
        {
            "reply": str,
            "delay_ms": int,
            "presence": str,
            "metadata": {
                "agent_id": str,
                "model_used": str,
                "escalated": bool,
                "tool_calls": [...]
            }
        }
    """
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    sender_name = payload.get("sender_name", "user")
    extra = payload.get("extra", {})

    masked_text = mask_pii(text)

    intent = _detect_intent(masked_text)
    specialist_id = _resolve_agent_for_intent(intent, instance)

    cmd = detect_command(masked_text)
    if cmd:
        logger.info(f"Proactive command detected from {phone}: {cmd}")
        cmd_result = await apply_command(phone, cmd)
        log_action(
            actor="user",
            action="PROACTIVE_COMMAND",
            target=phone,
            details={"command": cmd, "result": cmd_result},
        )
        return {
            "reply": cmd_result.get("message", "Comando aplicado."),
            "delay_ms": 0,
            "presence": "paused",
            "metadata": {
                "agent_id": "command-handler",
                "command": cmd,
                "applied": True,
            },
        }

    if specialist_id:
        agent = get_agent(specialist_id)
        if agent and agent.get("enabled", True):
            return await _execute_agent(agent, masked_text, payload, extra)

    orchestrator_id = _select_orchestrator_agent(instance)
    if not orchestrator_id:
        return _error_response(503, "no_orchestrator", "Nenhum orchestrator disponivel")

    orchestrator = get_agent(orchestrator_id)
    if not orchestrator:
        return _error_response(503, "agent_not_found", f"Orchestrator {orchestrator_id} nao encontrado")

    return await _execute_agent(orchestrator, masked_text, payload, extra)


async def _execute_agent(
    agent: Dict[str, Any],
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a specific agent with its system prompt and tools."""
    skills_section = _build_skills_section(agent.get("skills", []))
    system_prompt = agent.get("system_prompt", "") + skills_section

    static_user_prefix = (
        f"User: {payload.get('sender_name', 'user')} ({payload.get('phone', '')})\n"
    )
    dynamic_user_message = f"Mensagem: {text}"
    user_prompt = static_user_prefix + dynamic_user_message

    available_tools = agent.get("tools", [])

    llm = LLMProvider()
    if not llm.is_available():
        return _error_response(503, "llm_unavailable", "Nenhum provedor LLM configurado")

    threshold = agent.get("escalation_threshold", -2)
    no_escalation = agent.get("no_escalation", False)
    thinking = agent.get("thinking", "disabled") == "enabled"
    fast_model = agent.get("model", "deepseek-v4-flash")
    pro_model = agent.get("model_escalation") or "deepseek-v4-pro"

    def scoring_fn(text_response: str) -> int:
        return compute_confidence_score(text_response)

    try:
        result = llm.chat_escalating(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fast_model=fast_model,
            pro_model=pro_model,
            threshold=threshold,
            no_escalation=no_escalation,
            temperature=0.7,
            max_tokens=500,
            thinking_disabled=not thinking,
            scoring_fn=scoring_fn,
        )

        reply_text = result["content"]
        delay_ms = calculate_delay_ms(reply_text)
        presence = calculate_presence()

        tool_calls = _extract_tool_calls(reply_text, available_tools)

        return {
            "reply": reply_text,
            "delay_ms": delay_ms,
            "presence": presence,
            "metadata": {
                "agent_id": agent.get("id"),
                "model_used": result["model_used"],
                "provider": result["provider"],
                "escalated": result.get("escalated", False),
                "confidence_score": result.get("confidence_score"),
                "tool_calls": tool_calls,
                "has_audio": extra.get("has_audio", False),
            },
        }
    except LLMError as e:
        logger.error(f"LLM cascade failed for agent {agent.get('id')}: {e}")
        return _error_response(503, "llm_unavailable", "Todos provedores LLM falharam.")
    except Exception as e:
        logger.exception(f"Unexpected error in _execute_agent")
        return _error_response(500, "internal_error", str(e))


def _extract_tool_calls(reply_text: str, available_tools: List[str]) -> List[Dict[str, Any]]:
    """Best-effort detection of tool calls mentioned in reply.

    Checks both resource name (calendar) and method (list_events).
    For MVP, we detect by name pattern. Real Agno tool-calling would be JSON.
    """
    tool_calls = []
    if not reply_text or not available_tools:
        return tool_calls

    reply_lower = reply_text.lower()
    for tool_id in available_tools:
        parts = tool_id.split(".")
        resource = parts[0].replace("_", " ") if len(parts) > 0 else ""
        method = parts[-1].replace("_", " ") if len(parts) > 1 else ""

        matched = False
        match_type = None
        if resource and resource in reply_lower:
            matched = True
            match_type = "resource"
        elif method and method in reply_lower:
            matched = True
            match_type = "method"

        if matched:
            tool_calls.append({
                "tool_id": tool_id,
                "source": "text_match",
                "match_type": match_type,
            })
    return tool_calls


def _error_response(status_code: int, error: str, message: str) -> Dict[str, Any]:
    return {
        "reply": message,
        "delay_ms": 0,
        "presence": "paused",
        "metadata": {
            "error": error,
            "status_code": status_code,
        },
    }