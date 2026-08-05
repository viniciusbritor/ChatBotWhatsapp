"""Migra dados de colecoes antigas para knowledge-database unificada.

Origens:
  agent-knowledge-v2    → scope="private" + owner_hash
  group-knowledge-v2    → scope="group"   + group_hash

Destino:
  knowledge-database (Vector, 1536d, OpenAI embeddings)

Uso:
  python -m scripts.migrate_to_knowledge_database --dry-run
  python -m scripts.migrate_to_knowledge_database
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import sys
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

SOURCE_COLLECTIONS = [
    {"name": "agent-knowledge-v2", "scope": "private", "hash_field": "owner_hash"},
    {"name": "group-knowledge-v2", "scope": "group", "hash_field": "group_hash"},
]

TARGET_COLLECTION = "knowledge-database"

BATCH_SIZE = 200


def _get_firestore():
    from google.cloud import firestore

    project = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
    return firestore.Client(project=project)


async def _migrate_collection(db, source_name: str, scope: str, hash_field: str, dry_run: bool) -> dict:
    source = db.collection(source_name)
    target = db.collection(TARGET_COLLECTION)

    migrated = 0
    skipped = 0
    errors = 0

    try:
        docs = list(source.limit(1).stream())
        if not docs:
            logger.info("source_empty name=%s", source_name)
            return {"source": source_name, "migrated": 0, "skipped": 0, "errors": 0}
    except Exception as exc:
        logger.warning("source_unavailable name=%s error=%s", source_name, exc)
        return {"source": source_name, "migrated": 0, "skipped": 0, "errors": 0}

    page_token = None
    while True:
        batch = db.batch()
        batch_count = 0

        query = source.limit(BATCH_SIZE)
        if page_token:
            query = query.start_after({"__name__": page_token})

        stream = list(query.stream())
        if not stream:
            break

        for doc in stream:
            data = doc.to_dict() or {}
            if not data.get("text_content") or not data.get("vector_embedding"):
                skipped += 1
                continue

            source_hash = data.get(hash_field, "")
            if not source_hash:
                skipped += 1
                continue

            target_id_parts = [scope, source_hash, data.get("source_title", "unknown")]
            chunk_idx = data.get("chunk_index")
            if chunk_idx is not None:
                target_id_parts.append(str(chunk_idx))
            target_id = hashlib.sha256(
                ":".join(target_id_parts).encode("utf-8")
            ).hexdigest()[:32]

            doc_data = {
                "scope": scope,
                hash_field: source_hash,
                "text_content": data.get("text_content", ""),
                "vector_embedding": data.get("vector_embedding"),
                "source_title": data.get("source_title", ""),
                "source_url": data.get("source_url"),
                "category": data.get("category", ""),
                "class": data.get("class"),
                "group": data.get("group"),
                "theme": data.get("theme"),
                "chunk_index": data.get("chunk_index"),
                "chunk_type": data.get("chunk_type", "body"),
                "section_title": data.get("section_title", ""),
                "language": data.get("language", "pt-BR"),
                "embedding_model": data.get("embedding_model", "text-embedding-3-small"),
                "embedding_dim": data.get("embedding_dim", 1536),
                "schema_version": int(data.get("schema_version", 3)),
                "created_at": data.get("created_at", ""),
            }

            if not dry_run:
                batch.set(target.document(target_id), doc_data)
            batch_count += 1
            migrated += 1

        if not dry_run and batch_count > 0:
            try:
                await asyncio.to_thread(batch.commit)
                logger.info("batch_committed source=%s count=%d total=%d", source_name, batch_count, migrated)
            except Exception as exc:
                logger.error("batch_commit_failed source=%s count=%d error=%s", source_name, batch_count, exc)
                errors += batch_count

        page_token = stream[-1].id if stream else None
        if len(stream) < BATCH_SIZE:
            break

    return {"source": source_name, "migrated": migrated, "skipped": skipped, "errors": errors}


async def main():
    parser = argparse.ArgumentParser(description="Migrate knowledge collections to knowledge-database")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--source", help="Migrate only this source collection")
    args = parser.parse_args()

    db = _get_firestore()

    sources = SOURCE_COLLECTIONS
    if args.source:
        sources = [s for s in SOURCE_COLLECTIONS if s["name"] == args.source]
        if not sources:
            logger.error("source_not_found name=%s", args.source)
            sys.exit(1)

    total = {"migrated": 0, "skipped": 0, "errors": 0}
    for src in sources:
        logger.info("migrating source=%s scope=%s dry_run=%s", src["name"], src["scope"], args.dry_run)
        result = await _migrate_collection(
            db, src["name"], src["scope"], src["hash_field"], args.dry_run,
        )
        for k in ("migrated", "skipped", "errors"):
            total[k] += result[k]
        logger.info("source_done result=%s", result)

    logger.info("migration_complete %s", {**total, "dry_run": args.dry_run, "target": TARGET_COLLECTION})
    return total


if __name__ == "__main__":
    asyncio.run(main())
