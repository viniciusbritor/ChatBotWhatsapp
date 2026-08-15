"""Tests for agent_loader module."""
from unittest.mock import patch


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


class TestAtomicReload:
    def setup_method(self):
        from agent_loader import _agents_cache, _skills_cache, _tools_cache

        _agents_cache.clear()
        _skills_cache.clear()
        _tools_cache.clear()

    def test_reload_replaces_snapshot_and_removes_deleted_agent(self):
        from agent_loader import _agents_cache, _load_all

        _agents_cache["removed"] = {"id": "removed"}
        with patch(
            "agent_loader._read_collection",
            side_effect=[
                {"jennifier": {"id": "jennifier"}},
                {"skill": {"id": "skill"}},
                {"tool": {"id": "tool"}},
            ],
        ):
            success = _load_all()

        assert success is True
        assert "removed" not in _agents_cache
        assert "jennifier" in _agents_cache

    def test_partial_reload_preserves_last_valid_snapshot(self):
        from agent_loader import _agents_cache, _load_all

        _agents_cache["stable"] = {"id": "stable"}
        with patch(
            "agent_loader._read_collection",
            side_effect=[{"new": {"id": "new"}}, None, {}],
        ):
            success = _load_all()

        assert success is False
        assert list(_agents_cache) == ["stable"]

    def test_get_agent_returns_copy(self):
        from agent_loader import _agents_cache, get_agent

        _agents_cache["jennifier"] = {"id": "jennifier", "system_prompt": "original"}
        result = get_agent("jennifier")
        result["system_prompt"] = "changed"

        assert _agents_cache["jennifier"]["system_prompt"] == "original"

    def test_partial_seed_fills_only_missing_collections(self):
        from agent_loader import _agents_cache, _skills_cache, _tools_cache, seed_default_data

        _agents_cache["custom"] = {"id": "custom"}
        with patch("agent_loader._get_firestore_client", return_value=None):
            seed_default_data()

        assert list(_agents_cache) == ["custom"]
        assert len(_skills_cache) > 0
        assert len(_tools_cache) > 0

    def test_cache_stats_expose_reload_generation(self):
        from agent_loader import get_cache_stats

        stats = get_cache_stats()
        assert "config_generation" in stats
        assert "last_reload_attempt_at" in stats
        assert "last_reload_error" in stats


class TestEnsureUserRegistered:
    def test_ensure_user_registered_creates_new(self):
        from unittest.mock import MagicMock
        from agent_loader import ensure_user_registered

        db = MagicMock()
        doc_ref = MagicMock()
        doc_snap = MagicMock()
        doc_snap.exists = False
        doc_ref.get.return_value = doc_snap
        db.collection.return_value.document.return_value = doc_ref

        with patch("agent_loader._get_firestore_client", return_value=db):
            ok = ensure_user_registered("5511988776655", sender_name="João Silva", instance="jennifer")
            assert ok is True
            doc_ref.set.assert_called_once()
            args, kwargs = doc_ref.set.call_args
            payload = args[0]
            assert payload["phone"] == "5511988776655"
            assert payload["name"] == "João Silva"
            assert payload["role"] == "guest"
            assert payload["is_approved"] is False

    def test_ensure_user_registered_updates_existing_name(self):
        from unittest.mock import MagicMock
        from agent_loader import ensure_user_registered

        db = MagicMock()
        doc_ref = MagicMock()
        doc_snap = MagicMock()
        doc_snap.exists = True
        doc_snap.to_dict.return_value = {"phone": "5511988776655"}  # sem nome
        doc_ref.get.return_value = doc_snap
        db.collection.return_value.document.return_value = doc_ref

        with patch("agent_loader._get_firestore_client", return_value=db):
            ok = ensure_user_registered("5511988776655", sender_name="Maria Santos")
            assert ok is True
            doc_ref.set.assert_called_once()
            args, kwargs = doc_ref.set.call_args
            assert args[0]["name"] == "Maria Santos"
            assert kwargs.get("merge") is True

