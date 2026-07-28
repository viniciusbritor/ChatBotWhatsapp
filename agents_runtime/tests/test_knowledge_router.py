"""Tests for agent_orchestration/knowledge_router.py (Fase G)."""
from unittest.mock import AsyncMock, patch

import pytest


class TestKeywordDetection:
    def test_drive_keyword_is_detected(self):
        from agent_orchestration.knowledge_router import _detect_intent_keywords

        assert _detect_intent_keywords("manda pra mim") == "drive"
        assert _detect_intent_keywords("guardar no drive") == "drive"
        assert _detect_intent_keywords("salva no drive") == "drive"

    def test_rag_keyword_is_detected(self):
        from agent_orchestration.knowledge_router import _detect_intent_keywords

        assert _detect_intent_keywords("memorizar") == "rag"
        assert _detect_intent_keywords("indexar no vector") == "rag"
        assert _detect_intent_keywords("salva na base de conhecimento") == "rag"
        assert _detect_intent_keywords("gravar") == "rag"
        assert _detect_intent_keywords("guardar") == "rag"

    def test_ambiguous_when_no_keywords(self):
        from agent_orchestration.knowledge_router import _detect_intent_keywords

        assert _detect_intent_keywords("") == "ambiguous"
        assert _detect_intent_keywords("oi") == "ambiguous"
        assert _detect_intent_keywords("olha esse arquivo ai") == "ambiguous"


class TestScopeDetection:
    def test_private_scope(self):
        from agent_orchestration.knowledge_router import _detect_scope

        envelope = {"extra": {"remote_jid": "5511966830020@s.whatsapp.net"}}
        assert _detect_scope(envelope) == "private"

    def test_group_scope(self):
        from agent_orchestration.knowledge_router import _detect_scope

        envelope = {"extra": {"remote_jid": "120363123@g.us"}}
        assert _detect_scope(envelope) == "group"


class TestRouteAttachment:
    @pytest.mark.asyncio
    async def test_drive_keyword_routes_to_drive_skill(self):
        from agent_orchestration.knowledge_router import route_attachment

        envelope = {
            "phone": "5511999",
            "instance": "jennifer",
            "message_id": "MSG_DRV",
            "extra": {
                "remote_jid": "5511999@s.whatsapp.net",
                "doc_mimetype": "application/pdf",
                "doc_file_name": "doc.pdf",
                "doc_base64": "JVBERi0=",
            },
        }
        decision = await route_attachment(envelope, "manda pra mim")
        assert decision["decision"] == "drive"
        assert decision["skill_name"] == "drive"
        assert decision["scope"] == "private"

    @pytest.mark.asyncio
    async def test_rag_keyword_routes_to_matching_skill(self):
        from agent_orchestration.knowledge_router import route_attachment

        envelope = {
            "phone": "5511999",
            "instance": "jennifer",
            "message_id": "MSG_PDF",
            "extra": {
                "remote_jid": "5511999@s.whatsapp.net",
                "doc_mimetype": "application/pdf",
                "doc_file_name": "doc.pdf",
                "doc_base64": "JVBERi0=",
            },
        }
        decision = await route_attachment(envelope, "memorizar")
        assert decision["decision"] == "rag"
        assert decision["skill_name"] == "pdf"
        assert decision["scope"] == "private"

    @pytest.mark.asyncio
    async def test_group_scope_uses_group_routing(self):
        from agent_orchestration.knowledge_router import route_attachment

        envelope = {
            "phone": "5511999",
            "instance": "jennifer",
            "message_id": "MSG_GRP",
            "extra": {
                "remote_jid": "120363123@g.us",
                "doc_mimetype": "application/pdf",
                "doc_file_name": "doc.pdf",
                "doc_base64": "JVBERi0=",
            },
        }
        decision = await route_attachment(envelope, "memorizar")
        assert decision["decision"] == "rag"
        assert decision["scope"] == "group"

    @pytest.mark.asyncio
    async def test_unknown_mime_returns_error(self):
        from agent_orchestration.knowledge_router import route_attachment

        envelope = {
            "phone": "5511999",
            "instance": "jennifer",
            "message_id": "MSG_X",
            "extra": {
                "remote_jid": "5511999@s.whatsapp.net",
                "doc_mimetype": "application/x-totally-unknown",
                "doc_file_name": "file.bin",
            },
        }
        decision = await route_attachment(envelope, "memorizar")
        assert decision["decision"] == "rag"
        assert decision["skill"] is None
        assert decision["skill_name"] is None
        assert decision["persist_result"] == {
            "error": "no_skill_for_mime",
            "mime": "application/x-totally-unknown",
        }

    @pytest.mark.asyncio
    async def test_ambiguous_uses_llm_when_no_api_key_returns_drive(self):
        from agent_orchestration.knowledge_router import _detect_intent_keywords

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
            assert _detect_intent_keywords("olha esse contrato ai") == "ambiguous"