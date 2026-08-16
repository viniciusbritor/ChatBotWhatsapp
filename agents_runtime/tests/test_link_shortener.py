"""Tests for core.link_shortener (regra global de encurtamento de links)."""

from __future__ import annotations

import os
import time
from unittest.mock import patch, MagicMock

import pytest

from core.link_shortener import (
    shorten_urls_in_text,
    _is_shortened_url,
    _call_tinyurl,
    _call_isgd,
    _call_custom,
    clear_cache,
    _url_cache,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Limpa cache + env vars entre testes."""
    clear_cache()
    os.environ["LINK_SHORTENER_ENABLED"] = "true"
    os.environ["LINK_SHORTENER_PROVIDER"] = "tinyurl"
    os.environ["LINK_SHORTENER_TIMEOUT_SEC"] = "3"
    yield
    clear_cache()


class TestShortenOneUrl:
    def test_shorten_url_tinyurl(self):
        """TinyURL provider retorna URL encurtada."""
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/abc123") as mock_tiny:
            result = shorten_urls_in_text("Veja https://google.com/search?q=hello")
            assert "https://tinyurl.com/abc123" in result
            assert "https://google.com" not in result.replace("https://tinyurl.com/abc123", "")
            mock_tiny.assert_called_once_with("https://google.com/search?q=hello", 3.0)

    def test_shorten_multiple_urls(self):
        """Multiplas URLs na mesma string sao todas encurtadas."""
        text = "Acesse https://google.com e https://wikipedia.org/wiki/RAG"
        with patch("core.link_shortener._call_tinyurl") as mock_tiny:
            mock_tiny.side_effect = lambda url, t: (
                "https://tinyurl.com/g" if "google" in url else "https://tinyurl.com/w"
            )
            result = shorten_urls_in_text(text)
            assert "https://tinyurl.com/g" in result
            assert "https://tinyurl.com/w" in result
            assert mock_tiny.call_count == 2

    def test_skip_already_shortened(self):
        """URLs ja encurtadas nao sao re-encurtadas."""
        with patch("core.link_shortener._call_tinyurl") as mock_tiny:
            text = "curto: https://bit.ly/abc e longo: https://google.com"
            with patch("core.link_shortener._call_tinyurl") as mock_tiny:
                mock_tiny.return_value = "https://tinyurl.com/g"
                result = shorten_urls_in_text(text)
                # bit.ly preservado
                assert "https://bit.ly/abc" in result
                # google.com encurtado
                assert "https://tinyurl.com/g" in result
                assert mock_tiny.call_count == 1

    def test_provider_failure_fallback(self):
        """Se provedor falha, URL original eh preservada."""
        with patch("core.link_shortener._call_tinyurl", return_value=None):
            text = "olha https://google.com ai"
            result = shorten_urls_in_text(text)
            assert "https://google.com" in result
            assert "tinyurl" not in result

    def test_shortener_disabled(self):
        """LINK_SHORTENER_ENABLED=false bypass completo."""
        os.environ["LINK_SHORTENER_ENABLED"] = "false"
        with patch("core.link_shortener._call_tinyurl") as mock_tiny:
            text = "Veja https://google.com"
            result = shorten_urls_in_text(text)
            assert result == text
            mock_tiny.assert_not_called()

    def test_provider_isgd(self):
        """Provider is.gd funciona."""
        os.environ["LINK_SHORTENER_PROVIDER"] = "isgd"
        with patch("core.link_shortener._call_isgd", return_value="https://is.gd/xyz") as mock_isgd:
            result = shorten_urls_in_text("link https://example.com")
            assert "https://is.gd/xyz" in result
            mock_isgd.assert_called_once()

    def test_provider_custom(self):
        """Provider custom usa template."""
        os.environ["LINK_SHORTENER_PROVIDER"] = "custom"
        os.environ["LINK_SHORTENER_CUSTOM_URL"] = "https://my-shortener.com/api?url={url}"
        with patch("core.link_shortener._call_custom", return_value="https://my-shortener.com/x") as mock_custom:
            result = shorten_urls_in_text("https://google.com")
            assert "https://my-shortener.com/x" in result
            mock_custom.assert_called_once()

    def test_cache_hit(self):
        """Segunda chamada usa cache, nao HTTP."""
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/cached") as mock_tiny:
            shorten_urls_in_text("https://google.com")
            shorten_urls_in_text("https://google.com")
            shorten_urls_in_text("https://google.com")
            assert mock_tiny.call_count == 1

    def test_text_without_urls(self):
        """Texto sem URLs retorna intacto."""
        with patch("core.link_shortener._call_tinyurl") as mock_tiny:
            result = shorten_urls_in_text("apenas texto sem links")
            assert result == "apenas texto sem links"
            mock_tiny.assert_not_called()

    def test_url_in_special_positions(self):
        """URLs em final de frase, entre virgulas, entre parenteses."""
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/s"):
            text = "Veja (https://google.com), e tambem https://github.com/x."
            result = shorten_urls_in_text(text)
            assert "https://tinyurl.com/s" in result
            # Pelo menos 1 URL foi encurtada
            assert "tinyurl.com" in result


class TestIsShortenedUrl:
    def test_bitly_recognized(self):
        assert _is_shortened_url("https://bit.ly/abc123") is True

    def test_tinyurl_recognized(self):
        assert _is_shortened_url("https://tinyurl.com/abc") is True

    def test_google_long_not_shortened(self):
        assert _is_shortened_url("https://google.com/search?q=hello") is False

    def test_invalid_url_returns_false(self):
        assert _is_shortened_url("not a url") is False


class TestTinyURL:
    def test_shorten_success(self):
        """TinyURL API success."""
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "https://tinyurl.com/abc"
            mock_get.return_value = mock_resp
            result = _call_tinyurl("https://google.com", 3.0)
            assert result == "https://tinyurl.com/abc"

    def test_shorten_http_error(self):
        """TinyURL returns 500 = no short."""
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "error"
            mock_get.return_value = mock_resp
            result = _call_tinyurl("https://google.com", 3.0)
            assert result is None

    def test_shorten_exception(self):
        """Network exception captured gracefully."""
        with patch("httpx.Client.get", side_effect=Exception("network")):
            result = _call_tinyurl("https://google.com", 3.0)
            assert result is None


class TestIsgd:
    def test_shorten_success(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "https://is.gd/xyz"
            mock_get.return_value = mock_resp
            result = _call_isgd("https://google.com", 3.0)
            assert result == "https://is.gd/xyz"

    def test_shorten_returns_non_url(self):
        """is.gd retorna texto sem scheme."""
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "error"
            mock_get.return_value = mock_resp
            result = _call_isgd("https://google.com", 3.0)
            assert result is None


class TestCustom:
    def test_custom_template_json(self):
        """Custom provider returns JSON with short_url."""
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.json.return_value = {"short_url": "https://my.cx/abc"}
            mock_post.return_value = mock_resp
            result = _call_custom("https://google.com", "https://myapi.com/{url}", 3.0)
            assert result == "https://my.cx/abc"

    def test_custom_http_error(self):
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_post.return_value = mock_resp
            result = _call_custom("https://google.com", "https://x/{url}", 3.0)
            assert result is None


class TestClearCache:
    def test_clear_cache(self):
        """clear_cache limpa tudo."""
        _url_cache["test_url"] = "test_short"
        clear_cache()
        assert "test_url" not in _url_cache
        assert len(_url_cache) == 0


class TestEdgeCases:
    def test_empty_text(self):
        assert shorten_urls_in_text("") == ""

    def test_none_text(self):
        assert shorten_urls_in_text(None) == ""

    def test_url_with_query_and_fragment(self):
        """URL com query params + fragment."""
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/q"):
            text = "https://google.com/search?q=hello&lang=pt#section"
            result = shorten_urls_in_text(text)
            assert "https://tinyurl.com/q" in result

    def test_unknown_provider_falls_back_to_tinyurl(self):
        """Provider unknown usa tinyurl."""
        os.environ["LINK_SHORTENER_PROVIDER"] = "weird-provider"
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/x") as mock:
            result = shorten_urls_in_text("https://google.com")
            assert "https://tinyurl.com/x" in result
            mock.assert_called_once()
