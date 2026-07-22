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
    def test_available_with_deepseek(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()
        assert provider.is_available() is True

    def test_not_available_without_keys(self, monkeypatch):
        for key in ["DEEPSEEK_API_KEY", "NVIDIA_API_KEY", "MINIMAX_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GCP_PROJECT", "")
        monkeypatch.setenv("GCLOUD_PROJECT", "")
        monkeypatch.setattr("core.llm_provider.LLMProvider.gemini_available", lambda self: False)
        provider = LLMProvider()
        assert provider.is_available() is False


class TestChatCascade:
    @pytest.mark.asyncio
    async def test_deepseek_used_when_minimax_unavailable(self, monkeypatch, mock_responses):
        """When only DeepSeek is configured, the cascade reaches it directly."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("DeepSeek answer")):
            result = await provider.chat("sys", "user", model="deepseek-v4-flash")

        assert result["content"] == "DeepSeek answer"
        assert result["provider"] == "deepseek"
        assert result["model_used"] == "deepseek-v4-flash"

    @pytest.mark.asyncio
    async def test_cascade_fallback_to_deepseek(self, monkeypatch, mock_responses):
        """MiniMax fails (quota), DeepSeek is tried and used."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")

        provider = LLMProvider()

        fail_response = MagicMock()
        fail_response.status_code = 429

        success_response = mock_responses("DeepSeek answer")

        with patch("requests.post", side_effect=[fail_response, fail_response, success_response]):
            with patch("time.sleep"):
                result = await provider.chat("sys", "user", model="deepseek-v4-flash")

        assert result["content"] == "DeepSeek answer"
        assert result["provider"] == "deepseek"

    @pytest.mark.asyncio
    async def test_minimax_highspeed_first(self, monkeypatch, mock_responses):
        """MiniMax-M2.7-highspeed is the primary provider (Fase A decision)."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")

        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("MiniMax fast answer")):
            result = await provider.chat("sys", "user")

        assert result["content"] == "MiniMax fast answer"
        assert result["provider"] == "minimax-hs"
        assert result["model_used"] == "MiniMax-M2.7-highspeed"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")

        provider = LLMProvider()

        fail_response = MagicMock()
        fail_response.status_code = 429

        with patch("requests.post", return_value=fail_response):
            with patch("time.sleep"):
                with pytest.raises(LLMError, match="all_providers_failed"):
                    await provider.chat("sys", "user", model="deepseek-v4-flash")


class TestChatEscalating:
    @pytest.mark.asyncio
    async def test_no_escalation_when_confident(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("Good long answer with many words")):
            result = await provider.chat_escalating(
                "sys", "user",
                fast_model="deepseek-v4-flash",
                pro_model="deepseek-v4-pro",
                threshold=-2,
                scoring_fn=lambda t: 0,
            )
        assert result["escalated"] is False
        assert result["provider"] == "minimax-hs"

    @pytest.mark.asyncio
    async def test_escalation_when_low_confidence(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        flash_response = mock_responses("sim")
        pro_response = mock_responses("Much better detailed answer with many words")

        with patch("requests.post", side_effect=[flash_response, pro_response]):
            with patch("time.sleep"):
                result = await provider.chat_escalating(
                    "sys", "user",
                    fast_model="deepseek-v4-flash",
                    pro_model="deepseek-v4-pro",
                    threshold=-2,
                    scoring_fn=lambda t: -3,
                )
        assert result["escalated"] is True
        assert "fast_response" in result
        assert result["confidence_score"] == -3

    @pytest.mark.asyncio
    async def test_no_escalation_flag_disables_escalation(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("sim")):
            result = await provider.chat_escalating(
                "sys", "user",
                no_escalation=True,
                scoring_fn=lambda t: -5,
            )
        assert result["escalated"] is False


class TestJsonMarkerInjection:
    def test_injects_json_marker_when_json_mode(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()
        result = provider._maybe_inject_json_marker("You are helpful", json_mode=True)
        assert result.startswith("JSON: ")

    def test_no_injection_when_json_keyword_present(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()
        original = "Return json with the result"
        result = provider._maybe_inject_json_marker(original, json_mode=True)
        assert result == original

    def test_no_injection_when_json_mode_false(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()
        result = provider._maybe_inject_json_marker("Plain text", json_mode=False)
        assert result == "Plain text"


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
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
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

