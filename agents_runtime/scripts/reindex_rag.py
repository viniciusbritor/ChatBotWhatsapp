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

    total_chunks = 0
    reindexed_docs = 0
    skipped_errors = 0

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

        if dry_run:
            total_chunks += len(chunks)
            reindexed_docs += 1
            continue

        vectors = await embed_documents(chunks)
        if vectors is None or len(vectors) != len(chunks):
            logger.error("embed_failed source=%s chunks=%d", source_title, len(chunks))
            skipped_errors += 1
            continue

        try:
            db.collection(PRIVATE_COLLECTION).document(doc.id).delete()
        except Exception as exc:
            logger.warning("delete_failed doc_id=%s exc=%s", doc.id, exc)

        import hashlib
        import time
        from core.rag import _vector_filters
        from google.cloud.firestore_v1.vector import Vector

        now = time.time()
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
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
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
            }
            payload["embedding"] = Vector(vector)

            try:
                new_doc_ref = db.collection(PRIVATE_COLLECTION).document(chunk_id)
                new_doc_ref.set(payload)
            except Exception as exc:
                logger.error("write_failed chunk_id=%s exc=%s", chunk_id, exc)
                skipped_errors += 1
                continue

            total_chunks += 1

        reindexed_docs += 1

    return {
        "status": "ok",
        "reindexed": reindexed_docs,
        "chunks": total_chunks,
        "errors": skipped_errors,
        "dry_run": dry_run,
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
