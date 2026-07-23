"""Tests for the LangGraph orchestration pipeline."""
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "test")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    monkeypatch.setenv("INSTANCE", "Jennifer")


def _owner_db():
    fake_db = MagicMock()
    docs = [{
        "owner_phone": "5511966830020",
        "owner_uid": "5511966830020",
        "instance": "Jennifer",
        "name": "Jennifer",
        "status": "active",
    }]

    class _FC:
        def where(self, *_a, **_k):
            return self
        def limit(self, *_a, **_k):
            return self
        def stream(self):
            for item in docs:
                yield MagicMock(to_dict=lambda c=item: c, id=item["instance"])

    fake_db.collection.return_value = _FC()
    return fake_db


def _granted_token(scopes=None):
    return {
        "token": "ya29.fake",
        "refresh_token": "rt",
        "scopes": scopes or [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        "expiry": "9999999999",
    }


class TestAccessGuardianDecision:
    """The guardian function is pure; this covers the three verdicts."""

    def test_allow_when_owner_and_token_present(self):
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        resolution = OwnerResolution(
            owner_phone="5511966830020", owner_uid="5511966830020",
            account_id="Jennifer", instance="Jennifer",
        )
        decision = decide_guardian(
            instance="Jennifer", phone="5511966830020",
            capability="gmail.search_messages",
            resolution=resolution, token_data=_granted_token(),
        )
        assert decision.verdict == "allow"
        assert decision.granted_scopes

    def test_request_oauth_when_token_missing(self):
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        resolution = OwnerResolution(
            owner_phone="5511966830020", owner_uid="5511966830020",
            account_id="Jennifer", instance="Jennifer",
        )
        decision = decide_guardian(
            instance="Jennifer", phone="5511966830020",
            capability="gmail.search_messages",
            resolution=resolution, token_data={},
        )
        assert decision.verdict == "request_oauth"
        assert decision.oauth_link
        assert "oauth/google" in decision.oauth_link

    def test_deny_when_not_owner(self):
        from agent_orchestration.access_guardian import decide_guardian
        from core.owner import OwnerResolution

        resolution = OwnerResolution(
            owner_phone="5511966830020", owner_uid="5511966830020",
            account_id="Jennifer", instance="Jennifer",
        )
        decision = decide_guardian(
            instance="Jennifer", phone="5511999999999",
            capability="gmail.search_messages",
            resolution=resolution, token_data=_granted_token(),
        )
        assert decision.verdict == "deny"
        assert decision.reason == "not_owner"

    def test_deny_when_instance_unresolved(self):
        from agent_orchestration.access_guardian import decide_guardian

        decision = decide_guardian(
            instance="", phone="5511966830020",
            capability="gmail.search_messages",
            resolution=None, token_data={},
        )
        assert decision.verdict == "deny"
        assert decision.reason == "instance_unresolved"

    def test_normalize_capability_maps_correctly(self):
        from agent_orchestration.access_guardian import normalize_capability

        assert normalize_capability("gmail.search_messages") == "gmail.read"
        assert normalize_capability("gmail.send_message") == "gmail.send"
        assert normalize_capability("calendar.list_events") == "calendar.read"
        assert normalize_capability("calendar.create_event") == "calendar.write"
        assert normalize_capability("drive.search_files") == "drive.read"
        assert normalize_capability("drive.upload_file") == "drive.write"
        assert normalize_capability("drive.list_folder") == "drive.read"
        assert normalize_capability("drive.find_omnichannel_atas_folder") == "drive.read"


class TestGraphNodes:
    """Test individual graph nodes in isolation."""

    @pytest.mark.asyncio
    async def test_classify_intent_email(self):
        from agent_orchestration.graph import classify_intent_node

        state = {"text": "leia meus ultimos emails", "instance": "Jennifer", "phone": "5511966830020"}
        out = await classify_intent_node(state)
        assert out["intent"]["is_email"] is True
        assert out["intent"]["is_calendar"] is False
        assert out["intent"]["is_drive"] is False

    @pytest.mark.asyncio
    async def test_classify_intent_calendar(self):
        from agent_orchestration.graph import classify_intent_node

        state = {"text": "quais sao meus compromissos", "instance": "Jennifer", "phone": "5511966830020"}
        out = await classify_intent_node(state)
        assert out["intent"]["is_calendar"] is True

    @pytest.mark.asyncio
    async def test_classify_intent_drive(self):
        from agent_orchestration.graph import classify_intent_node

        state = {"text": "lista os arquivos no drive", "instance": "Jennifer", "phone": "5511966830020"}
        out = await classify_intent_node(state)
        assert out["intent"]["is_drive"] is True

    @pytest.mark.asyncio
    async def test_guard_node_returns_decision_for_owner_with_token(self):
        from agent_orchestration.graph import guard_node
        from core.owner import OwnerResolution

        fake_db = _owner_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                state = {
                    "instance": "Jennifer",
                    "phone": "5511966830020",
                    "text": "leia meus emails",
                    "intent": {"is_email": True, "is_calendar": False, "is_drive": False},
                }
                with patch(
                    "agent_orchestration.access_guardian.get_user_oauth",
                    return_value=_granted_token(),
                ):
                    out = await guard_node(state)

        assert out["guardian_decision"]["verdict"] == "allow"
        assert out["next_agent"] == "manager"

    @pytest.mark.asyncio
    async def test_guard_node_request_oauth_when_token_missing(self):
        from agent_orchestration.graph import guard_node

        fake_db = _owner_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                state = {
                    "instance": "Jennifer",
                    "phone": "5511966830020",
                    "text": "leia meus emails",
                    "intent": {"is_email": True, "is_calendar": False, "is_drive": False},
                }
                with patch("agent_orchestration.access_guardian.get_user_oauth", return_value={}):
                    out = await guard_node(state)

        assert out["guardian_decision"]["verdict"] == "request_oauth"
        assert "oauth/google" in out["guardian_decision"]["oauth_link"]
        assert out["next_agent"] is None

    @pytest.mark.asyncio
    async def test_guard_node_deny_for_non_owner(self):
        from agent_orchestration.graph import guard_node

        fake_db = _owner_db()
        with patch("agent_loader._get_firestore_client", lambda: fake_db):
            with patch("core.owner._get_firestore_client", lambda: fake_db):
                state = {
                    "instance": "Jennifer",
                    "phone": "5511999999999",
                    "text": "leia meus emails",
                    "intent": {"is_email": True, "is_calendar": False, "is_drive": False},
                }
                out = await guard_node(state)

        assert out["guardian_decision"]["verdict"] == "deny"
        assert out["guardian_decision"]["reason"] == "not_owner"

    @pytest.mark.asyncio
    async def test_reply_node_returns_oauth_link_for_request_oauth(self):
        from agent_orchestration.graph import reply_node

        state = {
            "guardian_decision": {
                "verdict": "request_oauth",
                "capability": "gmail.search_messages",
                "oauth_link": "https://agents-runtime-test.../oauth/google?phone=5511966830020",
            }
        }
        out = await reply_node(state)
        assert out["blocked"] is True
        assert "oauth/google" in out["reply"]
        assert "autorize" in out["reply"].lower() or "acesse" in out["reply"].lower()

    @pytest.mark.asyncio
    async def test_reply_node_returns_data_for_allow(self):
        from agent_orchestration.graph import reply_node

        state = {
            "guardian_decision": {"verdict": "allow", "capability": "gmail.search_messages"},
            "prefetch": '[{"id": "msg-1", "subject": "Hello"}]',
        }
        out = await reply_node(state)
        assert out.get("blocked") is not True
        assert "Resultado" in out["reply"]


class TestGraphCompilation:
    """Ensure the graph compiles and exposes the expected nodes."""

    def test_graph_compiles(self):
        from agent_orchestration.graph import build_graph, get_compiled_graph

        graph = build_graph()
        assert graph is not None

        compiled = get_compiled_graph()
        assert compiled is not None

    def test_graph_has_guardian_and_manager_nodes(self):
        from agent_orchestration.graph import build_graph

        graph = build_graph()
        nodes = set()
        for node_id in graph.nodes.keys():
            nodes.add(node_id)
        assert "jennifier" in nodes
        assert "classify_intent" in nodes
        assert "guardian" in nodes
        assert "manager" in nodes
        assert "reply" in nodes