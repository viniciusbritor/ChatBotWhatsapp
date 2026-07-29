"""Tests for multi-agent parallel routing (F4d.9).

Covers:
- ``_resolve_agents_for_intents`` returns the right list per intent.
- When multiple intents fire (e.g. is_email + is_rag), both agents
  are returned, NOT just the first one.
- ``_execute_multi_specialists_parallel`` runs agents concurrently
  via asyncio.gather and concatenates non-empty replies.
- Errors in one agent don't break the others.
- Single-agent path still works.
"""
import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolve_single_intent():
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents(
        {"is_email": True, "is_rag": False}, "jennifer"
    )
    assert agents == ["manager-email"]


@pytest.mark.asyncio
async def test_resolve_multi_intent_runs_in_parallel():
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents(
        {"is_email": True, "is_drive": True, "is_rag": False}, "jennifer"
    )
    assert "manager-email" in agents
    assert "manager-drive" in agents
    assert "agent-knowledge-retriever" not in agents
    assert len(agents) == 2


@pytest.mark.asyncio
async def test_resolve_rag_alone_includes_retriever():
    """F4d.9: defense-in-depth removes retriever only when personal
    intent is present. RAG-only queries keep the retriever."""
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents(
        {"is_email": False, "is_rag": True, "is_drive": False}, "jennifer"
    )
    assert agents == ["agent-knowledge-retriever"]


@pytest.mark.asyncio
async def test_resolve_dedup_when_intents_overlap():
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents(
        {"is_email": True, "is_calendar": True, "is_drive": True}, "jennifer"
    )
    assert len(agents) == 3
    assert "manager-email" in agents
    assert "manager-calendar" in agents
    assert "manager-drive" in agents


@pytest.mark.asyncio
async def test_resolve_no_intent_returns_empty():
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents({"is_greeting": True}, "jennifer")
    assert agents == []


@pytest.mark.asyncio
async def test_resolve_returns_morality_for_gross():
    from orchestrator import _resolve_agents_for_intents

    agents = _resolve_agents_for_intents(
        {"is_gross": True, "is_email": True}, "jennifer"
    )
    assert agents == ["agent-morality"]


@pytest.mark.asyncio
async def test_execute_multi_specialists_parallel_merges_replies():
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def fake_execute_agent(agent, text, payload, extra):
        return {
            "reply": f"{agent['id']} reply for {text}",
            "delay_ms": 100,
            "presence": "composing",
            "metadata": {"agent_id": agent["id"]},
        }

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=fake_execute_agent)
    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async):
        result = await _execute_multi_specialists_parallel(
            ["manager-email", "agent-knowledge-retriever"],
            {"is_email": True, "is_rag": True},
            {"phone": "+5511966830020"},
            "quais meus ultimos 5 emails?",
            {},
            "jennifer",
            "+5511966830020",
            "Vinicius",
            [],
        )

    assert "multi_agent" in result["metadata"]
    assert result["metadata"]["multi_agent"] is True
    assert result["metadata"]["agents_executed"] == [
        "manager-email",
        "agent-knowledge-retriever",
    ]
    assert "manager-email reply" in result["reply"]
    assert "agent-knowledge-retriever reply" in result["reply"]
    assert "---" in result["reply"]


@pytest.mark.asyncio
async def test_execute_multi_handles_partial_failure():
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def fake_execute_agent(agent, text, payload, extra):
        if agent["id"] == "manager-email":
            return {
                "reply": "Aqui estao os emails",
                "delay_ms": 100,
                "metadata": {"agent_id": "manager-email"},
            }
        raise RuntimeError("agent crashed")

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=fake_execute_agent)
    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async):
        result = await _execute_multi_specialists_parallel(
            ["manager-email", "agent-knowledge-retriever"],
            {"is_email": True, "is_rag": True},
            {"phone": "+5511966830020"},
            "teste",
            {},
            "jennifer",
            "+5511966830020",
            "Vinicius",
            [],
        )

    assert "Aqui estao os emails" in result["reply"]
    assert "agent-knowledge-retriever" not in result["reply"]


@pytest.mark.asyncio
async def test_execute_multi_returns_error_when_all_fail():
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def fake_execute_agent(agent, text, payload, extra):
        return {"reply": "", "metadata": {}}

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=fake_execute_agent)
    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async):
        result = await _execute_multi_specialists_parallel(
            ["manager-email", "agent-knowledge-retriever"],
            {"is_email": True, "is_rag": True},
            {},
            "teste",
            {},
            "jennifer",
            "+5511966830020",
            "Vinicius",
            [],
        )

    assert result["metadata"]["error"] == "multi_agent_empty"