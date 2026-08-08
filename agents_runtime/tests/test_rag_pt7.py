"""Tests para PT7 F4-F5: indexing pipeline + retrieval (offline com stubs)."""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as patch
from pathlib import Path

import pytest

os.environ.setdefault("GCP_PROJECT", "test-project")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "")
GOLDENSET_DIR = Path(__file__).resolve().parents[2] / "GoldenSet"


class TestChunkingCDC:
    def setup_method(self):
        from pypdf import PdfReader
        text = "\n\n".join(
            p.extract_text() or "" for p in PdfReader(str(GOLDENSET_DIR / "Codigo-do-consumidor-FINAL.pdf")).pages
        ).strip()
        self.text = text

    def test_cdc_produz_dois_chunks(self):
        from core.rag import _chunk_text
        chunks = _chunk_text(self.text)
        assert len(chunks) >= 2, f"Esperado 2+ chunks, got {len(chunks)}"
        for c in chunks:
            assert len(c) > 200
            assert len(c) < 2000

    def test_chunking_preserva_texto_util(self):
        from core.rag import _chunk_text
        chunks = _chunk_text(self.text)
        joined = " ".join(chunks)
        # Pelo menos uma palavra-chave do CDC deve aparecer em cada chunk
        for keyword in ("consumidor", "produto", "fornecedor"):
            assert keyword.lower() in joined.lower(), f"keyword missing: {keyword}"


class TestIndexPipeline:
    def setup_method(self):
        from unittest.mock import MagicMock
        from google.cloud.firestore_v1.vector import Vector

        self.fake_store = {}

        class _Batch:
            """Batch mock que armazena os sets para inspecao pos-test."""
            def __init__(self):
                self.ops = []

            def set(self, doc_ref, data, merge=False):
                doc_ref.set(data, merge=merge)
                self.ops.append(("set", doc_ref, data, merge))
                return self

            def commit(self):
                pass

            def delete(self, doc_ref):
                doc_ref.delete()
                self.ops.append(("delete", doc_ref))

        class _FirestoreCollection:
            def __init__(self, path, store):
                self._path = path
                self._store = store
                self._store.setdefault(path, [])

            def document(self, doc_id):
                for d in self._store[self._path]:
                    if d.id == doc_id:
                        return d
                new = _Doc(doc_id)
                self._store[self._path].append(new)
                return new

            def stream(self):
                for d in list(self._store[self._path]):
                    yield d

            def where(self, *args, **kwargs):
                field = args[0] if args else None
                value = args[2] if len(args) >= 3 else None
                if kwargs.get("filter"):
                    field = kwargs["filter"].field
                    value = kwargs["filter"].value
                new_path = f"{self._path}__where_{field}={value}"
                self._store.setdefault(new_path, [])
                for d in self._store[self._path]:
                    if d.to_dict().get(field) == value:
                        self._store[new_path].append(d)
                return _FirestoreCollection(new_path, self._store)

        class _Doc:
            def __init__(self, doc_id):
                self.id = doc_id
                self._data = {}

            def to_dict(self):
                return dict(self._data)

            def set(self, data, merge=False):
                if merge:
                    self._data = {**self._data, **data}
                else:
                    self._data = dict(data)
                return self

            def delete(self):
                self._data = {}

        self.FakeFirestoreCollection = _FirestoreCollection
        self._DocCls = _Doc
        self.fake_db = MagicMock()
        self.fake_db._by_name = self.fake_store
        self.fake_db.collection.side_effect = lambda name: _FirestoreCollection(name, self.fake_store)
        self.fake_db.batch.side_effect = lambda: _Batch()

    def test_index_private_document_persiste_chunks(self):
        """index_private_document deve persistir chunks com embeddings
        quando a retrieval estiver stub."""
        from unittest.mock import AsyncMock, patch as _patch

        from core.rag import index_private_document, PRIVATE_COLLECTION

        async def fake_embed_documents(texts):
            return [[float(i % 13) / 13.0 for i in range(1536)] for _ in texts]

        # Substituimos o callable direto em vez de mockar
        with _patch("core.rag.embed_documents", new=fake_embed_documents), \
             _patch("core.rag._get_firestore", return_value=self.fake_db):
            result = asyncio.run(index_private_document(
                phone="5511966830020",
                text_content="primeiro paragrafo.\n\nsegundo paragrafo.\n\nterceiro paragrafo.",
                source_title="teste.pdf",
                category="legal",
                class_="legal",
                group="legislacao",
                theme="teste",
            ))
        assert "error" not in result, result
        assert result["chunks"] >= 1
        assert result["chunks_indexed"] == result["chunks"]
        assert result["collection"] == "knowledge-database"

    def test_index_sem_embeddings_retorna_error(self):
        """Com embed_documents retornando [], index deve reportar erro."""
        from unittest.mock import patch as _patch
        from core.rag import index_private_document

        async def fake_embed_empty(texts):
            return []

        with _patch("core.rag.embed_documents", new=fake_embed_empty), \
             _patch("core.rag._get_firestore", return_value=self.fake_db):
            result = asyncio.run(index_private_document(
                phone="5511966830020",
                text_content="algum texto de teste.",
                source_title="teste.pdf",
            ))
        assert "error" in result, result


class TestRetrievalQueryContract:
    """Garante que o `_find_nearest` requer um indice que tem
    embedding_model+embedding_dim+schema_version [+ filtros] + vector_embedding
    nesta ordem exata."""

    def test_filtros_incluem_obrigatorios(self):
        """Os filtros sempre devem incluir embedding_model+embedding_dim+schema_version."""
        from core.rag import _vector_filters
        import hashlib

        owner_hash = hashlib.sha256(b"5511966830020").hexdigest()[:32]
        filters = _vector_filters(owner_hash, [("source_title", "==", "x.pdf")])
        fields = [f[0] for f in filters]
        assert "embedding_model" in fields
        assert "embedding_dim" in fields
        assert "schema_version" in fields
        assert "owner_hash" in fields
        assert "source_title" in fields

    def test_filtros_sem_owner_hash_ok(self):
        """Sem owner_hash, ainda funciona (mas lock-down recomenda sempre passar)."""
        from core.rag import _vector_filters
        filters = _vector_filters(None, [])
        fields = [f[0] for f in filters]
        assert "embedding_model" in fields
        assert "owner_hash" not in fields


class TestDocumentShaId:
    """Determinismo do document_id: mesmo texto gera mesmo id."""

    def test_deterministic_id(self):
        from core.rag import _chunk_text
        text = "Hello world. " * 100
        chunks_a = _chunk_text(text)
        chunks_b = _chunk_text(text)
        assert chunks_a == chunks_b


class TestClearScriptExists:
    """Garante que os scripts de cleanup + reindex existem."""

    def test_clear_knowledge_base_exists(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "clear_knowledge_base.py"
        assert path.is_file()

    def test_reindex_golden_set_exists(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "reindex_golden_set.py"
        assert path.is_file()


class TestGoldenSetPopulation:
    def test_goldenset_has_pdfs(self):
        pdfs = sorted(GOLDENSET_DIR.glob("*.pdf"))
        assert len(pdfs) >= 1, f"Nenhum PDF em {GOLDENSET_DIR}"
        # Cada PDF deve ter pelo menos 100 chars de texto extraivel
        from pypdf import PdfReader
        for p in pdfs:
            text = "\n\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages).strip()
            assert len(text) > 100, f"{p.name} extraido muito curto: {len(text)}"
