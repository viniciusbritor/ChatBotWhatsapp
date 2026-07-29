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