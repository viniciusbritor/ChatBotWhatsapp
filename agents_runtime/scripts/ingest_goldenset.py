"""Ingere os PDFs do GoldenSet na base de conhecimento (chunks + sections).

Valida o pipeline completo: parse_pdf_hybrid -> clean_portuguese ->
chunk_text_semantic -> embed_documents -> index_private_document ->
index_private_sections.
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest_goldenset")

GOLDENSET = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "GoldenSet",
)


async def ingest(phone: str, pdf_name: str, class_: str, category: str):
    from core.pdf_extract import parse_pdf_hybrid, _check_text_quality
    from core.rag import index_private_document

    path = os.path.join(GOLDENSET, pdf_name)
    if not os.path.exists(path):
        logger.error("PDF nao encontrado: %s", path)
        return

    with open(path, "rb") as f:
        raw = f.read()
    logger.info("=== %s (%d bytes) ===", pdf_name, len(raw))

    text = parse_pdf_hybrid(raw)
    logger.info("  extraido: %d chars, quality=%.3f", len(text), _check_text_quality(text))
    if len(text) < 10000:
        logger.error("  texto curto demais: %d chars", len(text))
        return

    result = await index_private_document(
        phone=phone,
        text_content=text,
        source_title=pdf_name,
        source_url=None,
        category=category,
        metadata={"filename": pdf_name, "mime_type": "application/pdf", "source": "goldenset"},
        class_=class_,
        group="",
        theme="",
    )
    logger.info("  resultado: chunks=%s indexed=%s sections=%s",
                result.get("chunks"), result.get("chunks_indexed"),
                result.get("sections", {}).get("count") if isinstance(result.get("sections"), dict) else "?")


async def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else "5511966830020"
    await ingest(phone, "Codigo-do-consumidor-FINAL.pdf", "legal", "legislacao")
    await ingest(phone, "Lei_geral_protecao_dados_pessoais_1ed.pdf", "legal", "legislacao")
    logger.info("done")


if __name__ == "__main__":
    asyncio.run(main())
