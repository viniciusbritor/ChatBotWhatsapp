"""Tests for core.llm_provider module (cascade fallback with mocks)."""
import pytest
import asyncio
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
    def test_deepseek_success(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()
        with patch("requests.post", return_value=mock_responses("DeepSeek answer")):
            result = asyncio.run(provider.chat("sys", "user", model="deepseek-v4-flash"))
        assert result["content"] == "DeepSeek answer"
        assert result["provider"] == "deepseek"
        assert result["model_used"] == "deepseek-v4-flash"

    def test_cascade_fallback_to_deepseek(self, monkeypatch, mock_responses):
        """If all MM fail, DeepSeek should be tried via chat() path."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("DeepSeek answer")):
            with patch("time.sleep"):
                result = asyncio.run(provider.chat("sys", "user", model="deepseek-v4-flash"))

        assert result["content"] == "DeepSeek answer"
        assert "deepseek" in result["provider"]

    def test_all_providers_fail(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")

        provider = LLMProvider()

        fail_response = MagicMock()
        fail_response.status_code = 429

        with patch("requests.post", return_value=fail_response):
            with patch("time.sleep"):
                with pytest.raises(LLMError, match="all_providers_failed"):
                    asyncio.run(provider.chat("sys", "user", model="deepseek-v4-flash"))


class TestChatEscalating:
    def test_no_escalation_when_confident(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("Good long answer with many words")):
            result = asyncio.run(provider.chat_escalating(
                "sys", "user",
                fast_model="deepseek-v4-flash",
                pro_model="deepseek-v4-pro",
                threshold=-2,
                scoring_fn=lambda t: 0,
            ))
        assert result["escalated"] is False
        assert result["provider"] == "deepseek"

    def test_escalation_when_low_confidence(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()

        flash_response = mock_responses("sim")
        pro_response = mock_responses("Much better detailed answer with many words")

        with patch("requests.post", side_effect=[flash_response, pro_response]):
            with patch("time.sleep"):
                result = asyncio.run(provider.chat_escalating(
                    "sys", "user",
                    fast_model="deepseek-v4-flash",
                    pro_model="deepseek-v4-pro",
                    threshold=-2,
                    scoring_fn=lambda t: -3,
                ))
        assert result["escalated"] is True
        assert "fast_response" in result
        assert result["confidence_score"] == -3

    def test_no_escalation_flag_disables_escalation(self, monkeypatch, mock_responses):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        provider = LLMProvider()

        with patch("requests.post", return_value=mock_responses("sim")):
            result = asyncio.run(provider.chat_escalating(
                "sys", "user",
                no_escalation=True,
                scoring_fn=lambda t: -5,
            ))
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