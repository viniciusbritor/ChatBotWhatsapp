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

    def fake_pypdf(raw):
        pypdf_calls.append(len(raw))
        return "texto do pypdf"

    def fake_pdfplumber(raw):
        return "texto do pdfplumber (NAO DEVE CHAMAR)"

    with patch.object(pdf_extract, "_try_pypdf", new=fake_pypdf), \
         patch.object(pdf_extract, "_try_pdfplumber", new=fake_pdfplumber):
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
