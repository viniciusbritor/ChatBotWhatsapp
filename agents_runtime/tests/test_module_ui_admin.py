"""Testes do portal Agentes Omnichannel e do endpoint /admin/status.

Cobre:
- render_dashboard() nao quebra com escaping
- /admin/status retorna llm_provider=deepseek-v4-flash, sem fallback LLM
- /admin/knowledge agrupa por source_title
- /admin/knowledge/{source_title} retorna chunks + metadados
- UI module embute botões Editar/Excluir para agentes
- UI tem handler de modal para visualização de documento
"""
from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock


os.environ.setdefault("GCP_PROJECT", "test-project")


class _AuthFixture:
    def setup_method(self, method):
        from _pytest.monkeypatch import MonkeyPatch

        self._mp = MonkeyPatch()
        self._mp.setenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "test-sa-secret")

    def teardown_method(self, method):
        self._mp.undo()


class TestRenderDashboard:
    def setup_method(self):
        from core.module_ui import render_dashboard

        self.render_dashboard = render_dashboard

    def test_returns_html_with_doctype(self):
        html = self.render_dashboard("abc1234", "2026-07-30T00:00:00Z")
        assert html.startswith("<!DOCTYPE html>")
        assert "Agentes Omnichannel" in html
        assert "abc1234" in html
        assert "2026-07-30T00:00:00Z" in html

    def test_has_agent_edit_button_handler(self):
        html = self.render_dashboard("deadbee", "local")
        # Rewrite usa agentEdit / agentDel como funções de CRUD
        assert "agentEdit" in html
        assert "agentDel" in html

    def test_has_knowledge_view_handler(self):
        html = self.render_dashboard("deadbee", "local")
        # Rewrite usa delKnowledge para ações na aba Conhecimento
        assert "delKnowledge" in html
        assert "renderKnowledge" in html

    def test_has_status_section_reflecting_deepseek(self):
        html = self.render_dashboard("deadbee", "local")
        # deepseek-v4-flash vem da API em runtime, não fica hardcoded no HTML
        # Verifica que a aba Status existe (renderStatus) e o badge também
        assert "renderStatus" in html
        assert 'id="runtime-badge"' in html


