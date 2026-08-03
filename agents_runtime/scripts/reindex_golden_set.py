"""Re-ingerir PDFs da pasta GoldenSet/ no Firestore (Fase D1.5).

Auto-descobre PDFs em GoldenSet/, extrai texto com pypdf e indexa
no Firestore real (agent-knowledge-v2 + agent-knowledge-v2-plain).
Suporta pdfplumber como fallback se pypdf falhar.

Uso:
    python -m scripts.reindex_golden_set [--phone 5511966830020]
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PHONE = os.getenv("REINDEX_PHONE", "5511966830020")
PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
GOLDENSET_DIR = Path(__file__).resolve().parent.parent.parent / "GoldenSet"

_FILENAME_CLASS_MAP = {
    "consumidor": ("legal", "legislacao", "cdc"),
    "cdc": ("legal", "legislacao", "cdc"),
    "protecao": ("legal", "legislacao", "lgpd"),
    "lgpd": ("legal", "legislacao", "lgpd"),
    "dados": ("legal", "legislacao", "lgpd"),
}


def _classify_filename(name: str) -> tuple:
    """Classifica o PDF pelo nome do arquivo."""
    lower = name.lower()
    for keyword, (klass, group, theme) in _FILENAME_CLASS_MAP.items():
        if keyword in lower:
            return klass, group, theme
    return "outros", "outros", name.rsplit(".", 1)[0][:30]


def _extract_pdf_text(path: Path) -> str:
    """Extrai texto de um PDF usando pypdf, com fallback para pdfplumber."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n".join(
            p.extract_text() or "" for p in reader.pages
        )
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("pypdf falhou para %s: %s, tentando pdfplumber...", path.name, exc)

    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join(
                p.extract_text() or "" for p in pdf.pages
            )
        if text.strip():
            return text
    except Exception as exc:
        logger.error("pdfplumber tambem falhou para %s: %s", path.name, exc)

    return ""


def discover_pdfs() -> list[dict]:
    """Varre GoldenSet/*.pdf e retorna lista de specs."""
    if not GOLDENSET_DIR.is_dir():
        logger.warning("GoldenSet/ nao encontrado em %s", GOLDENSET_DIR)
        return []

    docs = []
    for pdf_path in sorted(GOLDENSET_DIR.glob("*.pdf")):
        logger.info("Lendo %s...", pdf_path.name)
        text = _extract_pdf_text(pdf_path)
        if not text.strip():
            logger.warning("  texto vazio, pulando")
            continue

        klass, group, theme = _classify_filename(pdf_path.name)
        docs.append({
            "name": pdf_path.name,
            "text": text,
            "klass": klass,
            "group": group,
            "theme": theme,
        })
        logger.info("  OK %d chars, class=%s, group=%s, theme=%s",
                     len(text), klass, group, theme)

    return docs


def main() -> int:
    os.environ.setdefault("GCP_PROJECT", PROJECT)
    from core.rag import index_private_document

    docs = discover_pdfs()
    if not docs:
        logger.warning("Nenhum PDF encontrado em GoldenSet/")
        return 0

    failures = 0
    for spec in docs:
        text = spec["text"].strip()
        if len(text) < 100:
            logger.warning("%s muito curto (%d chars), skip", spec["name"], len(text))
            continue
        try:
            logger.info("Indexando %s (%d chars, class=%s)",
                        spec["name"], len(text), spec["klass"])
            result = asyncio.run(index_private_document(
                phone=PHONE,
                text_content=text,
                source_title=spec["name"],
                category=spec["klass"],
                class_=spec["klass"],
                group=spec["group"],
                theme=spec["theme"],
                metadata={
                    "filename": spec["name"],
                    "mime_type": "application/pdf",
                },
            ))
            if result.get("error"):
                logger.warning("  Erro: %s", result["error"])
                failures += 1
            else:
                logger.info(
                    "  OK chunks=%s chunks_indexed=%s",
                    result.get("chunks"),
                    result.get("chunks_indexed"),
                )
        except Exception as exc:
            logger.error("Falha ao indexar %s: %s", spec["name"], exc)
            failures += 1

    logger.info("Concluido. %d sucesso, %d falhas", len(docs) - failures, failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
