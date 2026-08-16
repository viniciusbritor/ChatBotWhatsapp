"""Intent confidence scoring para prefetch.

Fornece deteccao de intencao com score numerico (0.0-1.0) para que prefetch
possa ser skipped quando a confianca for baixa (caso ambiguo).

Heuristica:
- 0.0  = sem match (palavras-chave nem priority)
- 0.5  = match de keyword simples (1 keyword)
- 0.7  = match de priority pattern (alta confiança)
- 0.9  = match de priority + keyword (intencao clara)
- 1.0  = match multiplo (priority + keywords + sem exclusao)

Usado por:
- calendar_pipeline (is_calendar trigger)
- email_pipeline (is_email trigger)
- doc_pipeline (is_drive trigger)
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple


def detect_with_confidence(
    text: str,
    priority_patterns: Iterable[str],
    keywords: Iterable[str],
    exclude_patterns: Iterable[str] = (),
) -> Tuple[bool, float]:
    """Detecta intencao e retorna (bool, confidence) onde 0.0-1.0.

    Quando priority pattern matcha, keywords dentro do mesmo match NAO
    contam (elimina double-count por substrings).
    """
    if not text:
        return False, 0.0
    t = text.lower()
    priority_list = [p for p in priority_patterns if p]
    keyword_list = [k for k in keywords if k]
    exclude_list = [e for e in exclude_patterns if e]

    matched_priority = [p for p in priority_list if p in t]
    priority_hits = len(matched_priority)
    keyword_hits = sum(
        1 for k in keyword_list
        if k in t and not any(k in p or p in k for p in matched_priority)
    )
    has_exclusion = any(e in t for e in exclude_list)

    if priority_hits == 0 and keyword_hits == 0:
        return False, 0.0

    if has_exclusion:
        return False, 0.0

    if priority_hits > 0 and keyword_hits > 0:
        confidence = 0.9
    elif priority_hits > 0:
        confidence = 0.7
    elif keyword_hits == 1:
        confidence = 0.5
    else:
        confidence = 0.6

    return True, confidence


def should_prefetch(confidence: float, threshold: float = 0.7) -> bool:
    """Decide se deve prefetchar com base na confidence."""
    return confidence >= threshold
