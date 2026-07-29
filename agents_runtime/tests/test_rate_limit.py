"""Tests for in-process rate limiter (F4d.9)."""
import time

from core import rate_limit
from core.rate_limit import is_rate_limited


def setup_function(_):
    rate_limit.reset()


def test_first_message_passes():
    limited, remaining = is_rate_limited("+5511966830020")
    assert limited is False
    assert remaining == rate_limit.MAX_PER_MINUTE - 1


def test_consecutive_messages_increment():
    for i in range(5):
        limited, remaining = is_rate_limited("+5511966830020")
        assert limited is False
        assert remaining == rate_limit.MAX_PER_MINUTE - i - 1


def test_overflow_blocks_next_message():
    rate_limit.reset("+5511966830020")
    for _ in range(rate_limit.MAX_PER_MINUTE):
        is_rate_limited("+5511966830020")
    limited, remaining = is_rate_limited("+5511966830020")
    assert limited is True
    assert remaining == 0


def test_different_phones_have_independent_buckets():
    for _ in range(rate_limit.MAX_PER_MINUTE):
        is_rate_limited("+5511966830020")
    assert is_rate_limited("+5511966830020")[0] is True
    assert is_rate_limited("+5511966830021")[0] is False


def test_window_expires():
    rate_limit.reset("+5511966830020")
    for _ in range(rate_limit.MAX_PER_MINUTE):
        is_rate_limited("+5511966830020")
    assert is_rate_limited("+5511966830020")[0] is True
    rate_limit._buckets["+5511966830020"].clear()
    assert is_rate_limited("+5511966830020")[0] is False


def test_empty_phone_passes():
    assert is_rate_limited("")[0] is False


def test_reset_clears_all():
    is_rate_limited("+5511966830020")
    is_rate_limited("+5511966830021")
    rate_limit.reset()
    assert rate_limit._buckets == {}