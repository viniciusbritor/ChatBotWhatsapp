"""Tests para core/pdf_extract.py (Fase 30/07).

Cobre:
- PDF normal: retorna texto via pypdf (primeiro parser)
- PDF corrompido: cai para pdfplumber
- PDF invalido: cai para pdfminer
- Todos falham: retorna string vazia
- Metadata via return_metadata=True
- Logging estruturado em cada falha
"""
from unittest.mock import patch


def test_parse_pdf_robust_returns_string():
    """API basica retorna str."""
    from core.pdf_extract import parse_pdf_robust

    result = parse_pdf_robust(b"%PDF-1.4\nfake")
    assert isinstance(result, str)


def test_parse_pdf_robust_invalid_pdf_returns_empty():
    """PDF totalmente invalido: todos parsers falham, retorna vazio."""
    from core.pdf_extract import parse_pdf_robust

    result = parse_pdf_robust(b"NOT A PDF")
    assert result == ""


def test_parse_pdf_robust_uses_pypdf_first():
    """Quando pypdf funciona, ele e usado (sem fallback)."""
    from core import pdf_extract

    pypdf_calls = []

    def fake_pypdf_with_tolerance(raw):
        pypdf_calls.append(len(raw))
        return ("texto do pypdf", 1, 1)

    def fake_pdfplumber(raw):
        return "texto do pdfplumber (NAO DEVE CHAMAR)"

    with patch.object(
        pdf_extract, "_try_pypdf_with_tolerance", new=fake_pypdf_with_tolerance,
    ), patch.object(
        pdf_extract, "_try_pdfplumber", new=fake_pdfplumber,
    ):
        result = pdf_extract.parse_pdf_robust(b"fake pdf bytes")

    assert result == "texto do pypdf"
    assert len(pypdf_calls) == 1


def test_parse_pdf_robust_falls_back_to_pdfplumber():
    """Quando pypdf falha, tenta pdfplumber."""
    from core import pdf_extract

    def fake_pypdf(raw):
        raise ValueError("pypdf simulated error")

    def fake_pdfplumber(raw):
        return "texto recuperado pelo pdfplumber"

    pdfplumber_calls = []

    def tracked_pdfplumber(raw):
        pdfplumber_calls.append(1)
        return "texto recuperado pelo pdfplumber"

    with patch.object(pdf_extract, "_try_pypdf", new=fake_pypdf), \
         patch.object(pdf_extract, "_try_pdfplumber", new=tracked_pdfplumber):
        result = pdf_extract.parse_pdf_robust(b"corrupted bytes")

    assert result == "texto recuperado pelo pdfplumber"
    assert len(pdfplumber_calls) == 1


def test_parse_pdf_robust_falls_back_to_pdfminer():
    """Quando pypdf e pdfplumber falham, pdfminer tenta."""
    from core import pdf_extract

    def fake_pypdf(raw):
        raise ValueError("pypdf error")

    def fake_pdfplumber(raw):
        raise RuntimeError("pdfplumber error")

    def fake_pdfminer(raw):
        return "texto recuperado pelo pdfminer"

    with patch.object(pdf_extract, "_try_pypdf", new=fake_pypdf), \
         patch.object(pdf_extract, "_try_pdfplumber", new=fake_pdfplumber), \
         patch.object(pdf_extract, "_try_pdfminer", new=fake_pdfminer):
        result = pdf_extract.parse_pdf_robust(b"corrupted bytes")

    assert result == "texto recuperado pelo pdfminer"


def test_parse_pdf_robust_all_fail_returns_empty():
    """Quando todos os 3 parsers falham, retorna string vazia."""
    from core import pdf_extract

    def boom(raw):
        raise RuntimeError("simulated boom")

    with patch.object(pdf_extract, "_try_pypdf", new=boom), \
         patch.object(pdf_extract, "_try_pdfplumber", new=boom), \
         patch.object(pdf_extract, "_try_pdfminer", new=boom):
        result = pdf_extract.parse_pdf_robust(b"corrupted")

    assert result == ""


def test_parse_pdf_robust_returns_metadata():
    """return_metadata=True retorna (text, dict)."""
    from core.pdf_extract import parse_pdf_robust

    text, metadata = parse_pdf_robust(
        b"%PDF-1.4\nfake", return_metadata=True,
    )
    assert isinstance(metadata, dict)
    assert "parser" in metadata
    assert "file_size" in metadata
    assert "error_type" in metadata
    assert metadata["file_size"] == len(b"%PDF-1.4\nfake")


