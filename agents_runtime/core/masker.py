"""LGPD PII masker.

Patterns masked: CPF, RG, telefone, email, cartao, CNPJ.
Mask format: [MASK_{TYPE}].
"""
import re
import logging

logger = logging.getLogger(__name__)


PATTERNS = {
    "CPF": re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    "RG": re.compile(r"\d{1,2}\.?\d{3}\.?\d{3}-?\d{1}"),
    "CNPJ": re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"),
    "PHONE_BR": re.compile(r"\(?\d{2}\)?\s?9?\d{4,5}-?\d{4}"),
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "CARD": re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"),
}


def mask_pii(text: str) -> str:
    """Mask all PII patterns in text.

    Args:
        text: Input text potentially containing PII.

    Returns:
        Text with PII replaced by [MASK_{TYPE}].
    """
    if not text:
        return text

    masked = text
    for pii_type, pattern in PATTERNS.items():
        masked = pattern.sub(f"[MASK_{pii_type}]", masked)

    if masked != text:
        logger.debug(f"Masked PII in text ({len(text) - len(masked)} chars removed)")

    return masked


def has_pii(text: str) -> bool:
    """Check if text contains any PII pattern."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in PATTERNS.values())


def extract_pii(text: str) -> dict:
    """Extract all PII occurrences grouped by type."""
    if not text:
        return {}

    result = {}
    for pii_type, pattern in PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            result[pii_type] = matches
    return result
