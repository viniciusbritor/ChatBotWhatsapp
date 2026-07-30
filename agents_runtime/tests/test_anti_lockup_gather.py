"""Tests for anti-lockup patches (Fase 0.5, Patch 2).

Covers:
- ``_execute_multi_specialists_parallel`` per-task timeout preserves
  partial results when one agent hangs.
- Timeout per task surfaces in the `path` for observability.
- ``_prefetch_drive_multi`` returns empty results when gather exceeds
  PREFETCH_DRIVE_MULTI_TIMEOUT_SEC.
- ``embed_documents`` returns None when gather exceeds
  EMBED_DOCUMENTS_TIMEOUT_SEC.
- Normal-path behavior unchanged when all sub-tasks complete fast.
"""
import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_multi_specialist_timeout_keeps_fast_agent():
    """Per-task timeout: fast agent reply is preserved, slow agent
    is dropped with agent_timeout error."""
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def mixed_execute_agent(agent, text, payload, extra):
        if agent["id"] == "manager-email":
            await asyncio.sleep(0.05)
            return {
                "reply": "emails rapidos",
                "metadata": {"agent_id": "manager-email"},
            }
        await asyncio.sleep(5)
        return {"reply": "travado", "metadata": {"agent_id": agent["id"]}}

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=mixed_execute_agent)

    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async), \
         patch("orchestrator.MULTI_SPECIALIST_TIMEOUT_SEC", 0.3):
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

    assert "emails rapidos" in result["reply"]
    assert "agent-knowledge-retriever" not in result["reply"]


@pytest.mark.asyncio
async def test_multi_specialist_timeout_records_in_path():
    """Per-task timeout must surface in path for observability."""
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def hang(agent, text, payload, extra):
        await asyncio.sleep(5)
        return {"reply": "x", "metadata": {}}

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=hang)

    path: List[Dict[str, Any]] = []
    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async), \
         patch("orchestrator.MULTI_SPECIALIST_TIMEOUT_SEC", 0.1):
        await _execute_multi_specialists_parallel(
            ["manager-email", "agent-knowledge-retriever"],
            {"is_email": True, "is_rag": True},
            {},
            "teste",
            {},
            "jennifer",
            "+5511966830020",
            "Vinicius",
            path,
        )

    timeout_entries = [
        e for e in path
        if e.get("phase") == "multi_specialist_task_timeout"
    ]
    assert len(timeout_entries) == 2
    assert timeout_entries[0]["timeout_sec"] == 0.1
    assert {e["agent_id"] for e in timeout_entries} == {
        "manager-email", "agent-knowledge-retriever",
    }


@pytest.mark.asyncio
async def test_multi_specialist_all_timeout_returns_error():
    """When all agents time out, return multi_agent_empty error."""
    from orchestrator import _execute_multi_specialists_parallel

    def fake_get_agent(agent_id):
        return {"id": agent_id, "name": agent_id, "system_prompt": "", "tools": []}

    async def hang(agent, text, payload, extra):
        await asyncio.sleep(5)
        return {"reply": "x", "metadata": {}}

    fake_get_agent_sync = MagicMock(side_effect=fake_get_agent)
    fake_execute_agent_async = AsyncMock(side_effect=hang)

    with patch("orchestrator.get_agent", fake_get_agent_sync), \
         patch("orchestrator._execute_agent", fake_execute_agent_async), \
         patch("orchestrator.MULTI_SPECIALIST_TIMEOUT_SEC", 0.1):
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

    assert result["metadata"]["error"] == "multi_agent_empty"
    assert result["metadata"]["status_code"] == 500


@pytest.mark.asyncio
async def test_prefetch_drive_multi_timeout_returns_none():
    from orchestrator import _prefetch_drive_multi

    async def hanging(*args, **kwargs):
        await asyncio.sleep(5)
        return "result"

    with patch("orchestrator._prefetch_drive", new=AsyncMock(side_effect=hanging)), \
         patch("orchestrator._prefetch_drive_docs", new=AsyncMock(side_effect=hanging)), \
         patch("orchestrator.PREFETCH_DRIVE_MULTI_TIMEOUT_SEC", 0.1):
        result = await _prefetch_drive_multi("+5511966830020", "qualquer texto", "jennifer")

    assert result is None


@pytest.mark.asyncio
async def test_prefetch_drive_multi_picks_best_under_timeout():
    from orchestrator import _prefetch_drive_multi

    good_payload = json.dumps([{"id": "f1"}, {"id": "f2"}, {"id": "f3"}])

    async def docs(*args, **kwargs):
        return good_payload

    async def empty(*args, **kwargs):
        await asyncio.sleep(0.05)
        return ""

    pdr_drive = AsyncMock(side_effect=empty)
    pdr_docs = AsyncMock(side_effect=docs)

    with patch("orchestrator._prefetch_drive", new=pdr_drive), \
         patch("orchestrator._prefetch_drive_docs", new=pdr_docs), \
         patch("orchestrator.PREFETCH_DRIVE_MULTI_TIMEOUT_SEC", 1.0):
        result = await _prefetch_drive_multi("+5511966830020", "teste", "jennifer")

    assert result is not None
    assert "f1" in result


@pytest.mark.asyncio
async def test_embed_documents_normal_path():
    from core import rag

    async def fake_embed_query(text):
        return [0.1, 0.2, 0.3]

    with patch.object(rag, "embed_query", new=AsyncMock(side_effect=fake_embed_query)), \
         patch.object(rag, "EMBED_DOCUMENTS_TIMEOUT_SEC", 5.0):
        vectors = await rag.embed_documents(["texto 1", "texto 2"])

    assert vectors is not None
    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embed_documents_timeout_returns_none():
    from core import rag

    async def hanging_embed(text):
        await asyncio.sleep(5)
        return [0.1]

    with patch.object(rag, "embed_query", new=AsyncMock(side_effect=hanging_embed)), \
         patch.object(rag, "EMBED_DOCUMENTS_TIMEOUT_SEC", 0.1):
        result = await rag.embed_documents(["t1", "t2", "t3"])

    assert result is None


@pytest.mark.asyncio
async def test_embed_documents_partial_none_returns_filtered():
    """Phase 4: partial success. 1 falha em 3 -> retorna 2 vectors."""
    from core import rag

    async def mixed(text):
        if text == "t2":
            return None
        return [0.1, 0.2]

    with patch.object(rag, "embed_query", new=AsyncMock(side_effect=mixed)), \
         patch.object(rag, "EMBED_DOCUMENTS_TIMEOUT_SEC", 5.0):
        result = await rag.embed_documents(["t1", "t2", "t3"])

    assert result == [[0.1, 0.2], [0.1, 0.2]]
