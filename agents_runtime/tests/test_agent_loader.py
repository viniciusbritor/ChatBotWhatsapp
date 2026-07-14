"""Tests for agent_loader module."""
import pytest
import time
from unittest.mock import patch, MagicMock


class TestCacheStats:
    def test_initial_stats(self):
        from agent_loader import get_cache_stats
        stats = get_cache_stats()
        assert "agents" in stats
        assert "skills" in stats
        assert "tools" in stats
        assert "poll_interval_sec" in stats


class TestGetAgent:
    def test_returns_none_if_not_loaded(self):
        from agent_loader import get_agent, _agents_cache
        _agents_cache.clear()
        assert get_agent("nonexistent") is None


class TestForceReload:
    def test_force_reload_no_firestore(self):
        from agent_loader import force_reload, _agents_cache, _skills_cache, _tools_cache
        _agents_cache.clear()
        _skills_cache.clear()
        _tools_cache.clear()
        with patch("agent_loader._get_firestore_client", return_value=None):
            force_reload()
        assert isinstance(_agents_cache, dict)


class TestStartStopLoader:
    def test_start_and_stop_does_not_crash(self):
        from agent_loader import start_loader, stop_loader, _loader_thread
        _loader_thread_local = _loader_thread
        start_loader()
        start_loader()
        stop_loader()
        stop_loader()
        assert True

    def test_stop_idempotent(self):
        from agent_loader import stop_loader
        stop_loader()
        stop_loader()
        assert True


class TestListAgents:
    def test_empty(self):
        from agent_loader import list_agents, _agents_cache
        _agents_cache.clear()
        assert list_agents() == []