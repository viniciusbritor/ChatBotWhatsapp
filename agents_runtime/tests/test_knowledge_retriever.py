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
        assert result["decision"] == "no_results"
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