"""Testes dos handlers DOCX/XLSX/PPTX e fallback de síntese."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDocxTables:
    @pytest.mark.asyncio
    async def test_docx_extracts_tables_after_paragraphs(self):
        from skills.knowledge import docx_handler

        fake_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Paragrafo antes da tabela"
        fake_doc.paragraphs = [p1]

        table = MagicMock()
        r1 = MagicMock()
        r1.cells = [MagicMock(), MagicMock()]
        r1.cells[0].text = "Col A"
        r1.cells[1].text = "Col B"
        r2 = MagicMock()
        r2.cells = [MagicMock(), MagicMock()]
        r2.cells[0].text = "Val 1"
        r2.cells[1].text = "Val 2"
        table.rows = [r1, r2]
        fake_doc.tables = [table]

        with patch("docx.Document", return_value=fake_doc):
            with patch.object(docx_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await docx_handler.extract({"extra": {}, "instance": "x"})

        assert "[TABELA]" in result["text"]
        assert "Col A | Col B" in result["text"]
        assert "Val 1 | Val 2" in result["text"]
        assert "Paragrafo antes da tabela" in result["text"]

    @pytest.mark.asyncio
    async def test_docx_without_table_unchanged(self):
        from skills.knowledge import docx_handler

        fake_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Apenas texto"
        fake_doc.paragraphs = [p1]
        fake_doc.tables = []

        with patch("docx.Document", return_value=fake_doc):
            with patch.object(docx_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await docx_handler.extract({"extra": {}, "instance": "x"})

        assert result["text"] == "Apenas texto"


class TestXlsxPipe:
    @pytest.mark.asyncio
    async def test_xlsx_uses_pipe_separator(self):
        from skills.knowledge import xlsx_handler

        fake_wb = MagicMock()
        fake_sheet = MagicMock()
        fake_sheet.title = "Plan1"
        fake_sheet.iter_rows.return_value = [
            ("Saude, Educacao e Seguranca", "valor"),
            ("col2", "col3"),
        ]
        fake_wb.worksheets = [fake_sheet]

        with patch("openpyxl.load_workbook", return_value=fake_wb):
            with patch.object(xlsx_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await xlsx_handler.extract({"extra": {}, "instance": "x"})

        assert "--- Plan1 ---" in result["text"]
        assert "Saude, Educacao e Seguranca | valor" in result["text"]
        assert "col2 | col3" in result["text"]


class TestPptxHandler:
    @pytest.mark.asyncio
    async def test_pptx_extracts_slides(self):
        from skills.knowledge import pptx_handler

        fake_prs = MagicMock()
        slide = MagicMock()
        shape_text = MagicMock()
        shape_text.has_text_frame = True
        shape_text.has_table = False
        para = MagicMock()
        para.runs = [MagicMock(), MagicMock()]
        para.runs[0].text = "Titulo do slide"
        para.runs[1].text = " com conteudo"
        shape_text.text_frame.paragraphs = [para]
        slide.shapes = [shape_text]
        fake_prs.slides = [slide]

        with patch("pptx.Presentation", return_value=fake_prs):
            with patch.object(pptx_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await pptx_handler.extract({"extra": {}, "instance": "x"})

        assert "--- Slide 1 ---" in result["text"]
        assert "Titulo do slide com conteudo" in result["text"]

    @pytest.mark.asyncio
    async def test_pptx_empty_returns_empty_text(self):
        from skills.knowledge import pptx_handler

        fake_prs = MagicMock()
        fake_prs.slides = []

        with patch("pptx.Presentation", return_value=fake_prs):
            with patch.object(pptx_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await pptx_handler.extract({"extra": {}, "instance": "x"})

        assert result["text"] == ""


class TestPdfHandlerHybrid:
    @pytest.mark.asyncio
    async def test_pdf_handler_usa_parse_pdf_hybrid(self):
        """pdf_handler.extract DEVE usar parse_pdf_hybrid (OCR conectado)."""
        from skills.knowledge import pdf_handler

        with patch("core.pdf_extract.parse_pdf_hybrid") as mock_hybrid:
            mock_hybrid.return_value = "texto limpo extraido"
            with patch.object(pdf_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await pdf_handler.extract({"extra": {}, "instance": "x"})
        mock_hybrid.assert_called_once_with(b"fake")
        assert result["text"] == "texto limpo extraido"

    @pytest.mark.asyncio
    async def test_pdf_handler_ocr_clean_corrupted(self):
        """OCR deve retornar texto limpo para PDF corrompido."""
        from skills.knowledge import pdf_handler

        with patch("core.pdf_extract.parse_pdf_hybrid") as mock_hybrid:
            mock_hybrid.return_value = "necessários para a obtenção do grau"
            with patch.object(pdf_handler, "_download_bytes", new_callable=AsyncMock, return_value=b"fake"):
                result = await pdf_handler.extract({"extra": {}, "instance": "x"})
        assert "necessários" in result["text"]
        assert "\u0301" not in result["text"]


class TestSynthesisFallbackClean:
    def test_fallback_cleans_diacritics(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks

        chunks = [{"source": "tese.pdf", "text": "necess \u0301arios para"}]
        result = _fallback_raw_chunks(chunks)
        assert "necess\u00e1rios" in result
        assert "\u0301" not in result

    def test_fallback_includes_section(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks

        chunks = [{"source": "tese.pdf", "text": "conteudo do resumo", "section_title": "RESUMO"}]
        result = _fallback_raw_chunks(chunks)
        assert "RESUMO" in result

    def test_fallback_empty_chunks(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks
        result = _fallback_raw_chunks([])
        assert "nao encontrei" in result.lower()


class TestPrioritizeContentChunks:
    def test_about_query_prioritizes_resumo_chunk(self):
        from pipelines.doc_pipeline import _prioritize_content_chunks

        chunks = [
            {"source": "tese.pdf", "text": "Vinicius Brito Rocha ficha catalografica", "section_title": ""},
            {"source": "tese.pdf", "text": "Este trabalho propoe utilizar informacao para estimar volatilidade", "section_title": "RESUMO"},
        ]
        result = _prioritize_content_chunks("sobre o que se trata a dissertacao", chunks)
        assert result[0]["section_title"] == "RESUMO"

    def test_non_about_query_keeps_order(self):
        from pipelines.doc_pipeline import _prioritize_content_chunks

        chunks = [
            {"source": "tese.pdf", "text": "primeiro chunk", "section_title": ""},
            {"source": "tese.pdf", "text": "segundo chunk", "section_title": "RESUMO"},
        ]
        result = _prioritize_content_chunks("qual o valor de volatilidade", chunks)
        assert result == chunks

    def test_introducao_chunk_boosted(self):
        from pipelines.doc_pipeline import _prioritize_content_chunks

        chunks = [
            {"source": "tese.pdf", "text": "ficha catalografica", "section_title": ""},
            {"source": "tese.pdf", "text": "A introducao apresenta o contexto do mercado", "section_title": "1 INTRODUCAO"},
        ]
        result = _prioritize_content_chunks("qual o tema da dissertacao", chunks)
        assert "INTRODUCAO" in result[0]["section_title"]
