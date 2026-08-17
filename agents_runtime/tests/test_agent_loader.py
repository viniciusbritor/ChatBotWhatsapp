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

    def test_lookup_portal_profile_does_not_approve(self):
        """GUARDRAIL §0.7 (16/08/2026): _lookup_portal_profile_for_phone_or_name
        APENAS enriquece nome/picture/email. NAO seta role nem is_approved.
        Antes do fix, encontrar 'Rafael Oliveira' no Portal Coherence users/
        silenciosamente setava is_approved=True (Vetor #2 do incidente 16/08).
        """
        from unittest.mock import MagicMock
        from agent_loader import _lookup_portal_profile_for_phone_or_name

        db = MagicMock()
        # users/rafadesouzaoliveira@gmail.com existe com global_role=analyst
        portal_doc = MagicMock()
        portal_doc.exists = True
        portal_doc.to_dict.return_value = {
            "name": "Rafael Oliveira",
            "email": "rafadesouzaoliveira@gmail.com",
            "global_role": "analyst",
            "picture": "http://example.com/rafael.jpg",
        }

        call_count = {"users": 0, "collection": 0}

        def collection_router(name):
            call_count["collection"] += 1
            coll = MagicMock()
            if name == "users":
                coll.document.return_value.get.return_value = portal_doc
            return coll

        db.collection.side_effect = collection_router

        with patch("agent_loader._get_firestore_client", return_value=db):
            result = _lookup_portal_profile_for_phone_or_name(
                db,
                "5521984843235",
                name="",
                email="rafadesouzaoliveira@gmail.com",
            )

        # Deve retornar dados de enriquecimento
        assert result.get("name") == "Rafael Oliveira"
        assert result.get("email") == "rafadesouzaoliveira@gmail.com"
        assert result.get("picture") == "http://example.com/rafael.jpg"
        # NAO pode setar role ou is_approved
        assert "role" not in result
        assert "is_approved" not in result

    def test_lookup_portal_profile_by_name_does_not_approve(self):
        """GUARDRAIL §0.7: match por NOME no Portal Coherence NAO aprova.

        Antes do fix 1.2, a busca por substring (ex: 'Rafael' em 'Rafael
        Oliveira') silenciosamente setava is_approved=True.
        """
        from unittest.mock import MagicMock
        from agent_loader import _lookup_portal_profile_for_phone_or_name

        db = MagicMock()
        portal_doc = MagicMock()
        portal_doc.id = "rafadesouzaoliveira@gmail.com"
        portal_doc.to_dict.return_value = {
            "name": "Rafael Oliveira",
            "email": "rafadesouzaoliveira@gmail.com",
            "global_role": "analyst",
        }

        def collection_router(name):
            coll = MagicMock()
            if name == "users":
                # Sem doc.email == email_clean -> cai no loop por nome
                coll.document.return_value.get.return_value = MagicMock(exists=False)
                coll.stream.return_value = iter([portal_doc])
            return coll

        db.collection.side_effect = collection_router

        with patch("agent_loader._get_firestore_client", return_value=db):
            result = _lookup_portal_profile_for_phone_or_name(
                db,
                "5511999999999",  # phone novo, sem email
                name="Rafael Oliveira",
                email="",
            )

        # Encontrou match por nome -> enriqueceu
        assert result.get("name") == "Rafael Oliveira"
        # NAO aprova
        assert "role" not in result
        assert "is_approved" not in result

