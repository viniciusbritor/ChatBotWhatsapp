"""Tests for orchestrator module."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestDetectIntent:
    def test_clean_message(self):
        from orchestrator import _detect_morality, _detect_correction
        assert _detect_morality("Oi Jennifer, tudo bem?") is False
        assert _detect_correction("Oi Jennifer, tudo bem?") is False

    def test_gross_message(self):
        from orchestrator import _detect_morality
        assert _detect_morality("Vai se foder, sua piranha") is True

    def test_assault_related(self):
        from orchestrator import _detect_morality
        assert _detect_morality("Sofri assedio moral no trabalho") is True

    def test_correction_message(self):
        from orchestrator import _detect_correction
        assert _detect_correction("Na verdade, meu nome e Vinicius") is True


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


class TestBuildSkillsSection:
    def test_no_skills(self):
        from orchestrator import _build_skills_section
        assert _build_skills_section([]) == ""


class TestOrchestrate:
    @pytest.mark.asyncio
    async def test_orchestrate_fallback_to_jennifer(self):
        from orchestrator import orchestrate

        with patch("orchestrator._classify_intent_llm", return_value="conversa"):
            with patch("pipelines.jennifer_pipeline.run", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {
                    "reply": "Ola, em que posso ajudar?",
                    "delay_ms": 100,
                    "presence": "composing",
                    "metadata": {"agent_id": "manager-jennifier"},
                }
                result = await orchestrate({
                    "instance": "jennifer",
                    "phone": "+5511966830020",
                    "text": "oi",
                    "sender_name": "Vinicius",
                    "extra": {},
                })

        assert result["reply"] == "Ola, em que posso ajudar?"
        assert "manager-jennifier" in result["metadata"].get("agent_id", "")

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
                mock_exec.return_value = {"reply": "OK", "delay_ms": 100, "presence": "composing", "metadata": {"agent_id": "agent-morality"}}
                result = await orchestrate({
                    "instance": "jennifer",
                    "phone": "+5511966830020",
                    "text": "Vai se foder",
                    "sender_name": "User",
                    "extra": {},
                })

        assert mock_exec.called
        call_args = mock_exec.call_args
        assert call_args[0][0]["id"] == "agent-morality"