"""Tests for agent_orchestration/knowledge_retriever.py (Fase H)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRagHeuristic:
    def test_detects_rag_keyword(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("me diz o que memorizei do pdf")
        assert _looks_like_rag_query("tem algo na base de conhecimento sobre isso?")
        assert _looks_like_rag_query("o documento que salvamos ontem")
        assert _looks_like_rag_query("qual era o conteudo do pdf que mandei?")

    def test_does_not_detect_greeting(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert not _looks_like_rag_query("oi")
        assert not _looks_like_rag_query("obrigado")

    def test_empty_returns_false(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert not _looks_like_rag_query("")


class TestRetrievePrivate:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results_from_private_collection(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        fake_chunks = [
            {
                "text": "Chunk A",
                "score": 0.9,
                "source": "doc.pdf",
            }
        ]
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={
                "results": fake_chunks,
                "owner_hash": "abc",
            }),
        ):
            result = await retrieve(envelope, "o que tem no pdf?", limit=3, min_score=0.3)
        assert result["decision"] == "private"
        assert result["count"] == 1
        assert result["results"][0]["source"] == "doc.pdf"

    @pytest.mark.asyncio
    async def test_retrieve_private_no_results(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": [], "owner_hash": "abc"}),
        ):
            result = await retrieve(envelope, "irrelevante", limit=3, min_score=0.5)
        assert result["decision"] == "needs_clarification"
        assert result["count"] == 0


class TestRetrieveGroup:
    @pytest.mark.asyncio
    async def test_group_member_returns_results(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = True
        member_doc.to_dict.return_value = {"is_active": True}
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            with patch(
                "agent_orchestration.knowledge_retriever.search_group_knowledge",
                AsyncMock(return_value={
                    "results": [{"text": "x", "score": 0.7, "source_name": "ata.pdf"}],
                    "count": 1,
                }),
            ):
                result = await retrieve(envelope, "qual a ata?", limit=3, min_score=0.5)
        assert result["decision"] == "group"
        assert result["count"] == 1
        assert result["scope"] == "group"

    @pytest.mark.asyncio
    async def test_group_non_member_denied(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = False
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            result = await retrieve(envelope, "qualquer coisa", limit=3, min_score=0.5)
        assert result["decision"] == "denied"
        assert result["reason"] == "not_member"


class TestCrossScopePrivateInGroup:
    @pytest.mark.asyncio
    async def test_private_match_in_group_creates_pending_share(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = True
        member_doc.to_dict.return_value = {"is_active": True}
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            with patch(
                "agent_orchestration.knowledge_retriever.search_group_knowledge",
                AsyncMock(return_value={"results": [], "count": 0}),
            ):
                with patch(
                    "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                    AsyncMock(return_value={
                        "results": [{"text": "p", "score": 0.8, "source": "privado.pdf"}],
                        "owner_hash": "abc",
                    }),
                ):
                    with patch(
                        "core.pending_actions.set_pending_action",
                        AsyncMock(return_value={"action_type": "share_private_knowledge_in_group"}),
                    ) as mock_set:
                        result = await retrieve(envelope, "doc privado", limit=3, min_score=0.5)
        assert result["decision"] == "group_private_share_pending"
        assert result["needs_share_prompt"] is True
        assert mock_set.called
        assert mock_set.call_args.args[1] == "share_private_knowledge_in_group"


class TestSharePendingConsume:
    @pytest.mark.asyncio
    async def test_consume_returns_action(self):
        from agent_orchestration import knowledge_retriever

        action = {"action_type": "share_private_knowledge_in_group", "payload": {}}
        with patch(
            "core.pending_actions.consume_pending_action",
            AsyncMock(return_value=action),
        ):
            result = await knowledge_retriever.share_pending_action_consume("5511999")
        assert result["action_type"] == "share_private_knowledge_in_group"


class TestRetrievalMetrics:
    def test_dataclass_serializes(self):
        from agent_orchestration.knowledge_retriever import RetrievalMetrics

        m = RetrievalMetrics(
            query_hash="abc",
            scope="private",
            decision="private",
            min_score=0.7,
            candidates=3,
            returned=3,
        )
        data = m.to_dict()
        assert data["query_hash"] == "abc"
        assert data["scope"] == "private"
        assert data["decision"] == "private"
        assert data["min_score"] == 0.7
        assert data["candidates"] == 3
        assert data["classes"] == []
        assert data["sources"] == []

    def test_summarize_results_empty(self):
        from agent_orchestration.knowledge_retriever import _summarize_results

        s = _summarize_results([])
        assert s["classes"] == []
        assert s["sources"] == []
        assert s["top_score"] == 0.0
        assert s["avg_score"] == 0.0

    def test_summarize_results_with_data(self):
        from agent_orchestration.knowledge_retriever import _summarize_results

        chunks = [
            {"class": "legal", "source": "cdc.pdf", "score": 0.9},
            {"class": "legal", "source": "cdc.pdf", "score": 0.7},
            {"class": "outros", "source": "x.pdf", "score": 0.5},
        ]
        s = _summarize_results(chunks)
        assert s["classes"] == ["legal", "legal", "outros"]
        assert s["sources"] == ["cdc.pdf", "cdc.pdf", "x.pdf"]
        assert s["top_score"] == 0.9
        assert abs(s["avg_score"] - 0.7) < 1e-9

    @pytest.mark.asyncio
    async def test_retrieve_emits_metrics_log(self, caplog):
        from agent_orchestration import knowledge_retriever

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        chunks = [
            {"text": "c1", "score": 0.9, "source": "cdc.pdf", "class": "legal"},
            {"text": "c2", "score": 0.7, "source": "cdc.pdf", "class": "legal"},
        ]
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": chunks, "owner_hash": "abc"}),
        ):
            caplog.set_level("INFO")
            await knowledge_retriever.retrieve(envelope, "cdc test")
        # Look for our custom log record
        retrieval_logs = [
            r for r in caplog.records
            if getattr(r, "event_name", "") == "retrieval_quality"
        ]
        assert retrieval_logs, "expected retrieval_quality log"
        rec = retrieval_logs[-1]
        assert rec.decision == "private"
        assert rec.returned == 2
        assert rec.top_score == 0.9
        assert rec.classes == ["legal", "legal"]


class TestRetrieveWithHints:
    @pytest.mark.asyncio
    async def test_extracts_source_title_from_query(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = _extract_query_hints("o que tem no cdc-portugues-2013.pdf sobre saude?")
        assert hints.get("source_title") == "cdc-portugues-2013.pdf"

    @pytest.mark.asyncio
    async def test_extracts_class_hint(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = _extract_query_hints("tem algum edital de licitacao?")
        assert hints.get("class") == "edital"

    @pytest.mark.asyncio
    async def test_no_hints_when_unrelated(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = _extract_query_hints("oi, tudo bem?")
        assert "source_title" not in hints
        assert "class" not in hints

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        # Mock that respects k=10 by truncating client-side.
        def fake_search(**kwargs):
            k = kwargs.get("k", 10)
            return {"results": [{"text": f"c{i}", "score": 0.9, "source": "x.pdf"} for i in range(k)], "owner_hash": "abc"}
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(side_effect=fake_search),
        ):
            result = await retrieve(envelope, "qualquer coisa")
        # search_legal_knowledge is called with k=10 (default), so the mock
        # returns 10 results. We verify the k parameter is propagated.
        assert result["count"] == 10
        assert len(result["results"]) == 10

    @pytest.mark.asyncio
    async def test_no_results_returns_clarification(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": [], "owner_hash": "abc"}),
        ):
            result = await retrieve(envelope, "qualquer coisa")
        assert result["decision"] == "needs_clarification"
        assert result["needs_clarification"] is True
        assert "Não encontrei" in result["clarification_prompt"]