"""Fase B — Legal hierarchy, chunk overlap, truncation."""
from __future__ import annotations

import pytest


class TestLegalHierarchy:
    def test_artigo_with_paragraphs(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("Art. 7o Do Tratamento de Dados")
        assert h["level"] == "artigo"
        assert h["number"] == "7"

    def test_secao_with_roman(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("SECAO II - Do Tratamento de Dados Pessoais Sensiveis")
        assert h["level"] == "secao"
        assert h["number"] == "II"

    def test_capitulo(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("CAPITULO II - Do Tratamento")
        assert h["level"] == "capitulo"

    def test_paragrafo_unico(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("Paragrafo unico")
        assert h["level"] == "paragrafo"
        assert h["number"] == "unico"

    def test_inciso(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("I - a soberania")
        assert h["level"] == "inciso"
        assert h["number"] == "I"

    def test_lei_number(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("LEI N 13.709, DE 14 DE AGOSTO DE 2018")
        assert h["level"] == "lei"

    def test_titulo(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("TITULO I - Disposicoes Gerais")
        assert h["level"] == "titulo"
        assert h["number"] == "I"

    def test_plain_text_fallback(self):
        from core.rag import _extract_legal_hierarchy
        h = _extract_legal_hierarchy("texto qualquer sem hierarquia")
        assert h["level"] == "texto"


class TestChunkOverlap:
    def test_semantic_chunk_min_chars(self):
        from core.rag import _chunk_text_semantic
        chunks = _chunk_text_semantic("A" * 100, min_chars=50)
        assert len(chunks) > 0

    def test_short_text_not_dropped(self):
        from core.rag import _chunk_text_semantic
        text = "Art. 7o O tratamento de dados pessoais de criancas."
        chunks = _chunk_text_semantic(text, min_chars=50)
        assert len(chunks) > 0

    def test_long_paragraph_produces_overlap(self):
        from core.rag import _chunk_text_semantic
        sentences = ". ".join([f"Frase {i}" for i in range(50)]) + "."
        chunks = _chunk_text_semantic(sentences, max_chars=300, min_chars=50, overlap_chars=100)
        assert len(chunks) >= 2


class TestDocPipelineTruncation:
    def test_truncation_limit(self):
        from pipelines.doc_pipeline import _format_chunk_context
        result = _format_chunk_context({"text": "A" * 2000, "source": "test.pdf"})
        assert len(result.split("] ")[-1]) <= 1500
