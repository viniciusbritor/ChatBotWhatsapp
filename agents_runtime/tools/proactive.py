"""Proactive helpers (re-exports from core)."""
from core.proactive_gate import (
    check,
    is_dry_run,
    record_sent,
    set_kill_switch,
    get_config,
    is_prohibited_template,
)

__all__ = ["check", "is_dry_run", "record_sent", "set_kill_switch", "get_config", "is_prohibited_template"]
