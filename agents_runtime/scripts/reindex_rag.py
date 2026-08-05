"""Re-indexa documentos do Firestore Vector com novo chunking (A+B).

Usage:
    python -m scripts.reindex_rag --phone=+5511966830020
    python -m scripts.reindex_rag --phone=+5511966830020 --dry-run
    python -m scripts.reindex_rag --phone=+5511966830020 --collection=group-knowledge-v2

A: word-aware fallback (nunca corta mid-word)
B: overlap 25% (300 chars em vez de 180)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("reindex_rag")

_AGENTS_RUNTIME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_AGENTS_RUNTIME))


async def reindex_private(phone: str, dry_run: bool = False) -> dict:
    from core.rag import (
        _chunk_text,
        _get_firestore,
        _owner_hash,
        embed_documents,
        PRIVATE_COLLECTION,
    )
    from core.text_cleaner import clean_portuguese

    db = _get_firestore()
    if db is None:
        logger.error("Firestore unavailable")
        return {"status": "error", "reason": "firestore_unavailable"}

    owner_hash = _owner_hash(phone)
    logger.info("phone=%s owner_hash=%s collection=%s", phone, owner_hash, PRIVATE_COLLECTION)

    docs = list(
        db.collection(PRIVATE_COLLECTION)
        .where("owner_hash", "==", owner_hash)
        .stream()
    )

    if not docs:
        logger.info("no_documents_found")
        return {"status": "ok", "reindexed": 0, "chunks": 0}

    import hashlib
    import time
    from google.cloud.firestore_v1.vector import Vector

    all_chunks = []
    all_payloads = []
    old_doc_ids = []

    for doc in docs:
        data = doc.to_dict() or {}
        original_text = data.get("text_content") or data.get("text") or ""
        source_title = data.get("source_title", doc.id)

        if not original_text.strip():
            logger.info("skip_empty source=%s", source_title)
            continue

        clean_text = clean_portuguese(original_text)
        chunks = _chunk_text(clean_text, max_chars=1200, overlap=300)
        logger.info(
            "source=%s old_chunks=1 new_chunks=%d text_len=%d",
            source_title, len(chunks), len(original_text),
        )

        all_chunks.extend(chunks)
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(
                f"{doc.id}:{i}:{chunk[:50]}".encode("utf-8")
            ).hexdigest()[:16]
            payload = {
                "owner_hash": owner_hash,
                "text_content": chunk,
                "source_title": source_title,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "class": data.get("class", ""),
                "group": data.get("group", ""),
                "theme": data.get("theme", ""),
                "language": data.get("language", "pt"),
                "embedding_model": "text-embedding-3-small",
                "embedding_dim": 1536,
                "schema_version": 2,
                "created_at": data.get("created_at", ""),
            }
            all_payloads.append((chunk_id, payload))
        old_doc_ids.append(doc.id)

    logger.info(
        "collected %d chunks from %d sources for batch embedding",
        len(all_chunks), len(old_doc_ids),
    )

    if dry_run:
        return {
            "status": "ok",
            "reindexed": len(old_doc_ids),
            "chunks": len(all_chunks),
            "errors": 0,
            "dry_run": True,
        }

    if not all_chunks:
        return {"status": "ok", "reindexed": 0, "chunks": 0}

    batch_size = 10
    all_vectors = []
    for batch_start in range(0, len(all_chunks), batch_size):
        batch = all_chunks[batch_start : batch_start + batch_size]
        logger.info(
            "embedding batch %d-%d/%d",
            batch_start, batch_start + len(batch), len(all_chunks),
        )
        vectors = await embed_documents(batch)
        if vectors is None:
            logger.error("embed_batch_failed offset=%d", batch_start)
            return {
                "status": "error",
                "reason": "embed_batch_failed",
                "offset": batch_start,
                "reindexed": 0,
                "chunks": 0,
            }
        if len(vectors) != len(batch):
            logger.error(
                "embed_batch_mismatch expected=%d got=%d offset=%d",
                len(batch), len(vectors), batch_start,
            )
            return {
                "status": "error",
                "reason": "embed_batch_mismatch",
                "offset": batch_start,
                "reindexed": 0,
                "chunks": 0,
            }
        all_vectors.extend(vectors)

    for doc_id in old_doc_ids:
        try:
            db.collection(PRIVATE_COLLECTION).document(doc_id).delete()
        except Exception as exc:
            logger.warning("delete_failed doc_id=%s exc=%s", doc_id, exc)

    now = time.time()
    skipped_errors = 0
    for (chunk_id, payload), vector in zip(all_payloads, all_vectors):
        payload["vector_embedding"] = Vector(vector)
        payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
        try:
            db.collection(PRIVATE_COLLECTION).document(chunk_id).set(payload)
        except Exception as exc:
            logger.error("write_failed chunk_id=%s exc=%s", chunk_id, exc)
            skipped_errors += 1

    return {
        "status": "ok",
        "reindexed": len(old_doc_ids),
        "chunks": len(all_payloads) - skipped_errors,
        "errors": skipped_errors,
    }


async def main():
    parser = argparse.ArgumentParser(description="Re-index RAG documents")
    parser.add_argument("--phone", required=True, help="Phone number (owner)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--collection", default="agent-knowledge-v2",
                        help="Collection name (default: agent-knowledge-v2)")
    args = parser.parse_args()

    os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

    if args.collection != "agent-knowledge-v2":
        logger.warning("Only agent-knowledge-v2 supported for now; got %s", args.collection)

    result = await reindex_private(args.phone, dry_run=args.dry_run)
    logger.info("result=%s", result)


if __name__ == "__main__":
    asyncio.run(main())
