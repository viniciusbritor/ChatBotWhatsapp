"""Testes do FIX Bug #1B (15/08/2026): filtro curriculo_padrao em search_drive_files.

Quando o usuario ja marcou um arquivo como padrao via
``memory.save_fact(key=curriculo_padrao)``, a tool ``search_drive_files``
deve priorizar esse arquivo no topo do resultado para que o LLM nao
precise adivinhar entre copias duplicadas. Estes testes cobrem:
- Filtro prioriza arquivo padrao no topo.
- Filtro NAO esconde os outros arquivos.
- Filtro NAO dispara para queries sem keyword (curriculo/cv).
- Filtro NAO dispara quando nao ha fact salvo.
- Opt-out ``apply_default_filter=False`` retorna resultado original.
- ``get_fact_by_key`` retorna value quando doc existe.
- ``get_fact_by_key`` retorna None quando doc nao existe.
- ``get_fact_by_key`` retorna None quando Firestore indisponivel.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ============================================================
# Testes da funcao ``get_fact_by_key`` em tools.memory
# ============================================================


@pytest.mark.asyncio
async def test_get_fact_by_key_returns_value_when_present():
    """Quando o fact existe, retorna o value."""
    from tools.memory import get_fact_by_key

    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {"key": "curriculo_padrao", "value": "Curriculo.pdf"}

    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_doc

    fake_subcol = MagicMock()
    fake_subcol.document.return_value = fake_doc_ref

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_subcol

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = fake_user_doc

    with patch("tools.memory._get_firestore", return_value=fake_db):
        result = await get_fact_by_key("curriculo_padrao", "5511966830020")
    assert result == "Curriculo.pdf"


@pytest.mark.asyncio
async def test_get_fact_by_key_returns_none_when_missing():
    """Quando o fact NAO existe, retorna None."""
    from tools.memory import get_fact_by_key

    fake_doc = MagicMock()
    fake_doc.exists = False

    fake_doc_ref = MagicMock()
    fake_doc_ref.get.return_value = fake_doc

    fake_subcol = MagicMock()
    fake_subcol.document.return_value = fake_doc_ref

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_subcol

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = fake_user_doc

    with patch("tools.memory._get_firestore", return_value=fake_db):
        result = await get_fact_by_key("curriculo_padrao", "5511966830020")
    assert result is None


@pytest.mark.asyncio
async def test_get_fact_by_key_returns_none_when_firestore_unavailable():
    """Quando Firestore indisponivel, retorna None."""
    from tools.memory import get_fact_by_key

    with patch("tools.memory._get_firestore", return_value=None):
        assert await get_fact_by_key("curriculo_padrao", "5511966830020") is None
        assert await get_fact_by_key("", "5511966830020") is None
        assert await get_fact_by_key("curriculo_padrao", "") is None


# ============================================================
# Testes do pre-filtro em deepagent_layer/tools.search_drive_files
# ============================================================


def _sample_files():
    return [
        {
            "id": "1ABC",
            "name": "ViniciusBritoRocha_curriculo_atualizado.pdf",
            "mime_type": "application/pdf",
            "modified": "2026-01-27T00:00:00Z",
        },
        {
            "id": "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-",
            "name": "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
            "mime_type": "application/pdf",
            "modified": "2026-08-15T04:39:12Z",
        },
        {
            "id": "1h6YYC76Q6YkoRjRPoXuZQgHxBIpDgS_c",
            "name": "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf",
            "mime_type": "application/pdf",
            "modified": "2026-08-15T04:39:12Z",
        },
    ]


@pytest.mark.asyncio
async def test_search_drive_files_prioritizes_curriculo_padrao():
    """Quando ha fact curriculo_padrao salvo, o arquivo padrao fica no topo."""
    from deepagent_layer.tools import _build_drive_tools

    tools = _build_drive_tools()
    search_drive_files = next(t for t in tools if t.name == "search_drive_files")

    upstream_result = {"files": _sample_files(), "count": 3}

    async def fake_search_files(**kwargs):
        return upstream_result

    async def fake_get_fact(key, phone):
        return "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await search_drive_files.ainvoke(
            {
                "phone": "5511966830020",
                "query": "curriculo",
                "max_results": 20,
            }
        )

    assert result["default_file_id"] == "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-"
    assert result["default_file_name"] == "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"
    assert result["files"][0]["id"] == "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-"
    file_ids = [f["id"] for f in result["files"]]
    assert "1ABC" in file_ids
    assert "1h6YYC76Q6YkoRjRPoXuZQgHxBIpDgS_c" in file_ids


@pytest.mark.asyncio
async def test_search_drive_files_no_op_when_no_fact():
    """Quando NAO ha fact curriculo_padrao, o resultado NAO e reordenado."""
    from deepagent_layer.tools import _build_drive_tools

    tools = _build_drive_tools()
    search_drive_files = next(t for t in tools if t.name == "search_drive_files")

    upstream_result = {"files": _sample_files(), "count": 3}

    async def fake_search_files(**kwargs):
        return upstream_result

    async def fake_get_fact(key, phone):
        return None

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await search_drive_files.ainvoke(
            {
                "phone": "5511966830020",
                "query": "curriculo",
                "max_results": 20,
            }
        )

    assert "default_file_id" not in result
    file_ids = [f["id"] for f in result["files"]]
    assert file_ids == ["1ABC", "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-", "1h6YYC76Q6YkoRjRPoXuZQgHxBIpDgS_c"]


@pytest.mark.asyncio
async def test_search_drive_files_skips_non_curriculo_queries():
    """Para queries sem keyword (curriculo/cv/resumo), NAO aplica filtro."""
    from deepagent_layer.tools import _build_drive_tools

    tools = _build_drive_tools()
    search_drive_files = next(t for t in tools if t.name == "search_drive_files")

    upstream_result = {"files": _sample_files(), "count": 3}

    async def fake_search_files(**kwargs):
        return upstream_result

    get_fact_calls = []

    async def fake_get_fact(key, phone):
        get_fact_calls.append((key, phone))
        return "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await search_drive_files.ainvoke(
            {
                "phone": "5511966830020",
                "query": "ata de reuniao",
                "max_results": 20,
            }
        )

    assert "default_file_id" not in result
    assert get_fact_calls == [], f"get_fact_by_key NAO deveria ser chamado para query sem curriculum. Chamadas: {get_fact_calls}"


@pytest.mark.asyncio
async def test_search_drive_files_opt_out_returns_unfiltered():
    """Quando apply_default_filter=False, retorna resultado original."""
    from deepagent_layer.tools import _build_drive_tools

    tools = _build_drive_tools()
    search_drive_files = next(t for t in tools if t.name == "search_drive_files")

    upstream_result = {"files": _sample_files(), "count": 3}

    async def fake_search_files(**kwargs):
        return upstream_result

    get_fact_calls = []

    async def fake_get_fact(key, phone):
        get_fact_calls.append((key, phone))
        return "Curriculo_Vinicius_Brito_Rocha_Data_Science_AI_Manager.pdf"

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await search_drive_files.ainvoke(
            {
                "phone": "5511966830020",
                "query": "curriculo",
                "max_results": 20,
                "apply_default_filter": False,
            }
        )

    assert "default_file_id" not in result
    file_ids = [f["id"] for f in result["files"]]
    assert file_ids == ["1ABC", "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-", "1h6YYC76Q6YkoRjRPoXuZQgHxBIpDgS_c"]
    assert get_fact_calls == [], "Opt-out NAO deveria chamar get_fact_by_key"


@pytest.mark.asyncio
async def test_search_drive_files_handles_firestore_error_gracefully():
    """Se Firestore falha, NAO quebra a tool — retorna o resultado original."""
    from deepagent_layer.tools import _build_drive_tools

    tools = _build_drive_tools()
    search_drive_files = next(t for t in tools if t.name == "search_drive_files")

    upstream_result = {"files": _sample_files(), "count": 3}

    async def fake_search_files(**kwargs):
        return upstream_result

    async def fake_get_fact(key, phone):
        raise RuntimeError("firestore_unavailable")

    with patch("tools.google_drive.search_files", side_effect=fake_search_files), patch(
        "tools.memory.get_fact_by_key", side_effect=fake_get_fact
    ):
        result = await search_drive_files.ainvoke(
            {
                "phone": "5511966830020",
                "query": "curriculo",
                "max_results": 20,
            }
        )

    assert "default_file_id" not in result
    file_ids = [f["id"] for f in result["files"]]
    assert file_ids == ["1ABC", "1-LyCGTRDkO29JBe4OzwJ6MvPfpyEuQk-", "1h6YYC76Q6YkoRjRPoXuZQgHxBIpDgS_c"]
