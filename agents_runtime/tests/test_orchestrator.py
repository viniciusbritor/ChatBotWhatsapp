"""Tests for orchestrator module."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def close_coroutine(coroutine):
    coroutine.close()
    return MagicMock()


class TestDetectIntent:
    def test_clean_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Oi Jennifer, tudo bem?")
        assert intent["is_gross"] is False
        assert intent["is_assault_related"] is False
        assert intent["is_correction"] is False

    def test_gross_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Vai se foder, sua piranha")
        assert intent["is_gross"] is True

    def test_assault_related(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Sofri assedio moral no trabalho")
        assert intent["is_assault_related"] is True

    def test_correction_message(self):
        from orchestrator import _detect_intent
        intent = _detect_intent("Na verdade, meu nome e Vinicius")
        assert intent["is_correction"] is True


class TestResolveAgentForIntent:
    def test_gross_routes_to_morality(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": True, "is_assault_related": False, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-morality"

    def test_assault_routes_to_morality(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": True, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-morality"

    def test_correction_routes_to_learning(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": False, "is_correction": True, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") == "agent-learning"

    def test_clean_returns_none(self):
        from orchestrator import _resolve_agent_for_intent
        intent = {"is_gross": False, "is_assault_related": False, "is_correction": False, "is_calendar": False, "is_drive": False, "is_email": False, "is_web_search": False, "is_intimacy": False}
        assert _resolve_agent_for_intent(intent, "jennifer") is None


class TestExtractToolCalls:
    def test_extract_mentioned_tool(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls(
            "Vou verificar o calendar agora",
            ["calendar.list_events", "gmail.search_messages"],
        )
        assert len(result) >= 1
        assert result[0]["tool_id"] == "calendar.list_events"

    def test_no_match(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls("Apenas texto", ["calendar.list_events"])
        assert result == []

    def test_empty_tools(self):
        from orchestrator import _extract_tool_calls
        result = _extract_tool_calls("algum texto", [])
        assert result == []


class TestBindToolArgs:
    def test_user_phone_overrides_model_supplied_phone(self):
        from orchestrator import _bind_tool_args

        result = _bind_tool_args(
            "gmail.search_messages",
            {"query": "in:inbox", "phone": "attacker-phone"},
            "5511966830020",
        )
        assert result["phone"] == "5511966830020"

    def test_public_tool_does_not_receive_phone(self):
        from orchestrator import _bind_tool_args

        result = _bind_tool_args("web.search", {"query": "teste"}, "5511966830020")
        assert "phone" not in result


class TestBuildSkillsSection:
    def test_no_skills(self):
        from orchestrator import _build_skills_section
        assert _build_skills_section([]) == ""


class TestOrchestrate:
    @pytest.mark.asyncio
    async def test_orchestrate_with_no_agents_loaded(self):
        from orchestrator import orchestrate

        with patch("orchestrator.get_agent", return_value=None):
            with patch("orchestrator._select_orchestrator_agent", return_value=None):
                result = await orchestrate({
                    "instance": "jennifer",
                    "phone": "+5511966830020",
                    "text": "oi",
                    "sender_name": "Vinicius",
                    "extra": {},
                })

        assert "error" in result["metadata"]
        assert result["metadata"]["error"] == "no_orchestrator"

    @pytest.mark.asyncio
    async def test_orchestrate_gross_routes_to_morality(self):
        from orchestrator import orchestrate

        mock_morality = {
            "id": "agent-morality",
            "name": "Morality Agent",
            "enabled": True,
            "model": "deepseek-v4-flash",
            "system_prompt": "Test",
            "tools": ["rag.search_legal_knowledge"],
            "skills": [],
        }

        with patch("orchestrator.get_agent", return_value=mock_morality):
            with patch("orchestrator._execute_agent", new_callable=AsyncMock) as mock_exec:
                with patch("orchestrator._schedule_indexing", side_effect=close_coroutine):
                    mock_exec.return_value = {"reply": "OK", "delay_ms": 100, "presence": "composing", "metadata": {"agent_id": "agent-morality"}}
                    await orchestrate({
                        "instance": "jennifer",
                        "phone": "+5511966830020",
                        "text": "Vai se foder",
                        "sender_name": "User",
                        "extra": {},
                    })

        assert mock_exec.called
        call_args = mock_exec.call_args
        assert call_args[0][0]["id"] == "agent-morality"
