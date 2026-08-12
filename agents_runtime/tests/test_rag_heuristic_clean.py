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
    # Sem DEEPSEEK_API_KEY, o tie-breaker LLM nao roda -> determinismo
    from unittest.mock import patch
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
        assert await is_rag_query("qual meus compromissos de hoje") is False


@pytest.mark.asyncio
async def test_como_listar_arquivos_is_not_rag():
    assert await is_rag_query("como listo os arquivos do Drive") is False


@pytest.mark.asyncio
async def test_quando_reuniao_is_not_rag():
    # Sem DEEPSEEK_API_KEY, o tie-breaker LLM nao roda -> determinismo
    from unittest.mock import patch
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
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


@pytest.mark.asyncio
async def test_sobre_esse_documento_is_rag():
    """Bug que o user reportou: 'Sobre o que é esse documento?' deve is_rag=True."""
    assert await is_rag_query("Sobre o que é esse documento?") is True


@pytest.mark.asyncio
async def test_quem_e_o_autor_is_rag():
    """Bug 2: 'quem é o autor?' apos indexar documento."""
    assert await is_rag_query("quem é o autor?") is True


@pytest.mark.asyncio
async def test_qual_o_tema_is_rag():
    assert await is_rag_query("qual o tema dele?") is True


@pytest.mark.asyncio
async def test_de_que_se_trata_is_rag():
    assert await is_rag_query("de que se trata esse pdf?") is True


@pytest.mark.asyncio
async def test_followup_greeting_is_not_rag():
    """Regressao: 'oi', 'obrigado' continuam False."""
    assert await is_rag_query("oi jen") is False
    assert await is_rag_query("valeu") is False


@pytest.mark.asyncio
async def test_llm_tiebreaker_with_context(monkeypatch):
    """LLM tie-breaker recebe recent_context e retorna True
    para 'Sobre o que é esse documento?' apos indexing."""
    from agent_orchestration.knowledge_retriever import is_rag_query

    fake_ctx = (
        "Jennifer: Feito! Memorei 161 trechos do arquivo "
        "'dissertacao.pdf' no conhecimento privado."
    )
    captured = {}

    async def fake_llm(text, recent_context=""):
        captured["text"] = text
        captured["ctx"] = recent_context
        return True

    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._looks_like_rag_query",
        lambda t: False,
    )
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._llm_is_rag_query",
        fake_llm,
    )

    result = await is_rag_query(
        "Sobre o que é esse documento? quem é o autor?",
        recent_context=fake_ctx,
    )
    assert result is True
    assert captured["ctx"] == fake_ctx


@pytest.mark.asyncio
async def test_recent_indexing_forces_rag(monkeypatch):
    """Apos indexing, qualquer query do mesmo phone vira RAG."""
    from unittest.mock import AsyncMock

    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING,
        is_rag_query,
        register_indexing,
    )
    _RECENT_INDEXING.clear()
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._looks_like_rag_query",
        lambda t: False,
    )
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._llm_is_rag_query",
        AsyncMock(return_value=False),
    )
    phone = "+5511966830020"
    register_indexing(phone)
    assert await is_rag_query("oi", phone=phone) is True
    assert await is_rag_query("obrigado", phone=phone) is True


@pytest.mark.asyncio
async def test_recent_indexing_does_not_affect_other_phone(monkeypatch):
    """Indexing de um phone NAO afeta outro phone."""
    from unittest.mock import AsyncMock

    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING,
        is_rag_query,
        register_indexing,
    )
    _RECENT_INDEXING.clear()
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._looks_like_rag_query",
        lambda t: False,
    )
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._llm_is_rag_query",
        AsyncMock(return_value=False),
    )
    phone_a = "+5511966830020"
    phone_b = "+5511999999999"
    register_indexing(phone_a)
    assert await is_rag_query("oi", phone=phone_a) is True
    assert await is_rag_query("oi", phone=phone_b) is False


@pytest.mark.asyncio
async def test_busque_na_sua_base_is_rag():
    """Keyword 'busque na sua base de conhecimento' (sugestao user 30/07)."""
    assert await is_rag_query("busque na sua base de conhecimento sobre X") is True


@pytest.mark.asyncio
async def test_use_conhecimento_is_rag():
    """Keyword 'use a base de conhecimento' (sugestao user 30/07)."""
    assert await is_rag_query("use a base de conhecimento pra responder") is True


@pytest.mark.asyncio
async def test_o_que_voce_guardou_is_rag():
    """Keyword 'o que voce guardou' (sugestao user 30/07)."""
    assert await is_rag_query("o que voce guardou sobre vendas?") is True


@pytest.mark.asyncio
async def test_recupere_da_base_is_rag():
    """Keyword 'recupere da base' (variante)."""
    assert await is_rag_query("recupere da base o conteudo de 2024") is True


@pytest.mark.asyncio
async def test_recent_indexing_group_scope_forces_rag(monkeypatch):
    """Qualquer membro do grupo pode consultar apos indexing.
    Mesmo um phone NOVO (que nao upou o doc) deve virar RAG
    enquanto o group_jid estiver recente."""
    from unittest.mock import AsyncMock

    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING,
        is_rag_query,
        register_indexing,
    )
    _RECENT_INDEXING.clear()
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._looks_like_rag_query",
        lambda t: False,
    )
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._llm_is_rag_query",
        AsyncMock(return_value=False),
    )
    group_jid = "120363012345678@g.us"
    member_a = "+5511111111111"
    member_b = "+5511222222222"
    register_indexing(group_jid)
    assert await is_rag_query("o que é isso?", phone=group_jid) is True
    assert await is_rag_query("o que é isso?", phone=member_a) is False
    assert await is_rag_query("o que é isso?", phone=member_b) is False


@pytest.mark.asyncio
async def test_recent_indexing_individual_does_not_affect_group(monkeypatch):
    """Indexing de um phone NAO afeta outros phones (escopo 1:1)."""
    from unittest.mock import AsyncMock

    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING,
        is_rag_query,
        register_indexing,
    )
    _RECENT_INDEXING.clear()
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._looks_like_rag_query",
        lambda t: False,
    )
    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever._llm_is_rag_query",
        AsyncMock(return_value=False),
    )
    phone_individual = "+5511966830020"
    phone_other = "+5511999999999"
    register_indexing(phone_individual)
    assert await is_rag_query("olá", phone=phone_individual) is True
    assert await is_rag_query("olá", phone=phone_other) is False


@pytest.mark.asyncio
async def test_recent_indexing_window_default(monkeypatch):
    """RECENT_INDEXING_WINDOW_SEC default deve ser 1800 (30min)."""
    from agent_orchestration import knowledge_retriever

    monkeypatch.setattr(
        "agent_orchestration.knowledge_retriever.os.getenv",
        lambda k, default=None: default,
    )
    assert knowledge_retriever.RECENT_INDEXING_WINDOW_SEC == 1800

