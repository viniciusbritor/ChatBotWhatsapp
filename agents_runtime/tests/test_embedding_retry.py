"""Testes para retry com exponential backoff (PHASE 3)."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest


@pytest.mark.asyncio
async def test_embed_query_retries_rate_limit_succeeds(caplog):
    """1a chamada: RateLimitError. 2a chamada: sucesso."""
    from core import rag

    rate_err = openai.RateLimitError("rate", response=MagicMock(), body=None)
    success_vector = [0.1, 0.2, 0.3]

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise rate_err
        return success_vector

    with caplog.at_level(logging.INFO, logger="core.rag"):
        with patch("core.rag.embed_best", side_effect=side_effect):
            with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
                result = await rag.embed_query("texto de teste " * 50)

    assert result == success_vector
    assert call_count["n"] == 2
    mock_sleep.assert_called_once_with(1)
    assert any("embedding_rate_limit_retry" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_embed_query_exhausts_retries_on_rate_limit(caplog):
    """3 RateLimitError seguidas -> return None + log exhausted."""
    from core import rag

    rate_err = openai.RateLimitError("rate", response=MagicMock(), body=None)

    with caplog.at_level(logging.INFO, logger="core.rag"):
        with patch("core.rag.embed_best", side_effect=rate_err):
            with patch("asyncio.sleep", new=AsyncMock()):
                result = await rag.embed_query("texto de teste " * 50)

    assert result is None
    exhausted = [r for r in caplog.records if "exhausted" in r.message]
    assert len(exhausted) == 1


@pytest.mark.asyncio
async def test_embed_query_retries_timeout_succeeds(caplog):
    """1a chamada: APITimeoutError. 2a chamada: sucesso."""
    from core import rag

    timeout_err = openai.APITimeoutError("timeout")
    success_vector = [0.4, 0.5]

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise timeout_err
        return success_vector

    with caplog.at_level(logging.INFO, logger="core.rag"):
        with patch("core.rag.embed_best", side_effect=side_effect):
            with patch("asyncio.sleep", new=AsyncMock()):
                result = await rag.embed_query("texto de teste " * 30)

    assert result == success_vector
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_embed_query_no_retry_on_auth_error(caplog):
    """AuthenticationError NAO faz retry (key invalida nao vai virar
    valida com sleep)."""
    from core import rag

    auth_err = openai.AuthenticationError("invalid key", response=MagicMock(), body=None)
    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        raise auth_err

    with caplog.at_level(logging.INFO, logger="core.rag"):
        with patch("core.rag.embed_best", side_effect=side_effect):
            with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
                result = await rag.embed_query("texto")

    assert result is None
    assert call_count["n"] == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_embed_query_backoff_progression(caplog):
    """Tentativa 1: wait 1s. Tentativa 2: wait 2s. Tentativa 3: return None."""
    from core import rag

    rate_err = openai.RateLimitError("rate", response=MagicMock(), body=None)
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        raise rate_err

    with caplog.at_level(logging.INFO, logger="core.rag"):
        with patch("core.rag.embed_best", side_effect=side_effect):
            with patch("asyncio.sleep", new=fake_sleep):
                result = await rag.embed_query("texto")

    assert result is None
    assert call_count["n"] == 3
    assert sleep_calls == [1, 2]
