"""Typing effect delay calculator.

Formula: delay_ms = min(0.6 * word_count * 1000, cap_ms)
Default cap: 15000 ms (15s).
"""
import logging

logger = logging.getLogger(__name__)


def calculate_delay_ms(
    text: str,
    ms_per_word: float = 600.0,
    cap_ms: int = 15000,
) -> int:
    """Calculate typing delay in milliseconds.

    Args:
        text: Response text.
        ms_per_word: Delay per word in milliseconds (default 600 = 0.6s).
        cap_ms: Maximum delay cap in milliseconds (default 15000 = 15s).

    Returns:
        Delay in milliseconds (always >= 0, <= cap_ms).
    """
    if not text:
        return 0

    word_count = len(text.split())
    delay_ms = int(0.6 * word_count * 1000) if ms_per_word == 600.0 else int(word_count * ms_per_word)

    if delay_ms < 0:
        delay_ms = 0

    if delay_ms > cap_ms:
        delay_ms = cap_ms

    logger.debug(f"Typing delay for {word_count} words: {delay_ms}ms")
    return delay_ms


def calculate_presence() -> str:
    """Return the presence state for WhatsApp typing indicator."""
    return "composing"