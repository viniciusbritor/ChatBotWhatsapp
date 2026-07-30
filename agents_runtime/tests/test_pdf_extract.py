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
