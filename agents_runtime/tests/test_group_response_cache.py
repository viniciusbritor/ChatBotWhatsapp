"""Tests for core/group_response_cache.py."""
import time
from core.group_response_cache import (
    get_cached_group_response,
    set_cached_group_response,
    clear_group_response_cache,
    CACHE_TTL_SEC,
)


def setup_function():
    clear_group_response_cache()


def test_cache_miss_returns_none():
    assert get_cached_group_response("group1", "Qual o horário da reunião?") is None


def test_cache_hit_returns_cached_response():
    set_cached_group_response("group1", "Qual o horário da reunião?", "A reunião é às 15h.")
    # Case and whitespace normalization
    assert get_cached_group_response("group1", "qual o horário da reunião?") == "A reunião é às 15h."


def test_cache_expiry(monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    set_cached_group_response("group1", "pergunta", "resposta")

    # Fast forward past TTL
    monkeypatch.setattr(time, "time", lambda: now + CACHE_TTL_SEC + 1)
    assert get_cached_group_response("group1", "pergunta") is None
