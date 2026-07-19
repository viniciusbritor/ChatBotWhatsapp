"""Proactive gate - 8 camadas anti-spam (calibrado)."""
import os
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ALLOWLIST = [p.strip() for p in os.getenv("PROACTIVE_OWNER_PHONES", "").split(",") if p.strip()]
MAX_PER_CONTACT_DAY = int(os.getenv("PROACTIVE_MAX_PER_CONTACT_DAY", "2"))
MAX_GLOBAL_DAY = int(os.getenv("PROACTIVE_MAX_GLOBAL_DAY", "5"))
COOLDOWN_HOURS = int(os.getenv("PROACTIVE_COOLDOWN_HOURS", "12"))
QUIET_HOURS_START = int(os.getenv("PROACTIVE_QUIET_HOURS_START", "21"))
QUIET_HOURS_END = int(os.getenv("PROACTIVE_QUIET_HOURS_END", "9"))
MIN_RELEVANCE = float(os.getenv("PROACTIVE_MIN_RELEVANCE", "0.75"))
MAX_PER_WEEK = 5

_disabled = os.getenv("PROACTIVE_DISABLED", "false").lower() == "true"
_dry_run = os.getenv("PROACTIVE_DRY_RUN", "false").lower() == "true"

_global_sent_today: Dict[str, int] = {}
_global_sent_date: str = ""


def _now_brt() -> datetime:
    """Current time in UTC (server runs in UTC; display in BRT is handled by clients)."""
    return datetime.now(timezone.utc)


def _is_quiet_hours() -> bool:
    """Check if current UTC hour is within quiet hours (interpreted as BRT)."""
    now = _now_brt()
    brt_hour = (now.hour - 3) % 24
    if QUIET_HOURS_START > QUIET_HOURS_END:
        return brt_hour >= QUIET_HOURS_START or brt_hour < QUIET_HOURS_END
    return QUIET_HOURS_START <= brt_hour < QUIET_HOURS_END


def _reset_global_counter_if_new_day():
    global _global_sent_today, _global_sent_date
    today = _now_brt().date().isoformat()
    if _global_sent_date != today:
        _global_sent_today = {}
        _global_sent_date = today


def check(
    phone: str,
    group_jid: Optional[str] = None,
    is_group_member: bool = False,
    contact_state: Optional[Dict[str, Any]] = None,
    relevance_score: float = 0.85,
) -> Tuple[bool, str]:
    """Check if a proactive message can be sent.

    Args:
        phone: Target phone (DM)
        group_jid: Target group (if group message)
        is_group_member: True if phone is member of the group
        contact_state: From Firestore contatos/{phone} - proactive_messages_today,
                       proactive_messages_this_week, proactive_cooldown_until,
                       proactive_mode, proactive_paused_until, proactive_eligible,
                       proactive_opt_out
        relevance_score: LLM relevance (0-1)

    Returns:
        (allowed, reason) - True if can send, with reason string
    """
    if _disabled:
        return False, "kill_switch_global"

    _reset_global_counter_if_new_day()

    if group_jid:
        return _check_group(group_jid, phone, is_group_member, contact_state, relevance_score)

    return _check_dm(phone, contact_state, relevance_score)


def _check_dm(
    phone: str,
    contact_state: Optional[Dict[str, Any]],
    relevance_score: float,
) -> Tuple[bool, str]:
    """Check DM proactivity rules."""
    if phone not in ALLOWLIST:
        return False, "not_in_allowlist"

    if contact_state is None:
        contact_state = {}

    if contact_state.get("proactive_opt_out", False):
        return False, "user_opt_out"

    paused_until = contact_state.get("proactive_paused_until")
    if paused_until:
        try:
            paused_dt = datetime.fromisoformat(paused_until.replace("Z", "+00:00"))
            if _now_brt() < paused_dt:
                return False, "engagement_paused"
        except Exception:
            pass

    mode = contact_state.get("proactive_mode", "normal")
    if mode == "off":
        return False, "user_set_off"
    if mode == "emergencies":
        if relevance_score < 0.9:
            return False, "emergencies_only_high_relevance"

    if _is_quiet_hours():
        return False, "quiet_hours"

    if relevance_score < MIN_RELEVANCE:
        return False, f"low_relevance_{relevance_score:.2f}"

    today_count = contact_state.get("proactive_messages_today", 0)
    if today_count >= MAX_PER_CONTACT_DAY:
        return False, "max_per_contact_day"

    week_count = contact_state.get("proactive_messages_this_week", 0)
    if week_count >= MAX_PER_WEEK:
        return False, "max_per_week"

    cooldown_until = contact_state.get("proactive_cooldown_until")
    if cooldown_until:
        try:
            cd_dt = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
            if _now_brt() < cd_dt:
                return False, "cooldown_active"
        except Exception:
            pass

    global_count = _global_sent_today.get(_global_sent_date, 0)
    if global_count >= MAX_GLOBAL_DAY:
        return False, "max_global_day"

    return True, "passed"


def _check_group(
    group_jid: str,
    phone: str,
    is_group_member: bool,
    contact_state: Optional[Dict[str, Any]],
    relevance_score: float,
) -> Tuple[bool, str]:
    """Check group proactivity rules."""
    if contact_state is None:
        contact_state = {}

    if not is_group_member and phone not in ALLOWLIST:
        return False, "not_member_and_not_master"

    if contact_state.get("proactive_opt_out", False):
        return False, "user_opt_out"

    if _is_quiet_hours():
        return False, "quiet_hours"

    if relevance_score < MIN_RELEVANCE:
        return False, f"low_relevance_{relevance_score:.2f}"

    today_count = contact_state.get("proactive_messages_today", 0)
    if today_count >= MAX_PER_CONTACT_DAY:
        return False, "max_per_contact_day"

    return True, "passed_group"


def is_dry_run() -> bool:
    return _dry_run


def record_sent(phone: str, group_jid: Optional[str] = None):
    """Record that a proactive message was sent (for global counter)."""
    _reset_global_counter_if_new_day()
    today = _global_sent_date
    _global_sent_today[today] = _global_sent_today.get(today, 0) + 1
    logger.info(f"Proactive sent to {phone or group_jid} (global today: {_global_sent_today[today]})")


def set_kill_switch(enabled: bool):
    """Toggle global kill switch."""
    global _disabled
    _disabled = enabled
    logger.info(f"Proactive kill switch set to {enabled}")


def get_config() -> Dict[str, Any]:
    """Get current gate configuration."""
    return {
        "allowlist": ALLOWLIST,
        "max_per_contact_day": MAX_PER_CONTACT_DAY,
        "max_global_day": MAX_GLOBAL_DAY,
        "cooldown_hours": COOLDOWN_HOURS,
        "quiet_hours_start": QUIET_HOURS_START,
        "quiet_hours_end": QUIET_HOURS_END,
        "min_relevance": MIN_RELEVANCE,
        "disabled": _disabled,
        "dry_run": _dry_run,
    }


PROHIBITED_TEMPLATES = [
    r"^\s*oi,?\s*tudo bem\??$",
    r"senti sua falta",
    r"voce e incrivel",
    r"voce e demais",
    r"bom dia(!|\?)?$",
    r"boa tarde(!|\?)?$",
    r"boa noite(!|\?)?$",
]


def is_prohibited_template(text: str) -> bool:
    """Check if text matches a prohibited proactive template."""
    import re
    text_lower = text.lower().strip()
    for pattern in PROHIBITED_TEMPLATES:
        if re.search(pattern, text_lower):
            return True
    return False
