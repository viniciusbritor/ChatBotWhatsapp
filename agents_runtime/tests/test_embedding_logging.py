"""Tests for embedding diagnostic logging (PHASE 1 - 30/07/2026).

Cobre logging estruturado por tipo de erro:
- openai.RateLimitError -> embedding_rate_limit
- openai.AuthenticationError -> embedding_auth_failed
- openai.APITimeoutError -> embedding_timeout
- Outros -> embedding_other_error

Tambem cobre logging de partial failure em embed_documents.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest


@pytest.mark.asyncio
async def test_embed_query_logs_rate_limit(caplog):
    """openai.RateLimitError -> log 'embedding_rate_limit'."""
    from core import rag

    rate_err = openai.RateLimitError("rate limit", response=MagicMock(), body=None)
    with patch("core.rag.embed_best", side_effect=rate_err):
        with caplog.at_level(logging.WARNING, logger="core.rag"):
            result = await rag.embed_query("texto de teste " * 50)
    assert result is None
    assert any(
        "embedding_rate_limit" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_embed_query_logs_auth_failure(caplog, monkeypatch):
    """openai.AuthenticationError -> log 'embedding_auth_failed' (key prefix safe)."""
    from core import rag

    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc123def456")
    auth_err = openai.AuthenticationError("invalid api key", response=MagicMock(), body=None)
    with patch("core.rag.embed_best", side_effect=auth_err):
        with caplog.at_level(logging.ERROR, logger="core.rag"):
            result = await rag.embed_query("texto de teste")
    assert result is None
    auth_logs = [r for r in caplog.records if "embedding_auth_failed" in r.message]
    assert len(auth_logs) == 1
    assert "sk-abc1***" in auth_logs[0].message
    assert "sk-abc123def456" not in auth_logs[0].message


@pytest.mark.asyncio
async def test_embed_query_logs_timeout(caplog):
    """openai.APITimeoutError -> log 'embedding_timeout'."""
    from core import rag

    timeout_err = openai.APITimeoutError("request timed out")
    with patch("core.rag.embed_best", side_effect=timeout_err):
        with caplog.at_level(logging.WARNING, logger="core.rag"):
            result = await rag.embed_query("texto de teste " * 30)
    assert result is None
    assert any(
        "embedding_timeout" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_embed_query_logs_other_error(caplog):
    """Exception generica -> log 'embedding_other_error'."""
    from core import rag

    other_err = RuntimeError("outro erro qualquer")
    with patch("core.rag.embed_best", side_effect=other_err):
        with caplog.at_level(logging.WARNING, logger="core.rag"):
            result = await rag.embed_query("texto de teste")
    assert result is None
    assert any(
        "embedding_other_error" in record.message
        and "RuntimeError" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_embed_documents_logs_partial_failure(caplog):
    """embed_documents com 1 falha -> log 'embed_documents_partial_failure'."""
    from core import rag

    async def mixed(text):
        if text == "t2":
            return None
        return [0.1, 0.2, 0.3]

    with patch.object(rag, "embed_query", new=AsyncMock(side_effect=mixed)), \
         patch.object(rag, "EMBED_DOCUMENTS_TIMEOUT_SEC", 5.0):
        with caplog.at_level(logging.WARNING, logger="core.rag"):
            result = await rag.embed_documents(["t1", "t2", "t3"])

    assert any(
        "embed_documents_partial_failure" in r.message
        and "chunks=3" in r.message
        and "failures=1" in r.message
        for r in caplog.records
    )
    # Phase 4 fix: manter None nas posicoes com falha, nao mais strips
    assert result == [[0.1, 0.2, 0.3], None, [0.1, 0.2, 0.3]]
