"""Testes do FIX prefetch: filtro curriculo_padrao tambem no prefetch_drive."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


def _sample_files():
    return [
        {"id": "1ABC", "name": "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"},
        {"id": "1DEF", "name": "ViniciusBritoRocha_curriculo_atualizado.pdf"},
        {"id": "1GHI", "name": "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"},
    ]


@pytest.mark.asyncio
async def test_prefetch_drive_prioritizes_curriculo_padrao():
    """Prefetch deve priorizar arquivo curriculo_padrao no topo."""
    from orchestrator import _prefetch_drive

    async def fake_search_files(phone, query_text="", **kwargs):
        return {"files": _sample_files(), "count": 3}

    async def fake_get_fact(key, phone):
        if key == "curriculo_padrao":
            return "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"
        return None

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await _prefetch_drive(
            phone="5511966830020",
            query_text="busque meu curriculo no gdrive",
            instance="Jennifer",
        )

    assert result is not None
    files = json.loads(result)
    assert files[0]["name"] == "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"
    assert files[0]["id"] == "1ABC"
    file_names = [f["name"] for f in files]
    assert file_names == [
        "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
        "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
        "ViniciusBritoRocha_curriculo_atualizado.pdf",
    ]


@pytest.mark.asyncio
async def test_prefetch_drive_no_op_when_no_fact():
    """Sem fact curriculo_padrao, o prefetch NAO reordena."""
    from orchestrator import _prefetch_drive

    async def fake_search_files(phone, query_text="", **kwargs):
        return {"files": _sample_files(), "count": 3}

    async def fake_get_fact(key, phone):
        return None

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await _prefetch_drive(
            phone="5511966830020",
            query_text="busque meu curriculo no gdrive",
            instance="Jennifer",
        )

    assert result is not None
    files = json.loads(result)
    file_names = [f["name"] for f in files]
    assert file_names == [
        "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
        "ViniciusBritoRocha_curriculo_atualizado.pdf",
        "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
    ]


@pytest.mark.asyncio
async def test_prefetch_drive_skips_non_curriculo_queries():
    """Para queries sem curriculum, NAO chama get_fact_by_key."""
    from orchestrator import _prefetch_drive

    async def fake_search_files(phone, query_text="", **kwargs):
        return {"files": [], "count": 0}

    get_fact_calls = []

    async def fake_get_fact(key, phone):
        get_fact_calls.append((key, phone))
        return None

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await _prefetch_drive(
            phone="5511966830020",
            query_text="ata de reuniao de 15 de julho",
            instance="Jennifer",
        )

    assert result is None  # empty result
    assert get_fact_calls == [], "get_fact_by_key NAO deveria ser chamado"


@pytest.mark.asyncio
async def test_prefetch_drive_handles_firestore_error_gracefully():
    """Se Firestore falha no get_fact_by_key, o prefetch continua normalmente."""
    from orchestrator import _prefetch_drive

    async def fake_search_files(phone, query_text="", **kwargs):
        return {"files": _sample_files(), "count": 3}

    async def fake_get_fact(key, phone):
        raise RuntimeError("firestore_unavailable")

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await _prefetch_drive(
            phone="5511966830020",
            query_text="busque meu curriculo no gdrive",
            instance="Jennifer",
        )

    assert result is not None
    files = json.loads(result)
    assert len(files) == 3
