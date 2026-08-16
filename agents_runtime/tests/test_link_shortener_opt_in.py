"""Tests for link_shortener opt-in (skip short texts)."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def enable_shortener():
    os.environ["LINK_SHORTENER_ENABLED"] = "true"
    os.environ["LINK_SHORTENER_PROVIDER"] = "tinyurl"
    yield
    os.environ.pop("LINK_SHORTENER_MIN_TEXT_LENGTH", None)


@pytest.fixture(autouse=True)
def clear_cache():
    from core.link_shortener import clear_cache
    clear_cache()
    yield
    clear_cache()


class TestShortenOptIn:
    def test_short_text_returns_unchanged(self):
        """Texto curto (< 50 chars) NAO chama API."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            result = shorten_urls_in_text("oi google.com teste")
            assert result == "oi google.com teste"
            mock.assert_not_called()

    def test_short_text_even_with_url_unchanged(self):
        """Texto curto com URL NAO chama API."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            short = "https://google.com"
            result = shorten_urls_in_text(short)
            assert result == short
            mock.assert_not_called()

    def test_long_text_with_url_calls_api(self):
        """Texto longo (> 50 chars) COM URL chama API."""
        from core.link_shortener import shorten_urls_in_text
        long_text = "olha esse link interessante " + ("x" * 50) + " https://google.com"
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/abc") as mock:
            result = shorten_urls_in_text(long_text)
            assert "https://tinyurl.com/abc" in result
            mock.assert_called_once()

    def test_long_text_no_url_unchanged(self):
        """Texto longo SEM URL NAO chama API."""
        from core.link_shortener import shorten_urls_in_text
        long_text = "oi, " + ("y" * 50)
        with patch("core.link_shortener._call_tinyurl") as mock:
            result = shorten_urls_in_text(long_text)
            assert result == long_text
            mock.assert_not_called()

    def test_min_length_configurable(self):
        """LINK_SHORTENER_MIN_TEXT_LENGTH customiza threshold."""
        os.environ["LINK_SHORTENER_MIN_TEXT_LENGTH"] = "10"
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl", return_value="https://tinyurl.com/x") as mock:
            text = "oi https://google.com"  # 17 chars > 10
            result = shorten_urls_in_text(text)
            assert "https://tinyurl.com/x" in result
            mock.assert_called_once()

    def test_min_length_default_50(self):
        """Default min_length = 50 chars."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            # 49 chars + URL → should skip
            text = "x" * 30 + " https://google.com"
            result = shorten_urls_in_text(text)
            assert "https://google.com" in result
            mock.assert_not_called()

    def test_disabled_shortener_returns_text(self):
        """LINK_SHORTENER_ENABLED=false bypass total."""
        os.environ["LINK_SHORTENER_ENABLED"] = "false"
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            long_text = "olha esse link " + ("x" * 50) + " https://google.com"
            result = shorten_urls_in_text(long_text)
            assert result == long_text
            mock.assert_not_called()

    def test_disabled_shortener_zero_value(self):
        """LINK_SHORTENER_ENABLED=0 bypass total."""
        os.environ["LINK_SHORTENER_ENABLED"] = "0"
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            long_text = "olha esse link " + ("x" * 50) + " https://google.com"
            result = shorten_urls_in_text(long_text)
            assert result == long_text
            mock.assert_not_called()

    def test_skipped_short_message_no_log(self):
        """Skip de msg curta NAO emite log (otimizacao silenciosa)."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            with patch("core.link_shortener.logger") as mock_logger:
                shorten_urls_in_text("oi")
                mock_logger.info.assert_not_called()


class TestShortenOptInPerformance:
    """Testes que verificam o impacto de performance."""

    def test_short_text_zero_http_calls(self):
        """100 msgs curtas → 0 chamadas HTTP."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            for i in range(100):
                shorten_urls_in_text(f"msg {i} simples")
            assert mock.call_count == 0

    def test_mixed_batch_only_long_calls_api(self):
        """Mix de msgs curtas/longas → so longas chamam API."""
        from core.link_shortener import shorten_urls_in_text
        with patch("core.link_shortener._call_tinyurl") as mock:
            mock.return_value = "https://tinyurl.com/x"
            msgs = [
                f"ack {i}" for i in range(70)  # 70 curtas
            ] + [
                f"olha esse link {'x' * 50} https://google.com/page{i}" for i in range(30)  # 30 longas, URLs diferentes
            ]
            for m in msgs:
                shorten_urls_in_text(m)
            # Short msgs: 0 calls. Long msgs: 30 distinct URLs = 30 calls.
            assert mock.call_count == 30
