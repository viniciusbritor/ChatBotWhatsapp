"""Tests for core.llm_provider module (DeepSeek V4 Flash only)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm_provider import LLMError, LLMProvider


class _AsyncContextManagerMock:
    """Async context manager that returns a given client."""

    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _mock_response(content: str = "ok", tool_calls=None, status_code: int = 200):
    """Build a fake httpx.Response-like object for AsyncMock."""
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    payload = {
        "id": "test-id",
        "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": message}],
        "usage": {"total_tokens": 42},
    }
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


def _mock_response_from(payload: dict):
    """Build a fake httpx.Response from a raw payload dict."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class TestIsAvailable:
    def test_available_with_deepseek(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        provider = LLMProvider()
        assert provider.is_available() is True

    def test_not_available_without_keys(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch("core.secrets.get_secret", return_value=None):
            provider = LLMProvider()
            assert provider.is_available() is False


class TestChat:
    @pytest.mark.asyncio
    async def test_deepseek_primary(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()

            mock_response = _mock_response(content="Resposta da Jennifer")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat("sys", "user")

            assert result["content"] == "Resposta da Jennifer"
            assert result["provider"] == "deepseek-v4-flash"
            assert result["model_used"] == "deepseek-v4-flash"
            assert "deepseek-v4-flash:success" in result["attempts"]

    @pytest.mark.asyncio
    async def test_no_provider_key_raises(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with patch("core.secrets.get_secret", return_value=None):
            provider = LLMProvider()
            with pytest.raises(LLMError, match="deepseek_key_not_configured"):
                await provider.chat("sys", "user")

    @pytest.mark.asyncio
    async def test_quota_exceeded_maps_to_llm_error(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            response_429 = MagicMock()
            response_429.status_code = 429
            response_429.json.return_value = {}
            response_429.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=response_429)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                with pytest.raises(LLMError, match="deepseek_quota_exceeded"):
                    await provider.chat("sys", "user")


class TestChatEscalating:
    @pytest.mark.asyncio
    async def test_returns_deepseek_response(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            mock_response = _mock_response(content="ok")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat_escalating("sys", "user")
            assert result["provider"] == "deepseek-v4-flash"
            assert result["escalated"] is False

    @pytest.mark.asyncio
    async def test_no_escalation_flag_keeps_escalated_false(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            mock_response = _mock_response(content="curto")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat_escalating(
                    "sys",
                    "user",
                    threshold=-10,
                    no_escalation=True,
                    scoring_fn=lambda t: -100,
                )
            assert result["escalated"] is False


class TestChatWithTools:
    @pytest.mark.asyncio
    async def test_native_openai_tool_call_round(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()

            first_call = _mock_response(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calendar.list_events",
                            "arguments": json.dumps({"time_min": "2026-07-23T00:00:00-03:00"}),
                        },
                    }
                ],
            )
            second_call = _mock_response(content="Voce tem 0 eventos hoje.")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(side_effect=[first_call, second_call])

            async def fake_executor(name, args):
                return json.dumps({"events": [], "count": 0})

            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat_with_tools(
                    system_prompt="sys",
                    user_prompt="o que tenho hoje?",
                    tools=[{"type": "function", "function": {"name": "calendar.list_events"}}],
                    tool_executor=fake_executor,
                )

            assert result["content"] == "Voce tem 0 eventos hoje."
            assert result["tool_rounds"] == 1
            assert result["provider"] == "deepseek-v4-flash"
            assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_calls(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            mock_response = _mock_response(content="Resposta direta sem tool.")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat_with_tools(
                    system_prompt="sys",
                    user_prompt="oi",
                    tools=[{"type": "function", "function": {"name": "x"}}],
                    tool_executor=None,
                )
            assert result["content"] == "Resposta direta sem tool."
            assert result["tool_rounds"] == 0
            assert result["provider"] == "deepseek-v4-flash"

    @pytest.mark.asyncio
    async def test_chat_tracks_cache_hit_tokens(self, monkeypatch):
        """chat() captura prompt_cache_hit_tokens do usage da API."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            payload = {
                "id": "x",
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "total_tokens": 1050,
                    "prompt_cache_hit_tokens": 800,
                },
            }
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = payload
            response.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=response)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat(system_prompt="sys", user_prompt="oi")
            assert result["usage"]["cache_hit_tokens"] == 800
            assert result["usage"]["prompt_tokens"] == 1000
            sent = mock_client.post.await_args.kwargs["json"]
            assert sent.get("cache_mode") == "default"

    @pytest.mark.asyncio
    async def test_chat_tracks_cache_hit_from_details(self, monkeypatch):
        """Fallback: prompt_tokens_details.cached_tokens quando API usa esse formato."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            payload = {
                "id": "x",
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "total_tokens": 1050,
                    "prompt_tokens_details": {"cached_tokens": 600},
                },
            }
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = payload
            response.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=response)
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat(system_prompt="sys", user_prompt="oi")
            assert result["usage"]["cache_hit_tokens"] == 600

    @pytest.mark.asyncio
    async def test_chat_with_tools_sends_cache_mode_and_tracks_hits(self, monkeypatch):
        """chat_with_tools envia cache_mode na raiz e soma cache hits entre rounds."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            first = {
                "id": "x",
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}
                ]}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 10, "total_tokens": 1010,
                          "prompt_cache_hit_tokens": 900},
            }
            second = {
                "id": "y",
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "feito"}}],
                "usage": {"prompt_tokens": 1100, "completion_tokens": 20, "total_tokens": 1120,
                          "prompt_cache_hit_tokens": 950},
            }
            mock_client = MagicMock()
            mock_client.post = AsyncMock(side_effect=[
                _mock_response_from(first), _mock_response_from(second),
            ])
            with patch("core.llm_provider.httpx.AsyncClient", return_value=_AsyncContextManagerMock(mock_client)):
                result = await provider.chat_with_tools(
                    system_prompt="sys",
                    user_prompt="oi",
                    tools=[{"type": "function", "function": {"name": "x"}}],
                    tool_executor=lambda name, args: "{}",
                )
            assert result["usage"]["cache_hit_tokens"] == 1850  # 900 + 950
            for call in mock_client.post.await_args_list:
                assert call.kwargs["json"].get("cache_mode") == "default"


class TestParseToolCalls:
    def test_extracts_tool_calls(self):
        data = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "calendar.list_events", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        }
        calls = LLMProvider.parse_tool_calls(data)
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "calendar.list_events"

    def test_empty_choices_returns_empty(self):
        assert LLMProvider.parse_tool_calls({}) == []
        assert LLMProvider.parse_tool_calls({"choices": []}) == []


class TestDefaults:
    def test_default_model_is_deepseek_v4_flash(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            assert provider.deepseek_model == "deepseek-v4-flash"
            assert provider.deepseek_base == "https://api.deepseek.com"

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.example/v1")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()
            assert provider.deepseek_model == "deepseek-v4-pro"
            assert provider.deepseek_base == "https://api.deepseek.example/v1"


class TestToolNameTranslation:
    @pytest.mark.asyncio
    async def test_tool_call_name_translates_underscore_back_to_dot(self, monkeypatch):
        """DeepSeek v4-flash rejects tool names with dots (HTTP 400). We rewrite
        ``.`` -> ``_`` on the wire and translate back when the model calls."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("core.secrets.get_secret", return_value="sk-test"):
            provider = LLMProvider()

            wire_call = _mock_response(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calendar_list_events",
                            "arguments": json.dumps({"time_min": "2026-07-25T00:00:00-03:00"}),
                        },
                    }
                ],
            )
            wire_done = _mock_response(content="Voce tem 0 eventos hoje.")
            mock_client = MagicMock()
            mock_client.post = AsyncMock(side_effect=[wire_call, wire_done])

            captured_payloads = []

            class _CaptureClient(_AsyncContextManagerMock):
                async def __aenter__(self_inner):
                    captured_payloads.append(mock_client)
                    return mock_client

            async def fake_executor(name, args):
                assert name == "calendar.list_events", f"expected original name, got {name}"
                return json.dumps({"events": [], "count": 0})

            with patch("core.llm_provider.httpx.AsyncClient", return_value=_CaptureClient(mock_client)):
                result = await provider.chat_with_tools(
                    system_prompt="sys",
                    user_prompt="o que tenho?",
                    tools=[{"type": "function", "function": {"name": "calendar.list_events", "parameters": {"type": "object", "properties": {}}}}],
                    tool_executor=fake_executor,
                )

            assert captured_payloads, "no payload captured"
            sent_tools = captured_payloads[0].post.await_args.kwargs["json"].get("tools")
            assert sent_tools[0]["function"]["name"] == "calendar_list_events"
            assert result["tool_rounds"] == 1
            assert result["content"] == "Voce tem 0 eventos hoje."
