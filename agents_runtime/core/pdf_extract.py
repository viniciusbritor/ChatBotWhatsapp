"""Multi-parser PDF extraction (Fase 30/07).

Bug user 30/07: 'cdc-portugues-2013.pdf' falha com
'Stream has ended unexpectedly' em pypdf. Bot responde
'infelizmente nao foi possivel extrair o texto dele'.

Fallback encadeado:
  pypdf -> pdfplumber -> pdfminer.six

Cada parser tenta extrair texto. Se um falhar, o proximo e tentado.
Erros sao logados estruturados (parser, error_type, file_size).

Usado por:
- tools/google_drive.py::read_file_content (read files do Drive)
- skills/knowledge/pdf_handler.py::extract (index RAG inicial)

API:
    text = parse_pdf_robust(raw_bytes) -> str
    text, metadata = parse_pdf_robust(raw_bytes, return_metadata=True)
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import Any, Dict

logger = logging.getLogger(__name__)

_ENCODING_CORRUPTION_PATTERNS = [
    re.compile(r'\s[\u0300-\u036f]'),
    re.compile(r'[\ufb00-\ufb04]'),
    re.compile(r'[\u0300-\u036f]{2,}'),
]

_COMBINING_CHAR_THRESHOLD = 0.03


def _has_encoding_corruption(text: str, *, sample_len: int = 2000) -> bool:
    sample = text[:sample_len]
    if not sample:
        return False
    for pattern in _ENCODING_CORRUPTION_PATTERNS:
        if pattern.search(sample):
            return True
    control_count = sum(1 for c in sample if '\x80' <= c <= '\x9f')
    if control_count > len(sample) * 0.005:
        return True
    combining_count = sum(1 for c in sample if unicodedata.category(c) == 'Mn')
    if combining_count > len(sample) * _COMBINING_CHAR_THRESHOLD:
        return True
    return False


def _normalize_unicode(text: str) -> str:
    if not text:
        return text
    return unicodedata.normalize('NFKC', text)


def _try_pypdf(raw: bytes) -> str:
    """pypdf all-or-nothing. Captura log de aviso; pagina que falha
    quebra o parser inteiro.

    Para tolerancia a falha de uma unica pagina, veja
    _try_pypdf_with_tolerance.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    parts = [page.extract_text() or "" for page in reader.pages]
    return _normalize_unicode("\n".join(parts))


