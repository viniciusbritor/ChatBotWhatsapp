"""Tests for multi-instance (M1/M2): seed de agentes e resolucao por instancia."""
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestResolveAgentForInstance:
    def test_prefixed_agent_returns_instance_copy(self):
        from agent_loader import resolve_agent_for_instance

        fake = {"agent_id": "maycon__jennifier", "name": "Maycon", "instances": ["maycon", "Maycon"]}
        with patch("agent_loader.get_agent", side_effect=lambda aid: dict(fake) if aid == "maycon__jennifier" else None):
            agent = resolve_agent_for_instance("Maycon", "jennifier")
        assert agent is not None
        assert agent["name"] == "Maycon"

    def test_fallback_to_base_when_no_instance_copy(self):
        from agent_loader import resolve_agent_for_instance

        base = {"agent_id": "jennifier", "name": "Jennifer", "instances": ["jennifer", "Jennifer"]}
        with patch("agent_loader.get_agent", side_effect=lambda aid: dict(base) if aid == "jennifier" else None):
            agent = resolve_agent_for_instance("Desconhecido", "jennifier")
        assert agent is not None
        assert agent["name"] == "Jennifer"

    def test_none_when_neither_exists(self):
        from agent_loader import resolve_agent_for_instance

        with patch("agent_loader.get_agent", return_value=None):
            agent = resolve_agent_for_instance("X", "nao-existe")
        assert agent is None


class TestInstanceEndpoints:
    def setup_method(self):
        from _pytest.monkeypatch import MonkeyPatch

        self._mp = MonkeyPatch()
        self._mp.setenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "test-sa-secret")
        from main import app

        self.client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        self.headers = {"Authorization": "Bearer test-sa-secret"}

    def teardown_method(self):
        self._mp.undo()

    def test_seed_copies_agents_with_prefix(self):

        class FakeDoc:
            def __init__(self, exists=True):
                self._exists = exists

            def exists(self):
                return self._exists

        class FakeRef:
            def __init__(self):
                self._data = {}

            def get(self):
                return FakeDoc(True)

            def set(self, data, merge=False):
                self._data.update(data)
                return None

            def update(self, data):
                self._data.update(data)
                return None

        class FakeBatch:
            def __init__(self):
                self.ops = []

            def set(self, ref, data, merge=False):
                self.ops.append(data)
                return self

            def commit(self):
                return None

        class FakeClient:
            def __init__(self):
                self._docs = {}

            def collection(self, name):
                return self

            def document(self, doc_id):
                return FakeRef()

            def batch(self):
                return FakeBatch()

        fake_agents = [
            {"agent_id": "jennifier", "name": "Jennifer", "role": "orchestrator", "instances": ["jennifer"]},
            {"agent_id": "manager-calendar", "name": "Calendar", "role": "manager", "instances": ["jennifer"]},
        ]
        fake_client = FakeClient()
        with patch("agent_loader.list_agents", return_value=fake_agents), \
             patch("agent_loader._get_firestore_client", return_value=fake_client):
            resp = self.client.post("/admin/instances/maycon/seed", headers=self.headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["agents_copied"] == 2

    def test_create_instance_validates_input(self):
        resp = self.client.post(
            "/admin/instances",
            json={"name": "", "owner_phone": ""},
            headers=self.headers,
        )
        assert resp.status_code == 422


class TestJenniferPipelinePreserved:
    def test_jennifer_still_uses_base_agent(self):
        from agent_loader import resolve_agent_for_instance

        base = {"agent_id": "jennifier", "name": "Jennifer", "role": "orchestrator"}
        with patch("agent_loader.get_agent", side_effect=lambda aid: dict(base) if aid == "jennifier" else None):
            agent = resolve_agent_for_instance("Jennifer", "jennifier")
        assert agent["name"] == "Jennifer"  # Jennifer intacta
