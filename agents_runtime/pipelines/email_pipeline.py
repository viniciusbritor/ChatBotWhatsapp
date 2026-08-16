"""Email pipeline — keyword-only, zero LLM.

Detect: priority patterns → keyword fallback.
Run: guard OAuth → ack → prefetch → agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

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
    matched, _confidence = detect_with_confidence(text)
    return matched


def detect_with_confidence(text: str) -> Tuple[bool, float]:  # noqa: F811
    """Compat: delega para helper compartilhado."""
    from pipelines._intent import detect_with_confidence as _detect
    return _detect(text, EMAIL_PRIORITY, EMAIL_KEYWORDS, EXCLUDE_PATTERNS)


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._guard import check_google_access, blocked_response

    is_group = bool(extra.get("is_group", False))
    remote_jid = str(payload.get("remote_jid", "") or "")
    group_jid = remote_jid if is_group else ""
    guard = await check_google_access(
        instance, phone, "email",
        is_group=is_group, group_jid=group_jid, original_text=text,
    )
    if guard.get("verdict") != "allow":
        return blocked_response(guard)

    from pipelines._ack import send_ack

    try:
        await send_ack(instance, phone, "email", extra)
    except Exception:
        pass

    from pipelines._intent import should_prefetch
    from pipelines._prefetch import prefetch_for_agent

    prefetch = None
    _matched, confidence = detect_with_confidence(text)
    if should_prefetch(confidence, threshold=0.7):
        try:
            prefetch = await prefetch_for_agent(phone, instance, "email")
        except Exception:
            pass
    else:
        logger.debug(
            "prefetch_skipped_low_confidence agent=email confidence=%.2f",
            confidence,
        )

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
