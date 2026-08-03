"""Guard module — OAuth + owner check for Google tools.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).
NOT used by: doc_pipeline (rag path), jennifer_pipeline.

Fallback: returns deny if guard fails (safe default).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_CAPABILITY_MAP = {
    "calendar": "calendar.list_events",
    "email": "gmail.search_messages",
    "drive": "drive.search_files",
}


async def check_google_access(
    instance: str,
    phone: str,
    agent_type: str,
) -> Dict[str, Any]:
    """Verifica OAuth + owner para acesso a ferramentas Google.

    Returns:
        {"verdict": "allow"|"deny"|"request_oauth", "reason": str, "oauth_link": str|None}
    """
    capability = _CAPABILITY_MAP.get(agent_type, "noop")
    try:
        from agent_orchestration.access_guardian import decide_guardian

        decision = decide_guardian(
            instance=instance,
            phone=phone,
            capability=capability,
        )
        return {
            "verdict": decision.verdict,
            "reason": decision.reason,
            "oauth_link": getattr(decision, "oauth_link", None),
            "capability": capability,
        }
    except Exception as exc:
        logger.error("guard_failed capability=%s error=%s", capability, exc)
        return {
            "verdict": "deny",
            "reason": "guard_error",
            "capability": capability,
            "oauth_link": None,
        }


def blocked_response(guard: Dict[str, Any]) -> Dict[str, Any]:
    """Formata resposta de bloqueio para o usuário."""
    verdict = guard.get("verdict", "deny")
    capability = guard.get("capability", "")
    if verdict == "request_oauth":
        link = guard.get("oauth_link", "")
        return {
            "reply": (
                f"Oi! Para acessar {capability}, "
                f"preciso que voce autorize sua conta Google. "
                f"Acesse este link e faca o login: {link}"
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "access_guardian",
                "blocked": True,
                "blocked_reason": guard.get("reason", "request_oauth"),
            },
        }
    if verdict == "deny":
        return {
            "reply": (
                "Oi! Essa acao so pode ser executada pelo proprietario "
                "da conta WhatsApp."
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "access_guardian",
                "blocked": True,
                "blocked_reason": guard.get("reason", "deny"),
            },
        }
    return {}
