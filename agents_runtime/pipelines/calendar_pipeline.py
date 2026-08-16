"""Calendar pipeline — keyword-only, zero LLM.

Detect: priority patterns → keyword fallback.
Run: guard OAuth → ack → prefetch → agent.

Usado apenas em conversas privadas ou grupos com membro confirmado.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

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
    matched, _confidence = detect_with_confidence(text)
    return matched


def detect_with_confidence(text: str) -> Tuple[bool, float]:  # noqa: F811
    """Compat: delega para helper compartilhado."""
    from pipelines._intent import detect_with_confidence as _detect
    return _detect(text, CALENDAR_PRIORITY, CALENDAR_KEYWORDS, EXCLUDE_PATTERNS)


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa o pipeline de Calendar: guard → ack → prefetch → agent."""
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._guard import check_google_access, blocked_response

    extra = payload.get("extra", {}) or {}
    is_group = bool(extra.get("is_group", False))
    remote_jid = str(payload.get("remote_jid", "") or "")
    group_jid = remote_jid if is_group else ""
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

    from pipelines._intent import should_prefetch
    from pipelines._prefetch import prefetch_for_agent

    prefetch = None
    _matched, confidence = detect_with_confidence(text)
    if should_prefetch(confidence, threshold=0.7):
        try:
            prefetch = await prefetch_for_agent(phone, instance, "calendar")
        except Exception:
            pass
    else:
        logger.debug(
            "prefetch_skipped_low_confidence agent=calendar confidence=%.2f",
            confidence,
        )

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
