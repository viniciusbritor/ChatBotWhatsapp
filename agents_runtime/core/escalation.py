"""Escalation heuristic: Flash -> Pro.

Score-based:
  Negative score = low confidence = escalate
  Zero or positive = confident = keep Flash
"""
import re
import logging

logger = logging.getLogger(__name__)


LOW_CONFIDENCE_PHRASES = [
    r"nao sei",
    r"nao tenho certeza",
    r"desculpe,? nao posso",
    r"nao consigo",
    r"infelizmente",
    r"i don'?t know",
    r"i'?m not sure",
    r"i can'?t",
]


def compute_confidence_score(text: str) -> int:
    """Compute confidence score for an LLM response.

    Args:
        text: LLM response text.

    Returns:
        Integer score. Lower = less confident. Threshold default: -2.
    """
    if not text:
        return -3

    score = 0
    text_lower = text.lower().strip()
    word_count = len(text.split())

    if word_count < 8:
        score -= 2
    elif word_count < 3:
        score -= 3

    for phrase_pattern in LOW_CONFIDENCE_PHRASES:
        if re.search(phrase_pattern, text_lower):
            score -= 2
            break

    question_count = text.count("?")
    if question_count >= 3:
        score -= 1
    if question_count >= 5:
        score -= 2

    if _has_invalid_json(text):
        score -= 2

    if _has_excessive_emoji(text):
        score -= 1

    logger.debug(f"Confidence score for response ({word_count} words): {score}")
    return score


def _has_invalid_json(text: str) -> bool:
    """Heuristic: check if text looks like malformed JSON."""
    text = text.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return False
    if not (text.endswith("}") or text.endswith("]")):
        return True
    return False


def _has_excessive_emoji(text: str) -> bool:
    """Heuristic: more than 5 emojis in a short text = suspicious."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return len(emoji_pattern.findall(text)) > 5


def should_escalate(score: int, threshold: int = -2) -> bool:
    """Determine if response should be escalated to Pro model.

    Args:
        score: Confidence score from compute_confidence_score.
        threshold: Negative number. Score <= threshold triggers escalation.

    Returns:
        True if should escalate.
    """
    return score <= threshold