def test_parse_pdf_robust_partial_extraction():
    """Quando pypdf falha em uma pagina, retorna texto das paginas
    anteriores e marca partial=True."""
    from core import pdf_extract

    def fake_pypdf_with_tolerance(raw):
        return ("pagina 1\n\npagina 2\n\n", 2, 5)

    with patch.object(
        pdf_extract, "_try_pypdf_with_tolerance",
        new=fake_pypdf_with_tolerance,
    ):
        text, metadata = pdf_extract.parse_pdf_robust(
            b"corrupted pdf", return_metadata=True,
        )

    assert text == "pagina 1\n\npagina 2\n\n"
    assert metadata["partial"] is True
    assert metadata["pages_parsed"] == 2
    assert metadata["pages_total"] == 5
    assert metadata["parser"] == "pypdf"


def test_parse_pdf_robust_complete_extraction_not_partial():
    """Quando pypdf extrai TODAS as paginas com sucesso."""
    from core import pdf_extract

    def fake_pypdf_with_tolerance(raw):
        return ("todas paginas", 5, 5)

    with patch.object(
        pdf_extract, "_try_pypdf_with_tolerance",
        new=fake_pypdf_with_tolerance,
    ):
        text, metadata = pdf_extract.parse_pdf_robust(
            b"valid pdf", return_metadata=True,
        )

    assert text == "todas paginas"
    assert metadata["partial"] is False
    assert metadata["pages_parsed"] == 5
    assert metadata["pages_total"] == 5


def test_parse_pdf_robust_partial_uses_fallback_when_empty():
    """Quando pypdf (parcial) retorna vazio E pdfplumber tem texto,
    cai para pdfplumber como fallback final."""
    from core import pdf_extract

    def fake_pypdf_with_tolerance(raw):
        return ("", 0, 5)

    def fake_pdfplumber(raw):
        return "texto via pdfplumber"

    with patch.object(
        pdf_extract, "_try_pypdf_with_tolerance",
        new=fake_pypdf_with_tolerance,
    ), patch.object(
        pdf_extract, "_try_pdfplumber", new=fake_pdfplumber,
    ):
        text, metadata = pdf_extract.parse_pdf_robust(
            b"corrupted pdf", return_metadata=True,
        )

    assert text == "texto via pdfplumber"
    assert metadata["parser"] == "pdfplumber"
    assert metadata["partial"] is False


def test_parse_pdf_robust_metadata_fields_complete():
    """Metadata tem todos os campos esperados."""
    from core import pdf_extract

    def fake_pypdf_with_tolerance(raw):
        return ("texto", 10, 10)

    with patch.object(
        pdf_extract, "_try_pypdf_with_tolerance",
        new=fake_pypdf_with_tolerance,
    ):
        text, metadata = pdf_extract.parse_pdf_robust(
            b"x" * 1024, return_metadata=True,
        )

    expected_fields = {
        "parser", "file_size", "pages_total", "pages_parsed",
        "error_type", "error_message", "partial",
    }
    assert set(metadata.keys()) == expected_fields
    assert metadata["file_size"] == 1024


# ---------------------------------------------------------------------------
# Tests added in D1.6 — encoding corruption detection + NFKC normalization
# ---------------------------------------------------------------------------


class TestEncodingCorruption:
    def test_combining_char_with_space(self):
        """c cedilla + space + tilde desconectada deve ser detectado."""
        from core.pdf_extract import _has_encoding_corruption
        assert _has_encoding_corruption("Preci\ufb01ca\u0327 c\u0303 ao")

    def test_ligature_fi(self):
        """Ligatura \ufb01 (fi) deve ser detectada."""
        from core.pdf_extract import _has_encoding_corruption
        assert _has_encoding_corruption("Preci\ufb01ca\u00e7\u00e3o")

    def test_ligature_fl(self):
        """Ligatura \ufb02 (fl) deve ser detectada."""
        from core.pdf_extract import _has_encoding_corruption
        assert _has_encoding_corruption("in\ufb02u\u00eancia")

    def test_control_chars_c1(self):
        """Caracteres de controle C1 em alta densidade."""
        from core.pdf_extract import _has_encoding_corruption
        corrupted = "Texto normal " + "\x90\x9d" * 50
        assert _has_encoding_corruption(corrupted)

    def test_tilde_disconnected(self):
        """Dois combining chars em sequencia: cedilla + tilde."""
        from core.pdf_extract import _has_encoding_corruption
        assert _has_encoding_corruption("a\u0303o disserta\u0327\u0303")

    def test_combining_density_high(self):
        """Alta densidade de combining chars (>3%)."""
        from core.pdf_extract import _has_encoding_corruption
        corrupted = "Disserta\u0327c\u0303ao de Mestrado " * 30
        assert _has_encoding_corruption(corrupted)

    def test_normal_portuguese_ok(self):
        """Texto normal em portugu\u00eas n\u00e3o deve ser detectado."""
        from core.pdf_extract import _has_encoding_corruption
        assert not _has_encoding_corruption(
            "Precifica\u00e7\u00e3o de op\u00e7\u00f5es financeiras com volatilidade"
        )

    def test_normal_english_ok(self):
        """Texto em ingl\u00eas n\u00e3o deve ser detectado."""
        from core.pdf_extract import _has_encoding_corruption
        assert not _has_encoding_corruption(
            "Bayesian approach to estimate volatility in option pricing models"
        )

    def test_empty_text_ok(self):
        """Texto vazio n\u00e3o deve ser detectado."""
        from core.pdf_extract import _has_encoding_corruption
        assert not _has_encoding_corruption("")


