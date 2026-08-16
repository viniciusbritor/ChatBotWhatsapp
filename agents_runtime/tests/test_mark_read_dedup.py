"""Tests for mark_read dedup logic in main.py."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch, AsyncMock

import pytest


@pytest.fixture(autouse=True)
def clear_dedup():
    """Limpa cache dedup entre testes."""
    from main import _MARK_READ_DEDUP
    _MARK_READ_DEDUP.clear()
    yield
    _MARK_READ_DEDUP.clear()


def _envelope(instance="Jennifer", remote_jid="5511966830020@s.whatsapp.net"):
    return {
        "instance": instance,
        "remote_jid": remote_jid,
        "message_id": "abc123",
        "phone": "5511966830020",
    }


def test_first_call_creates_task():
    """Primeira chamada para novo par deve criar task."""
    from main import _schedule_mark_read
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        result = _schedule_mark_read(_envelope())
        assert result == "fake_task"
        mock_task.assert_called_once()


def test_repeat_within_5s_returns_none():
    """Segunda chamada para mesmo par dentro de 5s deve retornar None."""
    from main import _schedule_mark_read
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        r1 = _schedule_mark_read(_envelope())
        time.sleep(0.1)
        r2 = _schedule_mark_read(_envelope())
        assert r1 == "fake_task"
        assert r2 is None
        mock_task.assert_called_once()


def test_different_jid_does_not_dedupe():
    """Par (instance, remote_jid) diferente deve criar nova task."""
    from main import _schedule_mark_read
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        r1 = _schedule_mark_read(_envelope(remote_jid="user1@s.whatsapp.net"))
        r2 = _schedule_mark_read(_envelope(remote_jid="user2@s.whatsapp.net"))
        assert r1 == "fake_task"
        assert r2 == "fake_task"
        # Actually call count should be 2 (different envelopes)
        assert mock_task.call_count == 2


def test_different_instance_does_not_dedupe():
    """Pair (instance, remote_jid) -- instance diferente deve ser allowed."""
    from main import _schedule_mark_read
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        r1 = _schedule_mark_read(_envelope(instance="Jennifer"))
        r2 = _schedule_mark_read(_envelope(instance="Other"))
        assert r1 == "fake_task"
        assert r2 == "fake_task"


def test_dedup_cleans_stale_entries():
    """Entries com mais de 30s devem ser limpos."""
    from main import _MARK_READ_DEDUP, _schedule_mark_read
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        # Simulate old entry
        _MARK_READ_DEDUP["Jennifer:5511966830020@s.whatsapp.net"] = time.monotonic() - 31
        _schedule_mark_read(_envelope())
        # Old entry should be cleaned + new task created
        assert mock_task.call_count == 1


def test_missing_remote_jid_falls_back():
    """Envelope sem remote_jid deve cair na chamada direta (sem dedup)."""
    from main import _schedule_mark_read
    env = _envelope()
    env["remote_jid"] = ""
    with patch("main._schedule_mark_read_task") as mock_task:
        mock_task.return_value = "fake_task"
        result = _schedule_mark_read(env)
        assert result == "fake_task"
        mock_task.assert_called_once()
