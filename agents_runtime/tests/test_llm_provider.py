"""Tests for core.llm_provider module (cascade fallback with mocks)."""
import json

import pytest
from unittest.mock import patch, MagicMock
from core.llm_provider import LLMProvider, LLMError


@pytest.fixture
def mock_responses():
    """Mock successful response from requests.post."""
    def _make_response(content="Test response", status_code=200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock.raise_for_status = MagicMock()
        return mock
    return _make_response


class TestIsAvailable:
    def test_available_with_minimax(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        provider = LLMProvider()
        assert provider.is_available() is True

    def test_available_with_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")
        provider = LLMProvider()
        assert provider.is_available() is True

    def test_not_available_without_keys(self, monkeypatch):
        for key in ["MINIMAX_API_KEY", "GEMINI_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GCP_PROJECT", "")
        monkeypatch.setenv("GCLOUD_PROJECT", "")
        provider = LLMProvider()
        assert provider.is_available() is False


class TestCascade:
    @pytest.mark.asyncio
    async def test_minimax_highspeed_first(self, monkeypatch, mock_responses):
        """MiniMax-M2.7-highspeed is the primary provider."""
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("MiniMax fast answer")):
            result = await provider.chat("sys", "user")

        assert result["content"] == "MiniMax fast answer"
        assert result["provider"] == "minimax-hs"
        assert result["model_used"] == "MiniMax-M2.7-highspeed"

    @pytest.mark.asyncio
    async def test_gemini_fallback_when_minimax_fails(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        provider = LLMProvider()

        fail_response = MagicMock()
        fail_response.status_code = 429
        fail_response.raise_for_status = MagicMock()

        async def fake_call_gemini(*args, **kwargs):
            return "Gemini fallback answer"

        with patch("requests.post", return_value=fail_response):
            with patch("time.sleep"):
                with patch.object(
                    provider,
                    "_call_gemini",
                    side_effect=fake_call_gemini,
                ):
                    result = await provider.chat("sys", "user")

        assert result["content"] == "Gemini fallback answer"
        assert result["provider"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        provider = LLMProvider()

        fail_response = MagicMock()
        fail_response.status_code = 429
        fail_response.raise_for_status = MagicMock()

        async def fake_call_gemini(*args, **kwargs):
            raise LLMError("gemini_quota_exceeded")

        with patch("requests.post", return_value=fail_response):
            with patch("time.sleep"):
                with patch.object(provider, "_call_gemini", side_effect=fake_call_gemini):
                    with pytest.raises(LLMError, match="all_providers_failed"):
                        await provider.chat("sys", "user")


class TestChatEscalating:
    @pytest.mark.asyncio
    async def test_no_escalation_when_confident(self, monkeypatch, mock_responses):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("Good long answer with many words")):
            result = await provider.chat_escalating(
                "sys", "user",
                fast_model="MiniMax-M2.7-highspeed",
                pro_model="gemini-2.5-flash",
                threshold=-2,
                scoring_fn=lambda t: 0,
            )
        assert result["escalated"] is False
        assert result["provider"] == "minimax-hs"

    @pytest.mark.asyncio
    async def test_escalation_when_low_confidence(self, monkeypatch, mock_responses):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        async def fake_call_gemini(*args, **kwargs):
            return "Gemini better answer"

        with patch("requests.post", return_value=mock_responses("sim")):
            with patch.object(provider, "_call_gemini", side_effect=fake_call_gemini):
                result = await provider.chat_escalating(
                    "sys", "user",
                    fast_model="MiniMax-M2.7-highspeed",
                    pro_model="gemini-2.5-flash",
                    threshold=-2,
                    scoring_fn=lambda t: -3,
                )
        assert result["escalated"] is True
        assert "fast_response" in result
        assert result["confidence_score"] == -3

    @pytest.mark.asyncio
    async def test_no_escalation_flag_disables_escalation(self, monkeypatch, mock_responses):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("sim")):
            result = await provider.chat_escalating(
                "sys", "user",
                no_escalation=True,
                scoring_fn=lambda t: -5,
            )
        assert result["escalated"] is False


class TestExtractMiniMaxToolCalls:
    def test_extracts_invoke_from_content(self):
        from core.llm_provider import _extract_minimax_tool_calls

        dirty = (
            'Vou checar [<minimax>[<tool_call>'
            '<invoke name="calendar.list_events" date="2026-07-21">'
            '<action>{"time_min": "2026-07-21T00:00:00-03:00"}</action>'
            '</invoke>'
            '</tool_call>]'
        )
        tool_calls, cleaned = _extract_minimax_tool_calls(dirty)
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "calendar.list_events"
        assert json.loads(tool_calls[0]["function"]["arguments"]) == {
            "time_min": "2026-07-21T00:00:00-03:00"
        }
        assert "Vou checar" in cleaned
        assert "[<minimax>" not in cleaned
        assert "<tool_call>" not in cleaned

    def test_returns_empty_for_normal_text(self):
        from core.llm_provider import _extract_minimax_tool_calls

        tool_calls, cleaned = _extract_minimax_tool_calls("Oi tudo bem?")
        assert tool_calls == []
        assert cleaned == "Oi tudo bem?"

    def test_handles_invoke_without_action(self):
        from core.llm_provider import _extract_minimax_tool_calls

        dirty = '<invoke name="calendar.list_events"></invoke>'
        tool_calls, cleaned = _extract_minimax_tool_calls(dirty)
        assert len(tool_calls) == 1
        assert json.loads(tool_calls[0]["function"]["arguments"]) == {}
        assert cleaned == ""

    def test_extracts_multiple_invocations(self):
        from core.llm_provider import _extract_minimax_tool_calls

        dirty = (
            'oi [<minimax>[<tool_call>'
            '<invoke name="calendar.list_events"></invoke>'
            '</tool_call>]'
            ' [<minimax>[<tool_call>'
            '<invoke name="gmail.search_messages"></invoke>'
            '</tool_call>]'
        )
        tool_calls, cleaned = _extract_minimax_tool_calls(dirty)
        names = [tc["function"]["name"] for tc in tool_calls]
        assert names == ["calendar.list_events", "gmail.search_messages"]
        assert "oi" in cleaned
        assert "[<minimax>" not in cleaned


@pytest.mark.asyncio
class TestChatWithToolsMiniMaxFallback:
    @pytest.mark.asyncio
    async def test_extracts_inline_tool_call_when_structured_empty(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-mm")

        provider = LLMProvider()

        dirty_content = (
            "Vou checar [<minimax>[<tool_call>"
            '<invoke name="calendar.list_events">'
            '<action>{"time_min": "2026-07-21T00:00:00-03:00"}</action>'
            "</invoke></tool_call>]"
        )
        clean_content = "Voce tem 0 eventos hoje."

        call_count = {"n": 0}

        async def fake_call_provider(payload, model):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {
                    "choices": [
                        {"message": {"content": dirty_content, "tool_calls": []}}
                    ]
                }
            return {
                "choices": [
                    {"message": {"content": clean_content, "tool_calls": []}}
                ]
            }

        async def fake_executor(name, args):
            return json.dumps({"events": [], "count": 0})

        with patch.object(provider, "_call_provider", side_effect=fake_call_provider):
            result = await provider.chat_with_tools(
                system_prompt="sys",
                user_prompt="user",
                tools=[{"type": "function", "function": {"name": "calendar.list_events"}}],
                tool_executor=fake_executor,
                model="MiniMax-M2.7-highspeed",
            )

        assert "[<minimax>" not in result["content"]
        assert "<tool_call>" not in result["content"]
        assert "<invoke" not in result["content"]
        assert result["content"] == clean_content
        assert result["tool_rounds"] == 1
