"""Fase 3 — Tool search_chat_history + registro no TOOL_REGISTRY."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


class TestSearchChatHistory:
    @pytest.mark.asyncio
    async def test_empty_phone_returns_error(self):
        from tools.chat_history import search_chat_history
        result = await search_chat_history("", "query")
        assert result["count"] == 0
        assert "missing_phone" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        from tools.chat_history import search_chat_history
        result = await search_chat_history("+5511966830020", "")
        assert result["count"] == 0
        assert "empty_query" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_delegates_to_search_conversation_memory(self):
        from tools.chat_history import search_chat_history

        fake_results = [
            {"text": "Oi Jennifer", "direction": "in", "created_at": "2026-01-01", "score": 1.0},
            {"text": "Ola", "direction": "out", "created_at": "2026-01-01", "score": 1.0},
        ]
        with patch("core.rag.search_conversation_memory", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = fake_results
            result = await search_chat_history("+5511966830020", "oi")
        assert result["count"] == 2
        assert result["results"][0]["text"] == "Oi Jennifer"
        assert mock_search.called

    @pytest.mark.asyncio
    async def test_handles_search_exception(self):
        from tools.chat_history import search_chat_history

        with patch("core.rag.search_conversation_memory", side_effect=RuntimeError("db_unavailable")):
            result = await search_chat_history("+5511966830020", "query")
        assert result["count"] == 0
        assert "error" in result


class TestGetChatContext:
    @pytest.mark.asyncio
    async def test_empty_phone_returns_empty(self):
        from tools.chat_history import get_chat_context
        result = await get_chat_context("")
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_delegates_to_get_conversation_history(self):
        from tools.chat_history import get_chat_context

        with patch("core.rag.get_conversation_history", new_callable=AsyncMock) as mock_hist:
            mock_hist.return_value = "Usuario: Oi\nJennifer: Ola"
            result = await get_chat_context("+5511966830020")
        assert result["count"] > 0
        assert "Usuario" in result["text"]


class TestToolRegistry:
    def test_both_tools_registered(self):
        from tool_registry import TOOL_REGISTRY, get_tool

        assert "chat_history.search" in TOOL_REGISTRY
        assert "chat_history.context" in TOOL_REGISTRY

        fn = get_tool("chat_history.search")
        assert fn is not None
        assert callable(fn)

        fn = get_tool("chat_history.context")
        assert fn is not None
        assert callable(fn)

    def test_schemas_have_phone_param(self):
        from tool_registry import get_tool_schema

        schema = get_tool_schema("chat_history.search")
        assert schema is not None
        assert "phone" in schema["parameters"]["required"]

        schema = get_tool_schema("chat_history.context")
        assert schema is not None
        assert "phone" in schema["parameters"]["required"]

    def test_search_schema_requires_query(self):
        from tool_registry import get_tool_schema
        schema = get_tool_schema("chat_history.search")
        assert "query" in schema["parameters"]["required"]


class TestJenniferPromptUpdate:
    def test_chat_history_section_in_prompt(self):
        from agent_orchestration.jennifier import JENNIFER_SYSTEM_PROMPT
        assert "[CHAT HISTORY]" in JENNIFER_SYSTEM_PROMPT
        assert "chat_history.search" in JENNIFER_SYSTEM_PROMPT
        assert "chat_history.context" in JENNIFER_SYSTEM_PROMPT
