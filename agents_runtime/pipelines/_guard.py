"""Guard module — OAuth + owner check for Google tools.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).
NOT used by: doc_pipeline (rag path), jennifer_pipeline.

Fallback: returns deny if guard fails (safe default).

Group consent (10/08/2026): em grupos, um membro NAO-owner pode acessar as
proprias tools Google apos self-confirm. O fluxo:
  1. check_google_access retorna verdict="needs_group_consent" e cria
     pending_action group_consent (TTL 300s).
  2. Jennifer responde "digite 'sim' para confirmar".
  3. Membro responde "sim" -> orchestrator consome o pending_action,
     set_member_confirmation(confirmed=True) e re-rota o pipeline.
  4. Nas proximas vezes, o membro confirmado recebe allow direto.
Isolamento garantido: o token Google usado e SEMPRE o do phone do membro
(usuarios/{phone}.google_oauth_token) — nunca o do admin.
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
    is_group: bool = False,
    group_jid: str = "",
    original_text: str = "",
) -> Dict[str, Any]:
    """Verifica OAuth + owner para acesso a ferramentas Google.

    Args:
        instance: Instancia Evolution.
        phone: Phone do remetente.
        agent_type: 'calendar' | 'email' | 'drive'.
        is_group: True se a mensagem veio de um grupo WhatsApp.
        group_jid: JID do grupo (ex: 120363...@g.us) quando is_group.
        original_text: Texto original do pedido (usado para re-rotear
            apos o self-confirm do membro).

    Returns:
        {"verdict": "allow"|"deny"|"request_oauth"|"needs_group_consent",
         "reason": str, "oauth_link": str|None}
    """
    capability = _CAPABILITY_MAP.get(agent_type, "noop")
    try:
        from agent_orchestration.access_guardian import decide_guardian

        decision = decide_guardian(
            instance=instance,
            phone=phone,
            capability=capability,
        )
        if decision.verdict == "deny" and decision.reason == "not_owner" and is_group and group_jid:
            group_decision = await _handle_group_member_access(
                phone=phone,
                agent_type=agent_type,
                group_jid=group_jid,
                original_text=original_text,
            )
            if group_decision is not None:
                return group_decision
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


async def _handle_group_member_access(
    phone: str,
    agent_type: str,
    group_jid: str,
    original_text: str,
) -> Dict[str, Any]:
    """Fluxo de membro de grupo (nao-owner) usando tools Google.

    - Membro ja confirmado -> allow (usa o token DO MEMBRO).
    - Membro nao confirmado -> cria pending_action group_consent e
      retorna needs_group_consent.
    """
    capability = _CAPABILITY_MAP.get(agent_type, "noop")
    try:
        from tools.group import get_member_confirmation

        confirmed = await get_member_confirmation(group_jid, phone)
    except Exception as exc:
        logger.debug("group_member_confirmation_check_failed phone=%s exc=%s", phone, exc)
        confirmed = False

    if confirmed:
        logger.info("group_member_confirmed phone=%s group=%s capability=%s", phone, group_jid, capability)
        return {
            "verdict": "allow",
            "reason": "group_member_confirmed",
            "oauth_link": None,
            "capability": capability,
        }

    try:
        from core.pending_actions import set_pending_action

        await set_pending_action(
            phone,
            "group_consent",
            {
                "intent": agent_type,
                "group_jid": group_jid,
                "original_text": original_text,
            },
        )
        logger.info(
            "group_consent_pending_created phone=%s group=%s intent=%s",
            phone, group_jid, agent_type,
        )
    except Exception as exc:
        logger.warning("group_consent_pending_failed phone=%s exc=%s", phone, exc)
    return {
        "verdict": "needs_group_consent",
        "reason": "group_consent_required",
        "oauth_link": None,
        "capability": capability,
        "group_jid": group_jid,
    }


def blocked_response(guard: Dict[str, Any]) -> Dict[str, Any]:
    """Formata resposta de bloqueio para o usuário."""
    verdict = guard.get("verdict", "deny")
    capability = guard.get("capability", "")
    if verdict == "needs_group_consent":
        return {
            "reply": (
                f"Para acessar {capability} neste grupo, digite 'sim' para "
                f"confirmar. Seus dados sao protegidos: eu acesso apenas a "
                f"SUA conta (email/agenda/arquivos), nunca a de outra pessoa."
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "access_guardian",
                "blocked": True,
                "blocked_reason": "group_consent_required",
                "pending_action": "group_consent",
            },
        }
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
