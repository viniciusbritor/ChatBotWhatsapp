"""Email pipeline — keyword-only, zero LLM.

Detect: priority patterns → keyword fallback.
Run: guard OAuth → ack → prefetch → agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

EMAIL_PRIORITY = (
    "meus emails", "meus e-mails", "caixa de entrada", "ultimos emails",
    "ultimos e-mails", "ler email", "ler e-mail", "enviar email",
    "mandar email", "escrever email", "responder email",
)

EMAIL_KEYWORDS = (
    "email", "e-mail", "emails", "e-mails",
    "caixa de entrada", "caixa postal", "correio", "inbox",
    "gmail", "ler email", "enviar email", "ultimos emails",
    "ultima mensagem", "mensagens",
)

EXCLUDE_PATTERNS = (
    "agenda", "documento", "arquivo", "drive",
    "pdf", "docx", "xlsx", "planilha",
)


def detect(text: str) -> bool:
    t = text.lower()
    for pat in EMAIL_PRIORITY:
        if pat in t:
            return True
    for kw in EMAIL_KEYWORDS:
        if kw in t:
            has_exclusion = any(ex in t for ex in EXCLUDE_PATTERNS)
            if has_exclusion:
                return False
            return True
    return False


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._guard import check_google_access, blocked_response

    guard = await check_google_access(instance, phone, "email")
    if guard.get("verdict") != "allow":
        return blocked_response(guard)

    from pipelines._ack import send_ack

    try:
        await send_ack(instance, phone, "email", extra)
    except Exception:
        pass

    from pipelines._prefetch import prefetch_for_agent

    prefetch = None
    try:
        prefetch = await prefetch_for_agent(phone, instance, "email")
    except Exception:
        pass

    from pipelines._executor import run_agent

    return await run_agent(
        "manager-email",
        text,
        payload,
        extra,
        prefetch=prefetch,
        prefetch_label="EMAILS",
        tone_guide="Responda em portugues brasileiro com tom caloroso. "
                   "Liste emails do mais recente para o mais antigo.",
    )
