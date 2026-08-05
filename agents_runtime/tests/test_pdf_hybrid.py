"""Testes do OCR híbrido — parse_pdf_hybrid + qualidade."""
from __future__ import annotations

import pytest
from unittest.mock import patch


class TestQualityCheck:
    def test_clean_text_high_quality(self):
        from core.pdf_extract import _check_text_quality
        score = _check_text_quality("precificação normal sem corrupção")
        assert score >= 0.95

    def test_combining_mark_low_quality(self):
        from core.pdf_extract import _check_text_quality
        score = _check_text_quality(f"necess\u0301 arios")
        assert score < 0.95

    def test_spacing_diacritic_low_quality(self):
        from core.pdf_extract import _check_text_quality
        score = _check_text_quality("precifica\u00b8 c\u02dc ao")
        assert score < 0.95

    def test_empty_text_quality_zero(self):
        from core.pdf_extract import _check_text_quality
        assert _check_text_quality("") == 0.0
        assert _check_text_quality("   ") == 0.0


class TestHybrid:
    @patch("core.pdf_extract._parse_pdf_ocr")
    @patch("core.pdf_extract.parse_pdf_robust")
    def test_good_quality_no_ocr(self, mock_robust, mock_ocr):
        from core.pdf_extract import parse_pdf_hybrid
        mock_robust.return_value = "texto limpo e bem formatado"
        result = parse_pdf_hybrid(b"fake")
        assert result == "texto limpo e bem formatado"
        mock_ocr.assert_not_called()

    @patch("core.pdf_extract._parse_pdf_ocr")
    @patch("core.pdf_extract.parse_pdf_robust")
    def test_bad_quality_calls_ocr(self, mock_robust, mock_ocr):
        from core.pdf_extract import parse_pdf_hybrid
        mock_robust.return_value = f"necess\u0301 arios de obten\u0327ca"
        mock_ocr.return_value = "necessários de obtenção"
        result = parse_pdf_hybrid(b"fake")
        assert result == "necessários de obtenção"
        mock_ocr.assert_called_once()

    @patch("core.pdf_extract._parse_pdf_ocr")
    @patch("core.pdf_extract.parse_pdf_robust")
    def test_bad_quality_ocr_returns_metadata(self, mock_robust, mock_ocr):
        from core.pdf_extract import parse_pdf_hybrid
        mock_robust.return_value = f"necess\u0301 arios"
        mock_ocr.return_value = "necessários"
        text, meta = parse_pdf_hybrid(b"fake", return_metadata=True)
        assert text == "necessários"
        assert meta["parser"] == "ocr"

    @patch("core.pdf_extract._parse_pdf_ocr")
    @patch("core.pdf_extract.parse_pdf_robust")
    def test_empty_robust_falls_to_ocr(self, mock_robust, mock_ocr):
        from core.pdf_extract import parse_pdf_hybrid
        mock_robust.return_value = ""
        mock_ocr.return_value = ""
        result = parse_pdf_hybrid(b"fake")
        assert result == ""
        mock_ocr.assert_called_once()


class TestOcrExtraction:
    def test_ocr_deps_missing_returns_empty(self):
        from core.pdf_extract import _parse_pdf_ocr
        with patch.dict("sys.modules", {"pdf2image": None, "pytesseract": None}):
            assert _parse_pdf_ocr(b"fake") == ""