class TestAdminStatusEndpoint(_AuthFixture):
    def setup_method(self):
        super().setup_method(None)
        from main import app

        self.client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        self.headers = {"Authorization": "Bearer test-sa-secret"}

    def test_admin_status_returns_deepseek_no_fallback(self):
        with patch("main._short_sha", return_value="abc1234"):
            resp = self.client.get("/admin/status", headers=self.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        kpi_labels = {kpi["label"] for kpi in body.get("kpis", [])}
        assert "stt_primary" not in kpi_labels
        assert "stt_fallback" not in kpi_labels
        assert "llm_provider" in kpi_labels
        llm = body.get("llm", {})
        assert llm.get("provider") == "deepseek"
        assert llm.get("model") == "deepseek-v4-flash"
        assert llm.get("cascade") is False

    def test_admin_status_runtime_ok_default(self):
        with patch("main._short_sha", return_value="abc1234"):
            resp = self.client.get("/admin/status", headers=self.headers)
        body = resp.json()
        assert "runtime_ok" in body
        assert "agents_summary" in body
        assert "counts" in body["agents_summary"]


class TestAdminAgentsEndpoints(_AuthFixture):
    def setup_method(self):
        super().setup_method(None)
        from main import app

        self.client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        self.headers = {"Authorization": "Bearer test-sa-secret"}

    def test_admin_agents_get_returns_404_when_missing(self):
        with patch("agent_loader.get_agent", return_value=None):
            resp = self.client.get("/admin/agents/unknown-id", headers=self.headers)
        assert resp.status_code == 404

    def test_admin_agents_post_upserts(self):
        with patch("main.upsert_agent", return_value=True) as mock_upsert:
            resp = self.client.post(
                "/admin/agents",
                json={"id": "agent-test-1", "name": "Test", "role": "specialist", "model": "deepseek-v4-flash"},
                headers=self.headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["upserted"] is True
        assert mock_upsert.call_count == 1

    def test_admin_agents_delete_returns_500_on_failure(self):
        with patch("main.delete_agent", return_value=False):
            resp = self.client.delete("/admin/agents/agent-x", headers=self.headers)
        assert resp.status_code == 500

    def test_admin_skills_delete_success(self):
        with patch("main.delete_skill", return_value=True):
            resp = self.client.delete("/admin/skills/skill-test-1", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_admin_tools_delete_success(self):
        with patch("main.delete_tool", return_value=True):
            resp = self.client.delete("/admin/tools/tool-test-1", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_admin_skills_get_returns_skill(self):
        fake_skill = {"skill_id": "skill-x", "name": "Skill X", "system_prompt": "prompt da skill"}
        with patch("main.get_skill", return_value=fake_skill):
            resp = self.client.get("/admin/skills/skill-x", headers=self.headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["skill"]["system_prompt"] == "prompt da skill"

    def test_admin_skills_get_404_when_missing(self):
        with patch("main.get_skill", return_value=None):
            resp = self.client.get("/admin/skills/skill-nao-existe", headers=self.headers)
        assert resp.status_code == 404

    def test_admin_tools_get_returns_tool(self):
        fake_tool = {"tool_id": "tool-y", "name": "Tool Y", "system_prompt": "prompt da tool"}
        with patch("main.get_tool_meta", return_value=fake_tool):
            resp = self.client.get("/admin/tools/tool-y", headers=self.headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["tool"]["system_prompt"] == "prompt da tool"

    def test_admin_tools_get_404_when_missing(self):
        with patch("main.get_tool_meta", return_value=None):
            resp = self.client.get("/admin/tools/tool-nao-existe", headers=self.headers)
        assert resp.status_code == 404

    def test_admin_knowledge_user_post_indexes_private(self):
        from unittest.mock import AsyncMock

        fake_result = {
            "doc_ids": ["sha-abc"], "chunks": 2, "chunks_indexed": 2,
            "truncated": False, "collection": "knowledge-database",
        }
        with patch("core.rag.index_private_document", AsyncMock(return_value=fake_result)) as mock_index:
            resp = self.client.post(
                "/admin/knowledge/user",
                json={"phone": "5511966830020", "titulo": "meu-doc", "conteudo": "texto longo para indexar"},
                headers=self.headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["chunks_indexed"] == 2
        assert mock_index.call_count == 1
        call_kwargs = mock_index.call_args.kwargs
        assert call_kwargs["phone"] == "5511966830020"
        assert call_kwargs["source_title"] == "meu-doc"

    def test_admin_knowledge_user_post_requires_phone_and_fields(self):
        resp = self.client.post(
            "/admin/knowledge/user",
            json={"titulo": "sem phone", "conteudo": "x"},
            headers=self.headers,
        )
        assert resp.status_code == 422


class TestAdminKnowledgeGrouping(_AuthFixture):
    def setup_method(self):
        super().setup_method(None)
        from main import app

        self.client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        self.headers = {"Authorization": "Bearer test-sa-secret"}

    def _fake_firestore_with_chunks(self, plain_collection):
        class FakeDoc:
            def __init__(self, doc_id, data):
                self.id = doc_id
                self._data = data

            def to_dict(self):
                return self._data

        class FakeCollection:
            def __init__(self, name, docs):
                self._name = name
                self._docs = list(docs)

            def limit(self, n):
                return self

            def stream(self):
                for doc in list(self._docs):
                    yield doc

            def where(self, field, op, value):
                filtered = [doc for doc in self._docs if doc.to_dict().get(field) == value]
                return FakeCollection(self._name, filtered)

            def document(self, doc_id):
                return self._docs[0] if self._docs else None

        class FakeBatch:
            def __init__(self):
                self.ops = []

            def set(self, ref, data, merge=False):
                self.ops.append((ref, data))
                return self

            def commit(self):
                return None

        class FakeClient:
            def __init__(self, by_collection):
                self._by_collection = by_collection

            def collection(self, name):
                return FakeCollection(name, self._by_collection.get(name, []))

        chunks = [
            FakeDoc(f"sha-{i}", {
                "source_title": "dissertacao.pdf",
                "chunk_index": i,
                "text_content": f"chunk {i} do documento",
                "class": "documento_pessoal",
                "group": "academico",
                "theme": "machine_learning",
                "owner_hash": "a" * 32,
                "language": "pt-BR",
                "created_at": "2026-07-30T00:00:00-03:00",
            })
            for i in range(3)
        ]
        client = FakeClient({plain_collection: chunks})
        return client

    def test_admin_knowledge_groups_by_source_title(self):
        fake = self._fake_firestore_with_chunks("knowledge-database")
        with patch("agent_loader._get_firestore_client", return_value=fake):
            resp = self.client.get("/admin/knowledge?limit=10", headers=self.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        docs = body.get("documents", [])
        assert len(docs) == 1
        assert docs[0]["title"] == "dissertacao.pdf"
        assert docs[0]["chunk_count"] == 3
        assert docs[0]["klass"] == "documento_pessoal"
        assert docs[0]["group"] == "academico"

    def test_admin_knowledge_detail_returns_chunks(self):
        fake = self._fake_firestore_with_chunks("knowledge-database")
        with patch("agent_loader._get_firestore_client", return_value=fake):
            resp = self.client.get("/admin/knowledge/dissertacao.pdf", headers=self.headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        doc = body["document"]
        assert doc["chunk_count"] == 3
        assert len(doc["chunks"]) == 3
        assert doc["chunks"][0]["chunk_index"] == 0
        assert "chunk 0" in doc["chunks"][0]["text"]

    def test_admin_knowledge_detail_404_when_missing(self):
        fake = self._fake_firestore_with_chunks("knowledge-database")
        with patch("agent_loader._get_firestore_client", return_value=fake):
            resp = self.client.get("/admin/knowledge/inexistente.pdf", headers=self.headers)
        assert resp.status_code == 404


class TestEnrichUserConnections:
    def test_google_scopes_derived(self):
        from main import _enrich_user_connections

        user = {
            "phone": "5511966830020",
            "google_oauth_token": {
                "scopes": [
                    "https://www.googleapis.com/auth/calendar",
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/drive",
                ],
                "email": "viniciusbritor@gmail.com",
            },
        }
        import asyncio

        asyncio.run(_enrich_user_connections(user))
        assert user["google"]["connected"] is True
        assert user["google"]["email"] == "viniciusbritor@gmail.com"
        svc_by_id = {s["id"]: s["connected"] for s in user["google"]["services"]}
        assert svc_by_id["calendar"] is True
        assert svc_by_id["gmail"] is True
        assert svc_by_id["drive"] is True
        assert svc_by_id["tasks"] is False  # nao autorizado ainda

    def test_google_sem_token(self):
        from main import _enrich_user_connections

        user = {"phone": "5511999999999"}
        import asyncio

        asyncio.run(_enrich_user_connections(user))
        assert user["google"]["connected"] is False
        assert len(user["google"]["services"]) >= 5  # 5 servicos apos remover Google Photos  # lista dinâmica completa

    def test_composio_status_merged(self):
        from main import _enrich_user_connections

        fake_status = {
            "phone": "5511966830020",
            "apps": {"youtube": {"connected": True, "name": "YouTube"}, "linkedin": {"connected": False, "name": "LinkedIn"}},
        }
        import asyncio

        with patch("tools.composio_connect.get_status", AsyncMock(return_value=fake_status)):
            user = {"phone": "5511966830020"}
            asyncio.run(_enrich_user_connections(user))
        svc_by_id = {s["id"]: s["connected"] for s in user["composio"]["services"]}
        assert svc_by_id["youtube"] is True
        assert svc_by_id["linkedin"] is False


class TestOnboardingEndpoints(_AuthFixture):
    def setup_method(self):
        super().setup_method(None)
        from main import app

        self.client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)

    def test_conectar_page_public(self):
        from core.magic_link import generate_magic_link_token

        token = generate_magic_link_token("5511966830020")
        with patch("agent_loader.get_user", return_value=None):
            resp = self.client.get(f"/a/5511966830020/conectar?token={token}")
        assert resp.status_code == 200, resp.text
        assert "Jennifer - Conectar Contas" in resp.text
        assert "Conectar Apps de Trabalho" in resp.text

    def test_conectar_page_requires_valid_token(self):
        resp = self.client.get("/a/5511966830020/conectar")
        assert resp.status_code == 403, resp.text

        resp = self.client.get("/a/5511966830020/conectar?token=ml.invalido.forjado")
        assert resp.status_code == 403, resp.text

    def test_conectar_page_rejects_phone_mismatch(self):
        from core.magic_link import generate_magic_link_token

        token = generate_magic_link_token("5511999999999")
        resp = self.client.get(f"/a/5511966830020/conectar?token={token}")
        assert resp.status_code == 403, resp.text

    def test_composio_endpoint_public_returns_links(self):
        fake_result = {
            "links": [
                {"toolkit": "youtube", "status": "pending", "connect_url": "https://composio/youtube"},
                {"toolkit": "linkedin", "status": "connected", "connect_url": None},
            ],
            "already_connected": 1,
            "total": 2,
        }
        with patch("tools.composio_connect.connect_all", AsyncMock(return_value=fake_result)):
            resp = self.client.post("/a/5511966830020/composio")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["links"]) == 1
        assert body["links"][0]["toolkit"] == "youtube"
        assert body["links"][0]["url"] == "https://composio/youtube"
        assert body["already_connected"] == 1

    def test_onboarding_url_helper(self):
        from orchestrator import _onboarding_url

        url = _onboarding_url("+5511966830020")
        assert "token=ml." in url
