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
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _try_pypdf(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(parts)


def _try_pdfplumber(raw: bytes) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
    return "\n".join(parts)


def _try_pdfminer(raw: bytes) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract_text

    bio = io.BytesIO(raw)
    return pdfminer_extract_text(bio)


_PARSER_NAMES = ("pypdf", "pdfplumber", "pdfminer")


def parse_pdf_robust(
    raw: bytes,
    *,
    return_metadata: bool = False,
) -> Any:
    """Tenta extrair texto do PDF com fallback entre parsers.

    Args:
        raw: bytes do PDF
        return_metadata: se True, retorna (text, metadata_dict);
            se False, retorna apenas text (string).

    Returns:
        - str: texto extraido (ou string vazia se todos os parsers falharem)
        - tuple: (text, metadata) com chaves: parser, file_size,
          pages_total, pages_parsed, error_type, error_message

    Logs estruturados em warn para cada falha de parser.
    """
    metadata: Dict[str, Any] = {
        "parser": "none",
        "file_size": len(raw),
        "pages_total": 0,
        "pages_parsed": 0,
        "error_type": "",
        "error_message": "",
    }

    text = ""
    for parser_name in _PARSER_NAMES:
        parser_fn = globals()[f"_try_{parser_name}"]



        try:
            text = parser_fn(raw)
            metadata["parser"] = parser_name
            if parser_name == "pypdf":
                try:
                    from pypdf import PdfReader

                    metadata["pages_total"] = len(
                        PdfReader(io.BytesIO(raw)).pages,
                    )
                    metadata["pages_parsed"] = metadata["pages_total"]
                except Exception:
                    pass
            elif parser_name == "pdfplumber":
                try:
                    import pdfplumber

                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        metadata["pages_total"] = len(pdf.pages)
                        metadata["pages_parsed"] = metadata["pages_total"]
                except Exception:
                    pass
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

    if return_metadata:
        return text, metadata
    return text


__all__ = ["parse_pdf_robust"]
