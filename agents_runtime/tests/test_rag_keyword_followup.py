"""Testes para Phase A: keywords conversacionais RAG (loop RAG pt 2).

Cobre o fix do bug 'bot esquece arquivo recem-armazenado':
user: 'Qual o nome do arquivo, como vc memorizou?'
bot deveria detectar RAG via keywords conversacionais.
"""
import pytest


@pytest.mark.asyncio
async def test_qual_arquivo_como_memorizou_is_rag():
    """'Qual o nome do arquivo, como vc memorizou?' deve is_rag=True."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query(
        "Qual o nome do arquivo, como vc memorizou?",
    ) is True


@pytest.mark.asyncio
async def test_qual_o_arquivo_como_memorizou_is_rag():
    """Variacao sem interrogacao: 'qual o arquivo como memorizou' is_rag=True."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query(
        "qual o arquivo como memorizou",
    ) is True


@pytest.mark.asyncio
async def test_o_que_memorizou_is_rag():
    """'o que voce memorizou' is_rag=True (ja existia)."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query("o que voce memorizou") is True


@pytest.mark.asyncio
async def test_que_guardou_is_rag():
    """'que guardou' is_rag=True (novo)."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query("que guardou?") is True


@pytest.mark.asyncio
async def test_como_guardou_is_rag():
    """'como guardou' is_rag=True (novo)."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query("como voce guardou isso?") is True


@pytest.mark.asyncio
async def test_conteudo_da_introducao_is_rag():
    """'conteudo da introducao' is_rag=True (novo)."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query("me passa o conteudo da introducao") is True


@pytest.mark.asyncio
async def test_oi_simples_is_not_rag():
    """'oi' continua NAO sendo RAG (regressao)."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    assert await is_rag_query("oi") is False
    assert await is_rag_query("tudo bem?") is False


@pytest.mark.asyncio
async def test_quais_meus_emails_is_not_rag():
    """'quais meus emails' continua NAO sendo RAG (regressao)."""
    from agent_orchestration.knowledge_retriever import is_rag_query
    from unittest.mock import patch

    # Sem DEEPSEEK_API_KEY, o tie-breaker LLM nao roda -> determinismo
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
        assert await is_rag_query("quais meus emails?") is False
