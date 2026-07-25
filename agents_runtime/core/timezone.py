"""Centralized Brazil Time (BRT) timezone constants and helpers.

Harness global: this project runs in Brazil (America/Sao_Paulo).
All datetime operations MUST use the constants and helpers in this
module to avoid timezone bugs. Direct usage of
``timezone(timedelta(hours=-3))`` is forbidden by guardrail (see
``docs/GUARDRAILS.md``).

Semantics:
    BRT          = timezone(timedelta(hours=-3))
    now_brt()    = datetime.now(BRT)  -> aware datetime in BRT
    today_brt()  = date.today() in BRT timezone
    to_brt(dt)   = convert naive or aware datetime to BRT

DO NOT import ``datetime`` and create BRT manually elsewhere. Use this
module so the rule is enforced in one place.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Union

#: Brazil Time (America/Sao_Paulo, UTC-3, no DST since 2019).
BRT: timezone = timezone(timedelta(hours=-3))


def now_brt() -> datetime:
    """Return the current datetime in BRT (timezone-aware)."""
    return datetime.now(BRT)


def today_brt() -> date:
    """Return today's date in BRT (timezone-aware)."""
    return now_brt().date()


def to_brt(value: Union[datetime, None]) -> Union[datetime, None]:
    """Convert a naive or aware datetime to BRT. Returns ``None`` unchanged.

    Naive datetimes are assumed to be UTC (the convention used by
    httpx, requests, and Google API clients).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(BRT)
    return value.astimezone(BRT)


__all__ = ["BRT", "now_brt", "today_brt", "to_brt"]