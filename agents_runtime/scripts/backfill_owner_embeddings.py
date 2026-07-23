"""Backfill de embeddings para mensagens ja transacionadas.

Re-processa documentos existentes em ``conversation-memory-v2`` que nao
possuem ``owner_hash`` valido, recalcula o embedding OpenAI quando
necessario e grava os campos canonicos. Idempotente.

Uso::

    python scripts/backfill_owner_embeddings.py --dry-run
    python scripts/backfill_owner_embeddings.py

Parametros opcionais:

* ``--collection`` (default ``conversation-memory-v2``) — escolhe a
  colecao a varrer.
* ``--batch-size`` (default ``50``) — tamanho do batch Firestore.
* ``--max-docs`` (default ``0`` = sem limite) — limite de seguranca.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.cloud import firestore  # type: ignore  # noqa: E402

from core import rag  # noqa: E402
from core.rag import (  # noqa: E402
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    SCHEMA_VERSION,
)


logger = logging.getLogger("backfill_owner_embeddings")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _get_firestore():
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
        return None
    return firestore.Client(project=project)


def _needs_index(data: dict) -> bool:
    """Return True se o documento precisa de reescrita com owner_hash."""
    if not data.get("text_masked") and not data.get("text_content"):
        return False
    if not data.get("embedding_model") == EMBEDDING_MODEL:
        return True
    if int(data.get("embedding_dim", -1)) != EMBEDDING_DIM:
        return True
    if int(data.get("schema_version", -1)) != SCHEMA_VERSION:
        return True
    if "owner_hash" not in data:
        return True
    return False


async def _ensure_embedding(text: str) -> list | None:
    return await rag.embed_query(text)


async def _process_collection(db: firestore.Client, collection: str, *, batch_size: int, max_docs: int, dry_run: bool) -> dict:
    coll = db.collection(collection)
    processed = skipped = errors = 0
    counters: dict[str, int] = {}

    def chunks():
        docs = coll.stream()
        batch: list = []
        for doc in docs:
            batch.append(doc)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    for batch_docs in chunks():
        for doc in batch_docs:
            if max_docs and processed + skipped >= max_docs:
                return counters
            data = doc.to_dict() or {}
            if not _needs_index(data):
                skipped += 1
                continue
            text = data.get("text_masked") or data.get("text_content") or ""
            if not text.strip():
                skipped += 1
                continue
            try:
                vector = await _ensure_embedding(text[:2000])
            except Exception as exc:  # noqa: BLE001
                logger.warning("embed failed doc=%s error=%s", doc.id, exc)
                errors += 1
                continue
            if vector is None:
                errors += 1
                continue
            from google.cloud.firestore_v1.vector import Vector  # type: ignore

            updates = {
                "owner_hash": data.get("owner_hash")
                or rag._owner_hash(data.get("phone") or data.get("owner_id") or ""),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dim": EMBEDDING_DIM,
                "schema_version": SCHEMA_VERSION,
                "vector_embedding": Vector(vector),
                "backfilled_at": firestore.SERVER_TIMESTAMP,
            }
            if dry_run:
                counters["would_update"] = counters.get("would_update", 0) + 1
            else:
                doc_ref = db.collection(collection).document(doc.id)
                doc_ref.set(updates, merge=True)
                counters["updated"] = counters.get("updated", 0) + 1
            processed += 1
    counters["skipped"] = skipped
    counters["errors"] = errors
    counters["processed"] = processed
    return counters


async def _run(args: argparse.Namespace) -> int:
    db = _get_firestore()
    if db is None:
        logger.error("firestore not configured (set GCP_PROJECT e desabilite FIRESTORE_EMULATOR_HOST)")
        return 1
    started = time.monotonic()
    result = await _process_collection(
        db,
        args.collection,
        batch_size=args.batch_size,
        max_docs=args.max_docs,
        dry_run=args.dry_run,
    )
    elapsed = time.monotonic() - started
    logger.info(
        "summary collection=%s dry_run=%s elapsed_sec=%.1f counts=%s",
        args.collection,
        args.dry_run,
        elapsed,
        result,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill embeddings no Firestore Vector")
    parser.add_argument("--collection", default="conversation-memory-v2")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-docs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
