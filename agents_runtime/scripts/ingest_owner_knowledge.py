"""Per-owner knowledge ingestion.

Loads text or PDF files from Google Cloud Storage, extracts content, chunks it,
masks PII, generates OpenAI embeddings and persists into the owner's vector
collection. The collection name includes the owner id so RAG queries can be
filtered with `owner_hash == owner_id`.

Usage:
    python scripts/ingest_owner_knowledge.py \
        --owner-id 5511966830020 \
        --account-id jennifer \
        --bucket coherence-knowledge-prod \
        --object caminho/do/livro.pdf \
        --title "Codigo Penal Comentado" \
        --category legislacao
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.rag import (  # noqa: E402  pylint: disable=wrong-import-position
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    SCHEMA_VERSION,
    RETENTION_DAYS,
    index_private_document,
)


logger = logging.getLogger("ingest_owner_knowledge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _extract_text(bucket_name: str, object_name: str) -> str:
    from google.cloud import storage

    client = storage.Client(project=os.getenv("GCP_PROJECT"))
    blob = client.bucket(bucket_name).blob(object_name)
    raw = blob.download_as_bytes()
    if object_name.lower().endswith(".pdf"):
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8", errors="ignore")


async def _run(args: argparse.Namespace) -> int:
    text = _extract_text(args.bucket, args.object)
    if not text.strip():
        logger.error("empty document: gs://%s/%s", args.bucket, args.object)
        return 1
    metadata = {
        "owner_id": args.owner_id,
        "account_id": args.account_id,
        "source_bucket": args.bucket,
        "source_object": args.object,
        "ingestor": "scripts/ingest_owner_knowledge.py",
    }
    result = await index_private_document(
        phone=args.owner_id,
        text_content=text,
        source_title=args.title,
        source_url=f"gs://{args.bucket}/{args.object}",
        category=args.category,
        metadata=metadata,
    )
    if "error" in result:
        logger.error("ingestion_failed error=%s", result.get("error"))
        return 2
    logger.info(
        "ingestion_ok owner=%s account=%s chunks=%s embedding_model=%s dim=%s schema_version=%s retention_days=%s",
        args.owner_id,
        args.account_id,
        result.get("chunks"),
        EMBEDDING_MODEL,
        EMBEDDING_DIM,
        SCHEMA_VERSION,
        RETENTION_DAYS,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a document for a WhatsApp account owner")
    parser.add_argument("--owner-id", required=True, help="Owner phone (digits only)")
    parser.add_argument("--account-id", required=True, help="Evolution instance / account id")
    parser.add_argument("--bucket", required=True, help="GCS bucket")
    parser.add_argument("--object", required=True, help="Object name inside the bucket")
    parser.add_argument("--title", required=True, help="Display title")
    parser.add_argument("--category", default="legislacao")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
