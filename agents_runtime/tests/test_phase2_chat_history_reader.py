"""Fase 2 — Reader + Wrapper + Injecao de contexto."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGetConversationHistory:
    @pytest.mark.asyncio
    async def test_empty_phone_returns_empty(self):
        from core.rag import get_conversation_history
        result = await get_conversation_history("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_no_firestore_returns_empty(self):
        from core.rag import get_conversation_history
        with patch("core.rag._get_firestore", return_value=None):
            result = await get_conversation_history("+5511966830020")
        assert result == ""

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self, monkeypatch):
        from core.rag import get_conversation_history
        fake_db = MagicMock()
        fake_db.collection.side_effect = RuntimeError("db_down")
        monkeypatch.setattr("core.rag._get_firestore", lambda: fake_db)
        result = await get_conversation_history("+5511966830020")
        assert result == ""


class TestContextWrapper:
    @pytest.mark.asyncio
    async def test_prefers_new_reader(self):
        from orchestrator import _get_context_for_prompt
        with patch("core.rag.get_conversation_history", new_callable=AsyncMock) as mock_new:
            mock_new.return_value = "Usuario: Oi\nJennifer: Ola"
            result = await _get_context_for_prompt("+5511966830020")
        assert "Usuario" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy(self):
        from orchestrator import _get_context_for_prompt
        with patch("core.rag.get_conversation_history", new_callable=AsyncMock) as mock_new:
            mock_new.return_value = ""
            with patch("orchestrator._get_conversation_history", return_value="legacy"):
                result = await _get_context_for_prompt("+5511966830020")
        assert result == "legacy"

    @pytest.mark.asyncio
    async def test_new_reader_exception_falls_back(self):
        from orchestrator import _get_context_for_prompt
        with patch("core.rag.get_conversation_history", side_effect=RuntimeError("boom")):
            with patch("orchestrator._get_conversation_history", return_value="survived"):
                result = await _get_context_for_prompt("+5511966830020")
        assert result == "survived"

    @pytest.mark.asyncio
    async def test_both_failures_return_empty(self):
        from orchestrator import _get_context_for_prompt
        with patch("core.rag.get_conversation_history", side_effect=RuntimeError("boom")):
            with patch("orchestrator._get_conversation_history", side_effect=RuntimeError("boom2")):
                result = await _get_context_for_prompt("+5511966830020")
        assert result == ""
