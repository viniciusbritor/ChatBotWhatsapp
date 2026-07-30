"""Tests for defense-in-depth in multi-agent routing (F4d.9).

When a personal intent (email/calendar/drive) is present, the
knowledge-retriever must be excluded from the agent list. RAG tool
calls happen via the personal agent's own tool registry.
"""
from orchestrator import _resolve_agents_for_intents


def test_email_intent_alone_returns_only_manager_email():
    agents = _resolve_agents_for_intents({"is_email": True}, "jennifer")
    assert agents == ["manager-email"]
    assert "agent-knowledge-retriever" not in agents


def test_email_plus_rag_intent_drops_retriever():
    """Even when the heuristic over-fires is_rag=True, the router
    must drop the retriever so the personal agent executes cleanly."""
    agents = _resolve_agents_for_intents(
        {"is_email": True, "is_rag": True}, "jennifer"
    )
    assert agents == ["manager-email"]
    assert "agent-knowledge-retriever" not in agents


def test_calendar_plus_rag_drops_retriever():
    agents = _resolve_agents_for_intents(
        {"is_calendar": True, "is_rag": True}, "jennifer"
    )
    assert agents == ["manager-calendar"]


def test_drive_plus_rag_drops_retriever():
    agents = _resolve_agents_for_intents(
        {"is_drive": True, "is_rag": True}, "jennifer"
    )
    assert agents == ["manager-drive"]


def test_all_personal_intents_keeps_only_managers():
    agents = _resolve_agents_for_intents(
        {
            "is_email": True,
            "is_calendar": True,
            "is_drive": True,
            "is_rag": True,
        },
        "jennifer",
    )
    assert "agent-knowledge-retriever" not in agents
    assert sorted(agents) == sorted(["manager-email", "manager-calendar", "manager-drive"])


def test_rag_alone_keeps_retriever():
    agents = _resolve_agents_for_intents({"is_rag": True}, "jennifer")
    assert agents == ["agent-knowledge-retriever"]
def test_filename_hint_with_recent_indexing_forces_retriever(monkeypatch):
    """Filename .pdf + recent indexing (escopo individual) bypassa
    defense-in-depth: mesmo com is_drive True, retriever e preferido."""
    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING, register_indexing,
    )
    _RECENT_INDEXING.clear()
    register_indexing("+5511966830020")
    agents = _resolve_agents_for_intents(
        {"is_drive": True, "is_rag": True},
        "jennifer",
        masked_text="conteudo do arquivo cdc-portugues-2013.pdf",
        scope_key="+5511966830020",
    )
    assert agents == ["agent-knowledge-retriever"]


def test_filename_hint_with_group_recent_indexing_forces_retriever(monkeypatch):
    """Filename .pdf + recent indexing em grupo bypassa defense-in-depth
    para qualquer membro do grupo."""
    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING, register_indexing,
    )
    _RECENT_INDEXING.clear()
    register_indexing("120363012345678@g.us")
    agents = _resolve_agents_for_intents(
        {"is_drive": True, "is_rag": True},
        "jennifer",
        masked_text="resumo do relatorio.docx",
        scope_key="120363012345678@g.us",
    )
    assert agents == ["agent-knowledge-retriever"]


def test_filename_hint_without_recent_indexing_keeps_drive(monkeypatch):
    """Filename sem indexing recente NAO bypassa defense-in-depth
    (nao ha documento indexado, Drive e o caminho correto)."""
    from agent_orchestration.knowledge_retriever import _RECENT_INDEXING

    _RECENT_INDEXING.clear()
    agents = _resolve_agents_for_intents(
        {"is_drive": True, "is_rag": True},
        "jennifer",
        masked_text="leia o arquivo relatorio.pdf",
        scope_key="+5511966830020",
    )
    assert "agent-knowledge-retriever" not in agents
    assert "manager-drive" in agents


def test_filename_unsupported_extension_no_bypass(monkeypatch):
    """Extensao nao suportada (ex: .exe, .dmg) NAO dispara bypass."""
    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING, register_indexing,
    )
    _RECENT_INDEXING.clear()
    register_indexing("+5511966830020")
    agents = _resolve_agents_for_intents(
        {"is_drive": True},
        "jennifer",
        masked_text="abrir o malware.exe",
        scope_key="+5511966830020",
    )
    assert "agent-knowledge-retriever" not in agents
    assert "manager-drive" in agents


def test_non_filename_with_recent_indexing_uses_defense_in_depth(monkeypatch):
    """Sem filename + recent indexing: defense-in-depth ainda ativo."""
    from agent_orchestration.knowledge_retriever import (
        _RECENT_INDEXING, register_indexing,
    )
    _RECENT_INDEXING.clear()
    register_indexing("+5511966830020")
    agents = _resolve_agents_for_intents(
        {"is_email": True, "is_rag": True},
        "jennifer",
        masked_text="qual meu compromisso",
        scope_key="+5511966830020",
    )
    assert "agent-knowledge-retriever" not in agents
    assert "manager-email" in agents
