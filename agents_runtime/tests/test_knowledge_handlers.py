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


class TestSynthesisFallbackClean:
    def test_fallback_cleans_diacritics(self):
        from pipelines.doc_pipeline import _fallback_raw_chunks

        chunks = [{"source": "tese.pdf", "text": "necess \u0301arios para"}]
        result = _fallback_raw_chunks(chunks)
        assert "necess\u00e1rios" in result
        assert "\u0301" not in result
