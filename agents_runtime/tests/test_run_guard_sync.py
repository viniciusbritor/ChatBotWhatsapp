"""Tests para run_guard_sync (Fase A.2 30/07/2026).

Garante que o caminho sync produz o mesmo resultado que o grafo
LangGraph, sem overhead do CompiledStateGraph. Suite roda contra
sync path com todos os nodes mockados.
"""
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_run_guard_sync_calls_nodes_in_order():
    """Sync deve chamar jennifier -> classify_intent -> guardian -> reply,
    e sOMENTE manager se verdict=allow."""
    from agent_orchestration import graph as graph_module
    from agent_orchestration.graph import run_guard_sync

    calls = []

    async def j(state):
        calls.append("j")
        state["guardian_decision"] = {"verdict": "allow"}
        return state

    async def c(state):
        calls.append("c")
        return state

    async def g(state):
        calls.append("g")
        state["guardian_decision"] = {"verdict": "allow"}
        return state

    async def m(state):
        calls.append("m")
        state["prefetch"] = "ok"
        return state

    async def r(state):
        calls.append("r")
        return state

    with patch.object(graph_module, "jennifier_node", new=j), \
         patch.object(graph_module, "classify_intent_node", new=c), \
         patch.object(graph_module, "guard_node", new=g), \
         patch.object(graph_module, "manager_node", new=m), \
         patch.object(graph_module, "reply_node", new=r):
        result = await run_guard_sync({})

    assert calls == ["j", "c", "g", "m", "r"]
    assert result is not None
    assert result["prefetch"] == "ok"


@pytest.mark.asyncio
async def test_run_guard_sync_skips_manager_when_deny():
    """Verdict=deny: manager NAO deve ser chamado (early exit)."""
    from agent_orchestration import graph as graph_module
    from agent_orchestration.graph import run_guard_sync

    calls = []

    async def j(state):
        calls.append("j")
        return state

    async def c(state):
        calls.append("c")
        return state

    async def g(state):
        calls.append("g")
        state["guardian_decision"] = {"verdict": "deny"}
        return state

    async def m(state):
        calls.append("m")
        raise AssertionError("manager should NOT run on deny")

    async def r(state):
        calls.append("r")
        return state

    with patch.object(graph_module, "jennifier_node", new=j), \
         patch.object(graph_module, "classify_intent_node", new=c), \
         patch.object(graph_module, "guard_node", new=g), \
         patch.object(graph_module, "manager_node", new=m), \
         patch.object(graph_module, "reply_node", new=r):
        result = await run_guard_sync({})

    assert calls == ["j", "c", "g", "r"]
    assert result is not None


@pytest.mark.asyncio
async def test_run_guard_sync_skips_manager_when_request_oauth():
    """Verdict=request_oauth: manager NAO deve ser chamado."""
    from agent_orchestration import graph as graph_module
    from agent_orchestration.graph import run_guard_sync

    calls = []

    async def j(state):
        calls.append("j")
        return state

    async def c(state):
        calls.append("c")
        return state

    async def g(state):
        calls.append("g")
        state["guardian_decision"] = {"verdict": "request_oauth"}
        return state

    async def m(state):
        calls.append("m")
        raise AssertionError("manager should NOT run on request_oauth")

    async def r(state):
        calls.append("r")
        return state

    with patch.object(graph_module, "jennifier_node", new=j), \
         patch.object(graph_module, "classify_intent_node", new=c), \
         patch.object(graph_module, "guard_node", new=g), \
         patch.object(graph_module, "manager_node", new=m), \
         patch.object(graph_module, "reply_node", new=r):
         result = await run_guard_sync({})

    assert calls == ["j", "c", "g", "r"]
    assert result is not None


@pytest.mark.asyncio
async def test_run_guard_sync_preserves_initial_state():
    """Sync NAO muta o initial_state recebido; retorna copia."""
    from agent_orchestration.graph import run_guard_sync

    initial = {
        "instance": "Jennifer",
        "phone": "+5511",
        "intent": {"is_rag": True},
        "masked_text": "test",
    }

    async def j(state):
        state["jennifier_visited"] = True
        return state

    async def c(state):
        return state

    async def g(state):
        state["guardian_decision"] = {"verdict": "allow"}
        return state

    async def m(state):
        state["prefetch"] = "ok"
        return state

    async def r(state):
        return state

    with patch("agent_orchestration.graph.jennifier_node", new=j), \
         patch("agent_orchestration.graph.classify_intent_node", new=c), \
         patch("agent_orchestration.graph.guard_node", new=g), \
         patch("agent_orchestration.graph.manager_node", new=m), \
         patch("agent_orchestration.graph.reply_node", new=r):
        result = await run_guard_sync(initial)

    assert "jennifier_visited" not in initial
    assert "prefetch" not in initial
    assert result["jennifier_visited"] is True
    assert result["prefetch"] == "ok"
