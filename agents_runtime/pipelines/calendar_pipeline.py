"""Calendar pipeline — keyword-only, zero LLM.

Detect: priority patterns → keyword fallback.
Run: guard OAuth → ack → prefetch → agent.

Usado apenas em conversas privadas ou grupos com membro confirmado.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

CALENDAR_PRIORITY = (
    "agenda hoje", "agenda de hoje", "compromissos hoje", "compromissos de hoje",
    "criar evento", "crie um evento", "criar compromisso", "crie um compromisso",
    "criar um compromisso", "adicionar compromisso", "adicionar evento",
    "marcar compromisso", "marcar reuniao", "agendar", "novo compromisso",
    "agenda amanha", "compromissos amanha", "agenda da semana",
    "meus compromissos", "minha agenda", "eventos hoje",
)

CALENDAR_KEYWORDS = (
    "agenda", "agend", "reuniao", "evento", "eventos", "compromiss",
    "compromisso", "compromissos", "lembrete", "calendario", "disponivel",
    "semana que vem", "proxima semana", "agenda de hoje",
)

EXCLUDE_PATTERNS = (
    "documento", "arquivo", "email", "e-mail", "drive",
    "pdf", "docx", "xlsx", "planilha",
)


def detect(text: str) -> bool:
    """Prioridade: patterns exatos → keyword → false."""
    t = text.lower()
    for pat in CALENDAR_PRIORITY:
        if pat in t:
            return True
    for kw in CALENDAR_KEYWORDS:
        if kw in t:
            has_exclusion = any(ex in t for ex in EXCLUDE_PATTERNS)
            if has_exclusion:
                return False
            return True
    return False


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa o pipeline de Calendar: guard → ack → prefetch → agent."""
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._guard import check_google_access, blocked_response

    extra = payload.get("extra", {}) or {}
    is_group = "@g.us" in str(extra.get("remote_jid", ""))
    group_jid = str(extra.get("remote_jid", "")) if is_group else ""
    guard = await check_google_access(
        instance, phone, "calendar",
        is_group=is_group, group_jid=group_jid, original_text=text,
    )
    if guard.get("verdict") != "allow":
        return blocked_response(guard)

    from pipelines._ack import send_ack

    try:
        await send_ack(instance, phone, "calendar", extra)
    except Exception:
        pass

    from pipelines._prefetch import prefetch_for_agent

    prefetch = None
    try:
        prefetch = await prefetch_for_agent(phone, instance, "calendar")
    except Exception:
        pass

    from pipelines._executor import run_agent

    return await run_agent(
        "manager-calendar",
        text,
        payload,
        extra,
        prefetch=prefetch,
        prefetch_label="CALENDARIO",
        tone_guide="Responda em portugues brasileiro com tom caloroso. "
                   "Liste os eventos em ordem cronologica.",
    )
