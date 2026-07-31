"""Re-ingerir PDF do GoldenSet/ na base REAL do Firestore (PT7 F4-D).

Uso:
    python -m scripts.reindex_golden_set

Le os PDFs do GoldenSet/, faz parse, chunk, categoria mockada, embed via
OpenAI real (precisa OPENAI_API_KEY valida) ou stub deterministico, e
indexa em agent-knowledge-v2 com phone 5511966830020.

Requer GOOGLE_APPLICATION_CREDENTIALS (gcloud auth applica) + OPENAI_API_KEY.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PHONE = "5511966830020"
GOLDENSET = Path(__file__).resolve().parents[2] / "GoldenSet"
PROJECT = "coherence-ominichannel-fs"


def _categorize_stub(source_name: str, text: str) -> dict:
    n = source_name.lower()
    if "cdc" in n or "consumidor" in text[:1000].lower():
        return {"class": "legal", "group": "legislacao", "theme": "codigo consumidor"}
    if "lgpd" in n or "protecao de dados" in text[:1000].lower():
        return {"class": "legal", "group": "legislacao", "theme": "lgpd"}
    if "manual" in n or "higiene" in n:
        return {"class": "saude", "group": "protocolo", "theme": "higiene"}
    return {"class": "outros", "group": "outros", "theme": source_name[:40]}


async def reindex_one(db, pdf_path: Path):
    from core.rag import (
        EMBEDDING_DIM,
        EMBEDDING_MODEL,
        PRIVATE_COLLECTION,
        SCHEMA_VERSION,
        _chunk_text,
        index_private_document,
    )

    from pypdf import PdfReader

    text = "\n\n".join(p.extract_text() or "" for p in PdfReader(str(pdf_path)).pages).strip()
    if not text:
        logger.warning("%s extraido vazio, skip", pdf_path.name)
        return None
    tax = _categorize_stub(pdf_path.name, text)
    logger.info("Indexando %s (%d chars, class=%s)", pdf_path.name, len(text), tax["class"])

    # Reaproveita index_private_document do pipeline real
    result = await index_private_document(
        phone=PHONE,
        text_content=text,
        source_title=pdf_path.name,
        category=tax["class"],
        class_=tax["class"],
        group=tax["group"],
        theme=tax["theme"],
        metadata={
            "filename": pdf_path.name,
            "mime_type": "application/pdf",
            "test_run": True,
            "reindex_pt7": True,
        },
    )
    return result


async def main() -> int:
    if not GOLDENSET.exists():
        logger.error("GoldenSet nao encontrado em %s", GOLDENSET)
        return 1
    pdfs = sorted(GOLDENSET.glob("*.pdf"))
    if not pdfs:
        logger.error("Nenhum PDF em GoldenSet/. Rode: python -m scripts.build_golden_set")
        return 1
    logger.info("PDFs: %s", [p.name for p in pdfs])

    failures = 0
    for pdf in pdfs:
        try:
            result = await reindex_one(None, pdf)
            if result is None:
                continue
            if result.get("error"):
                logger.warning("  erro retornado por index_private_document: %s", result["error"])
                failures += 1
            else:
                logger.info(
                    "  OK chunks=%s chunks_indexed=%s class=%s",
                    result.get("chunks"),
                    result.get("chunks_indexed"),
                    result.get("class"),
                )
        except Exception as exc:
            logger.error("Falha ao indexar %s: %s", pdf.name, exc)
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
