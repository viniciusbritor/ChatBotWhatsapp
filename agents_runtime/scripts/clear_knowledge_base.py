"""Limpa a base de conhecimento do phone especificado (PT7 F4-B).

Uso:
    python -m scripts.clear_knowledge_base --phone 5511966830020 [--all]

Apaga em agent-knowledge-v2 e agent-knowledge-v2-plain apenas os
documentos do owner_hash do phone. Se --all, apaga TUDO.

Requer GOOGLE_APPLICATION_CREDENTIALS apontando para um service account
com permissao firestore.documents.delete no projeto
coherence-ominichannel-fs.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


def _owner_hash(phone: str) -> str:
    normalized = "".join(c for c in str(phone) if c.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _delete_phone_knowledge(phone: str, dry_run: bool = False) -> int:
    from google.cloud import firestore

    db = firestore.Client(project=PROJECT)
    owner_hash = _owner_hash(phone)
    removed = 0
    for collection in ("agent-knowledge-v2", "agent-knowledge-v2-plain"):
        logger.info("Scanning %s for owner_hash=%s", collection, owner_hash[:8])
        coll = db.collection(collection)
        docs = list(coll.where("owner_hash", "==", owner_hash).stream())
        logger.info("  found %d docs", len(docs))
        for doc in docs:
            if dry_run:
                logger.info("  [DRY] would delete %s/%s", collection, doc.id)
            else:
                logger.info("  deleting %s/%s", collection, doc.id)
                doc.reference.delete()
                removed += 1
    return removed


def _delete_all_knowledge(dry_run: bool = False) -> int:
    from google.cloud import firestore

    db = firestore.Client(project=PROJECT)
    removed = 0
    for collection in (
        "agent-knowledge-v2",
        "agent-knowledge-v2-plain",
        "public-knowledge-v2",
        "public-knowledge-v2-plain",
        "collective-knowledge-v2",
        "collective-knowledge-v2-plain",
    ):
        coll = db.collection(collection)
        docs = list(coll.stream())
        logger.info("Collection %s: %d docs", collection, len(docs))
        for doc in docs:
            if dry_run:
                logger.info("  [DRY] would delete %s/%s", collection, doc.id)
            else:
                doc.reference.delete()
                removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", default="5511966830020")
    parser.add_argument("--all", action="store_true",
                        help="Apagar TODA a base (todas as collections knowledge)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all:
        n = _delete_all_knowledge(dry_run=args.dry_run)
        logger.info("Total removidos: %d", n)
    else:
        n = _delete_phone_knowledge(args.phone, dry_run=args.dry_run)
        logger.info("Docs removidos para phone=%s: %d", args.phone, n)

    return 0


if __name__ == "__main__":
    sys.exit(main())
