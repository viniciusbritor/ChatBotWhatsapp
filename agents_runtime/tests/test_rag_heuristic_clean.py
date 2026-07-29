"""Tests for cleaned RAG heuristic (F4d.9).

Verifies that:
- Generic question keywords ('?', 'quais', 'como', 'quando') do NOT
  trigger ``is_rag=True`` anymore.
- Strong RAG markers ('tem alguma coisa sobre', 'existe algum documento')
  DO trigger ``is_rag=True``.
- Personal intents (is_email, is_calendar, is_drive) are unaffected.
"""
import pytest

from agent_orchestration.knowledge_retriever import (
    _looks_like_rag_query,
    is_rag_query,
)


@pytest.mark.asyncio
async def test_quais_emails_is_not_rag():
    assert await is_rag_query("quais meus ultimos 5 emails?") is False


@pytest.mark.asyncio
async def test_qual_compromissos_is_not_rag():
    assert await is_rag_query("qual meus compromissos de hoje") is False


@pytest.mark.asyncio
async def test_como_listar_arquivos_is_not_rag():
    assert await is_rag_query("como listo os arquivos do Drive") is False


@pytest.mark.asyncio
async def test_quando_reuniao_is_not_rag():
    assert await is_rag_query("quando é a proxima reuniao") is False


@pytest.mark.asyncio
async def test_strong_marker_still_triggers_rag():
    assert await is_rag_query("tem alguma coisa sobre o CDC?") is True


@pytest.mark.asyncio
async def test_existe_documento_still_triggers_rag():
    assert await is_rag_query("existe algum documento sobre dissertação?") is True


@pytest.mark.asyncio
async def test_memorizei_still_triggers_rag():
    """Direct verb form should still flag RAG via the strong markers
    in RAG_KEYWORDS (not QUESTION_KEYWORDS)."""
    assert await is_rag_query("o que eu memorizei sobre vendas") is True


@pytest.mark.asyncio
async def test_greeting_is_not_rag():
    assert await is_rag_query("oi jen") is False


def test_looks_like_rag_query_pure_heuristic():
    assert _looks_like_rag_query("tem alguma coisa sobre X") is True
    assert _looks_like_rag_query("existe algum documento Y") is True
    assert _looks_like_rag_query("qual é o email") is False
    assert _looks_like_rag_query("?") is False
    assert _looks_like_rag_query("quais emails") is False