def _try_pypdf_with_tolerance(raw: bytes) -> tuple[str, int, int]:
    """Extrai texto pagina-a-pagina, retornando o que conseguir.

    Returns:
        (text, pages_parsed, pages_total)

    Se a pagina 1 falha, retorna ("", 0, N). Se pagina N falha no
    meio, retorna texto das paginas 1..N-1 concatenado.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    parts = []
    pages_total = len(reader.pages)
    pages_parsed = 0
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
            parts.append(txt)
            pages_parsed = i + 1
        except Exception as exc:
            logger.warning(
                "pdf_extract page failed",
                extra={
                    "event_name": "pdf_extract_page_failed",
                    "parser": "pypdf",
                    "page_index": i,
                    "error_type": type(exc).__name__,
                },
            )
            break
    return _normalize_unicode("\n".join(parts)), pages_parsed, pages_total


def _try_pdfplumber(raw: bytes) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
    return _normalize_unicode("\n".join(parts))


def _try_pdfminer(raw: bytes) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract_text

    bio = io.BytesIO(raw)
    return _normalize_unicode(pdfminer_extract_text(bio))


_PARSER_NAMES = ("pypdf", "pdfplumber", "pdfminer")


def _count_pypdf_pages(raw: bytes) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        return 0


def _count_pdfplumber_pages(raw: bytes) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def parse_pdf_robust(
    raw: bytes,
    *,
    return_metadata: bool = False,
    allow_partial: bool = True,
) -> Any:
    """Tenta extrair texto do PDF com fallback entre parsers.

    Args:
        raw: bytes do PDF
        return_metadata: se True, retorna (text, metadata_dict);
            se False, retorna apenas text (string).
        allow_partial: se True, aceita texto parcial quando um
            parser falha no meio (pypdf page-by-page tolerant).
            Default True para maximizar recuperacao em PDFs malformados.

    Returns:
        - str: texto extraido (ou string vazia se todos os parsers falharem)
        - tuple: (text, metadata) com chaves: parser, file_size,
          pages_total, pages_parsed, error_type, error_message, partial

    Logs estruturados em warn para cada falha de parser.
    """
    metadata: Dict[str, Any] = {
        "parser": "none",
        "file_size": len(raw),
        "pages_total": 0,
        "pages_parsed": 0,
        "error_type": "",
        "error_message": "",
        "partial": False,
    }

    text = ""

    for parser_name in _PARSER_NAMES:
        try:
            if allow_partial and parser_name == "pypdf":
                partial_text, parsed, total = _try_pypdf_with_tolerance(raw)
                if partial_text:
                    if _has_encoding_corruption(partial_text):
                        logger.warning(
                            "pdf_extract encoding corruption detected in pypdf — falling through",
                            extra={
                                "event_name": "pdf_extract_encoding_corruption",
                                "parser": parser_name,
                                "pages_parsed": parsed,
                                "pages_total": total,
                                "sample": partial_text[:200],
                            },
                        )
                        continue
                    text = partial_text
                    metadata["parser"] = parser_name
                    metadata["pages_total"] = total
                    metadata["pages_parsed"] = parsed
                    metadata["partial"] = parsed < total
                    if metadata["partial"]:
                        logger.warning(
                            "pdf_extract partial",
                            extra={
                                "event_name": "pdf_extract_partial",
                                "parser": parser_name,
                                "pages_parsed": parsed,
                                "pages_total": total,
                            },
                        )
                    break
                continue

            parser_fn = globals()[f"_try_{parser_name}"]
            text = parser_fn(raw)
            if text and parser_name == "pypdf" and _has_encoding_corruption(text):
                logger.warning(
                    "pdf_extract encoding corruption in non-tolerance pypdf — falling through",
                    extra={
                        "event_name": "pdf_extract_encoding_corruption",
                        "parser": parser_name,
                        "sample": text[:200],
                    },
                )
                continue
            metadata["parser"] = parser_name
            if parser_name == "pypdf":
                metadata["pages_total"] = _count_pypdf_pages(raw)
                metadata["pages_parsed"] = metadata["pages_total"]
            elif parser_name == "pdfplumber":
                metadata["pages_total"] = _count_pdfplumber_pages(raw)
                metadata["pages_parsed"] = metadata["pages_total"]
            break
        except Exception as exc:
            metadata["error_type"] = type(exc).__name__
            metadata["error_message"] = str(exc)[:200]
            logger.warning(
                "pdf_extract parser failed",
                extra={
                    "event_name": "pdf_extract_parser_failed",
                    "parser": parser_name,
                    "error_type": metadata["error_type"],
                    "file_size": metadata["file_size"],
                },
            )
            continue

    if not text and allow_partial:
        for parser_name in ("pypdf", "pdfplumber", "pdfminer"):
            if parser_name == "pypdf":
                continue
            parser_fn = globals()[f"_try_{parser_name}"]
            try:
                text = parser_fn(raw)
                if text:
                    metadata["parser"] = parser_name
                    metadata["error_type"] = ""
                    if parser_name == "pdfplumber":
                        metadata["pages_total"] = _count_pdfplumber_pages(raw)
                        metadata["pages_parsed"] = metadata["pages_total"]
                    logger.warning(
                        "pdf_extract fallback used",
                        extra={
                            "event_name": "pdf_extract_fallback_used",
                            "fallback_parser": parser_name,
                            "file_size": metadata["file_size"],
                        },
                    )
                    break
            except Exception:
                continue

    if return_metadata:
        return text, metadata
    return text


__all__ = ["parse_pdf_robust"]
