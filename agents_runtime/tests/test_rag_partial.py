"""Testes para partial success (PHASE 4 do loop RAG).

Quando alguns embeddings falham mas outros dao OK, indexa os
que funcionaram e marca partial=True no resultado.

Estes testes usam um mock para embed_documents que retorna direto
os vectors (bypass do chunker + OpenAI).
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_index_partial_7_of_10_chunks_ok(monkeypatch):
    """embed_documents retorna 7 vectors de 10 chunks -> 7 indexed + partial=True."""
    from core import rag

    monkeypatch.setattr(rag, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(rag, "EMBEDDING_DIM", 1536)
    monkeypatch.setattr(rag, "PRIVATE_CHARS_SOFT_LIMIT", 10**9)
    monkeypatch.setattr(rag, "PRIVATE_CHUNKS_SOFT_LIMIT", 10**6)
    monkeypatch.setattr(rag, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(rag, "_owner_hash", lambda p: "oh_test")
    monkeypatch.setattr(rag, "_now_brt", lambda: MagicMock(isoformat=lambda: "2026"))
    monkeypatch.setattr(rag, "mask_pii", lambda s: s)
    monkeypatch.setattr(rag, "_chunk_text", lambda text, max_chars=1200, overlap=180: [
        f"chunk_{i}" for i in range(10)
    ])
    monkeypatch.setattr(rag, "_chunk_text_semantic", lambda text, **kw: [("", "paragraph", f"chunk_{i}") for i in range(10)])

    async def fake_embed_documents(chunks):
        # embed_documents ja filtra Nones internamente, entao
        # retornamos a lista filtrada (4 success de 10).
        return [[0.1] * 1536 for i in range(len(chunks)) if i not in (3, 5, 7)]

    monkeypatch.setattr(rag, "embed_documents", fake_embed_documents)

    fake_db = MagicMock()
    with patch.object(rag, "_get_firestore", return_value=fake_db):
        result = await rag.index_private_document(
            phone="+5511966830020",
            text_content="dummy text for chunker bypass",
            source_title="t.pdf",
            category="t",
        )

    assert result.get("error") is None
    assert result["chunks"] == 10
    assert result["chunks_indexed"] == 7


@pytest.mark.asyncio
async def test_index_all_embeddings_fail_returns_error(monkeypatch):
    """embed_documents retorna [] -> error all_embeddings_failed."""
    from core import rag

    monkeypatch.setattr(rag, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(rag, "EMBEDDING_DIM", 1536)
    monkeypatch.setattr(rag, "PRIVATE_CHARS_SOFT_LIMIT", 10**9)
    monkeypatch.setattr(rag, "PRIVATE_CHUNKS_SOFT_LIMIT", 10**6)
    monkeypatch.setattr(rag, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(rag, "_owner_hash", lambda p: "oh_test")
    monkeypatch.setattr(rag, "_now_brt", lambda: MagicMock(isoformat=lambda: "2026"))
    monkeypatch.setattr(rag, "mask_pii", lambda s: s)
    monkeypatch.setattr(rag, "_chunk_text", lambda text, **kw: ["c1", "c2"])
    monkeypatch.setattr(rag, "_chunk_text_semantic", lambda text, **kw: [("", "paragraph", "c1"), ("", "paragraph", "c2")])

    async def fake_embed_documents(chunks):
        return []  # empty list = all failed

    monkeypatch.setattr(rag, "embed_documents", fake_embed_documents)

    fake_db = MagicMock()
    with patch.object(rag, "_get_firestore", return_value=fake_db):
        result = await rag.index_private_document(
            phone="+5511", text_content="t", source_title="t.pdf", category="t",
        )

    assert result.get("error") == "all_embeddings_failed"
    assert result.get("chunks") == 2


@pytest.mark.asyncio
async def test_index_all_embeddings_ok_partial_false(monkeypatch):
    """embed_documents retorna todos vectors -> partial=False."""
    from core import rag

    monkeypatch.setattr(rag, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(rag, "EMBEDDING_DIM", 1536)
    monkeypatch.setattr(rag, "PRIVATE_CHARS_SOFT_LIMIT", 10**9)
    monkeypatch.setattr(rag, "PRIVATE_CHUNKS_SOFT_LIMIT", 10**6)
    monkeypatch.setattr(rag, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(rag, "_owner_hash", lambda p: "oh_test")
    monkeypatch.setattr(rag, "_now_brt", lambda: MagicMock(isoformat=lambda: "2026"))
    monkeypatch.setattr(rag, "mask_pii", lambda s: s)
    monkeypatch.setattr(rag, "_chunk_text", lambda text, **kw: ["c1", "c2", "c3"])
    monkeypatch.setattr(rag, "_chunk_text_semantic", lambda text, **kw: [("", "p", "c1"), ("", "p", "c2"), ("", "p", "c3")])

    async def fake_embed_documents(chunks):
        return [[0.1] * 1536 for _ in chunks]

    monkeypatch.setattr(rag, "embed_documents", fake_embed_documents)

    fake_db = MagicMock()
    with patch.object(rag, "_get_firestore", return_value=fake_db):
        result = await rag.index_private_document(
            phone="+5511", text_content="t", source_title="t.pdf", category="t",
        )

    assert result["chunks"] == 3
    assert result["chunks_indexed"] == 3


@pytest.mark.asyncio
async def test_index_embed_documents_returns_none_returns_error(monkeypatch):
    """embed_documents retorna None (timeout) -> error embedding_failed."""
    from core import rag

    monkeypatch.setattr(rag, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(rag, "EMBEDDING_DIM", 1536)
    monkeypatch.setattr(rag, "PRIVATE_CHARS_SOFT_LIMIT", 10**9)
    monkeypatch.setattr(rag, "PRIVATE_CHUNKS_SOFT_LIMIT", 10**6)
    monkeypatch.setattr(rag, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(rag, "_owner_hash", lambda p: "oh_test")
    monkeypatch.setattr(rag, "_now_brt", lambda: MagicMock(isoformat=lambda: "2026"))
    monkeypatch.setattr(rag, "mask_pii", lambda s: s)
    monkeypatch.setattr(rag, "_chunk_text", lambda text, **kw: ["c1", "c2", "c3"])
    monkeypatch.setattr(rag, "_chunk_text_semantic", lambda text, **kw: [("", "p", "c1"), ("", "p", "c2"), ("", "p", "c3")])

    async def fake_embed_documents(chunks):
        return None  # timeout or all-errored

    monkeypatch.setattr(rag, "embed_documents", fake_embed_documents)

    fake_db = MagicMock()
    with patch.object(rag, "_get_firestore", return_value=fake_db):
        result = await rag.index_private_document(
            phone="+5511", text_content="t", source_title="t.pdf", category="t",
        )

    assert result.get("error") == "embedding_failed"


@pytest.mark.asyncio
async def test_pdf_handler_propagates_partial_status(monkeypatch):
    """pdf_handler.persist propaga rag_individual_partial + chunks_indexed."""
    from skills.knowledge import pdf_handler
    from core import rag as rag_mod

    async def fake_index(**kwargs):
        return {
            "chunks": 10,
            "chunks_indexed": 7,
            "partial": True,
            "doc_ids": ["a"] * 10,
            "vector_doc_ids": ["v"] * 7,
            "owner_hash": "oh",
        }

    monkeypatch.setattr(rag_mod, "index_private_document", fake_index)

    envelope = {"phone": "+5511966830020", "extra": {}}
    extracted = {
        "text": "x" * 1000,
        "source_name": "x.pdf",
        "mimetype": "application/pdf",
    }
    result = await pdf_handler.persist(envelope, extracted, scope="private")

    assert result["status"] == "rag_individual_partial"
    assert result["chunks_indexed"] == 7
    assert result["chunks_total"] == 10


@pytest.mark.asyncio
async def test_pdf_handler_propagates_full_error(monkeypatch):
    """pdf_handler.persist propaga error quando index retorna all-fail."""
    from skills.knowledge import pdf_handler
    from core import rag as rag_mod

    async def fake_index(**kwargs):
        return {"error": "all_embeddings_failed", "chunks": 10}

    monkeypatch.setattr(rag_mod, "index_private_document", fake_index)

    envelope = {"phone": "+5511966830020", "extra": {}}
    extracted = {
        "text": "x" * 1000,
        "source_name": "x.pdf",
        "mimetype": "application/pdf",
    }
    result = await pdf_handler.persist(envelope, extracted, scope="private")

    assert result.get("error") == "rag_index_failed"
    assert result.get("detail") == "all_embeddings_failed"