class TestUnicodeNormalization:
    def test_ligature_fi_becomes_fi(self):
        """Ligatura \ufb01 vira 'fi' ap\u00f3s NFKC."""
        from core.pdf_extract import _normalize_unicode
        result = _normalize_unicode("Preci\ufb01ca\u00e7\u00e3o")
        assert "\ufb01" not in result
        assert "fi" in result
        assert result == "Precifica\u00e7\u00e3o"

    def test_ligature_fl_becomes_fl(self):
        """Ligatura \ufb02 vira 'fl' ap\u00f3s NFKC."""
        from core.pdf_extract import _normalize_unicode
        result = _normalize_unicode("in\ufb02u\u00eancia")
        assert "\ufb02" not in result
        assert "fl" in result

    def test_normal_text_unchanged(self):
        """Texto normal em portugu\u00eas permanece inalterado."""
        from core.pdf_extract import _normalize_unicode
        original = "Precifica\u00e7\u00e3o de op\u00e7\u00f5es financeiras com volatilidade"
        assert _normalize_unicode(original) == original

    def test_empty_text(self):
        """Texto vazio permanece vazio."""
        from core.pdf_extract import _normalize_unicode
        assert _normalize_unicode("") == ""

    def test_combining_chars_composed(self):
        """Caracteres combinantes s\u00e3o compostos: a + til = \u00e3."""
        from core.pdf_extract import _normalize_unicode
        decomposed = "a\u0303 c\u0327 e\u0301"
        result = _normalize_unicode(decomposed)
        assert result == "\u00e3 \u00e7 \u00e9"


class TestParsePdfRobustFallthrough:
    def test_corruption_falls_through_to_pdfplumber(self):
        """Quando pypdf retorna texto com encoding quebrado,
        parse_pdf_robust deve cair para pdfplumber."""
        from unittest.mock import patch
        from core.pdf_extract import parse_pdf_robust

        corrupted_text = "Disserta\u0327c\u0303ao de Mestrado " * 30
        corrupted_text += "normal filler text. " * 10

        fake_raw = b"%PDF-1.4 fake pdf content"

        with patch("core.pdf_extract._try_pypdf_with_tolerance",
                   return_value=(corrupted_text, 10, 10)):
            with patch("core.pdf_extract._try_pdfplumber",
                       return_value="Texto correto extra\u00eddo pelo pdfplumber"):
                result = parse_pdf_robust(fake_raw, return_metadata=True)
                text, meta = result
                assert meta["parser"] == "pdfplumber"
                assert "pdfplumber" in text

    def test_clean_pypdf_stops_at_pypdf(self):
        """Quando pypdf retorna texto limpo, pdfplumber nunca \u00e9 chamado."""
        from unittest.mock import patch
        from core.pdf_extract import parse_pdf_robust

        clean_text = "Texto limpo extra\u00eddo do PDF sem corrup\u00e7\u00e3o. " * 20
        fake_raw = b"%PDF-1.4 clean pdf"

        with patch("core.pdf_extract._try_pypdf_with_tolerance",
                   return_value=(clean_text, 10, 10)):
            with patch("core.pdf_extract._try_pdfplumber") as mock_plumber:
                result = parse_pdf_robust(fake_raw, return_metadata=True)
                text, meta = result
                assert meta["parser"] == "pypdf"
                mock_plumber.assert_not_called()
