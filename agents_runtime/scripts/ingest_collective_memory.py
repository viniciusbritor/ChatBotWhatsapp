"""Memória coletiva persistente do ChatBotWhatsapp.

Diferente de ``owner-knowledge-v2`` (privado por telefone), a coleção
``collective-knowledge-v2`` armazena conteúdo **compartilhado** entre
todos os usuários autorizados do módulo "Agentes Omnichannel". Sem
filtro de ``owner_hash`` na leitura — qualquer contato da conta pode
recuperar.

Fontes aceitas (GCS):
- ``.txt`` / ``.md`` — texto puro.
- ``.pdf`` — extração via ``pypdf``.
- ``.json`` — lista de objetos com campos ``title``, ``text``, ``metadata``.

Cada chunk é mascarado via ``core.masker`` antes de gerar o embedding
OpenAI. O documento final carrega:

- ``schema_version=2``;
- ``embedding_model=RAG_EMBEDDING_MODEL``;
- ``embedding_dim=RAG_EMBEDDING_DIM``;
- ``vector_embedding: Vector``;
- ``source_kind``: ``gcs-object`` ou ``inline``;
- ``visibility``: ``collective``;
- ``created_at``: timestamp ISO em BRT.

Uso::

    python scripts/ingest_collective_memory.py \
        --bucket coherence-knowledge-prod \
        --object collective/manual-onboarding.md

    # ou texto inline:
    echo "..." | python scripts/ingest_collective_memory.py \
        --title "Manual de onboarding" --inline
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.cloud import firestore  # type: ignore  # noqa: E402
from google.cloud import storage  # type: ignore  # noqa: E402

from core.masker import mask_pii  # noqa: E402
from core.rag import (  # noqa: E402
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    PRIVATE_COLLECTION,
    SCHEMA_VERSION,
    _chunk_text,
    embed_documents,
)
from core.timezone import now_brt  # noqa: E402


logger = logging.getLogger("ingest_collective_memory")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


_COLLECTION_NAME = os.getenv("RAG_COLLECTIVE_COLLECTION", "collective-knowledge-v2")


def _project_id() -> str | None:
    return os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")


def _get_firestore():
    project = _project_id()
    if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
        return None
    return firestore.Client(project=project)


def _extract_text(bucket_name: str, object_name: str) -> str:
    client = storage.Client(project=_project_id())
    blob = client.bucket(bucket_name).blob(object_name)
    raw = blob.download_as_bytes()
    if object_name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if object_name.lower().endswith(".json"):
        items = json.loads(raw.decode("utf-8"))
        return "\n\n".join(f"{item.get('title','')}\n\n{item.get('text','')}" for item in items)
    return raw.decode("utf-8", errors="ignore")


async def _index_chunks(db: firestore.Client, chunks: list[str], *, title: str, metadata: dict, kind: str, reference: str) -> dict:
    """Index chunks durably in Firestore plain; embed as bonus."""
    from google.cloud.firestore_v1.vector import Vector  # type: ignore

    now = now_brt().isoformat()
    written = 0
    plain_batch = db.batch()
    vector_batch = db.batch()
    vector_pending = []
    plain_ids: list[str] = []
    vector_ids: list[str] = []

    for idx, chunk in enumerate(chunks):
        document_id = f"{(reference or title)[:80]}-{idx}".lower().replace(" ", "-")
        plain_id = f"{document_id}-history"
        vector_id = document_id
        base_data = {
            "title": mask_pii(title),
            "text_content": mask_pii(chunk),
            "schema_version": SCHEMA_VERSION,
            "source_kind": kind,
            "source_reference": reference,
            "visibility": "collective",
            "category": metadata.get("category", "general"),
            "metadata": {k: v for k, v in metadata.items() if k != "category"},
            "chunk_index": idx,
            "created_at": now,
            "language": "pt-BR",
        }
        plain_batch.set(db.collection(_COLLECTION_NAME).document(plain_id), base_data)
        plain_ids.append(plain_id)
        vector_pending.append((vector_id, base_data, chunk))
        written += 1

    await asyncio.to_thread(plain_batch.commit)
    logger.info("indexed_plain chunks=%s reference=%s", written, reference)

    vectors = await embed_documents(chunks)
    if vectors is not None and len(vectors) == len(chunks):
        for (vec_id, base_data, _chunk), vector in zip(vector_pending, vectors):
            data = dict(
                base_data,
                vector_embedding=Vector(vector),
                embedding_model=EMBEDDING_MODEL,
                embedding_dim=EMBEDDING_DIM,
            )
            vector_batch.set(db.collection(_COLLECTION_NAME + "-vector").document(vec_id), data)
            vector_ids.append(vec_id)
        try:
            await asyncio.to_thread(vector_batch.commit)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Vector commit failed (history kept) reference=%s error=%s",
                reference,
                exc,
            )
            vector_ids = []
    else:
        logger.info(
            "Vector skipped (history only) reference=%s embedding_unavailable",
            reference,
        )

    return {
        "doc_ids": plain_ids,
        "vector_doc_ids": vector_ids,
        "chunks": written,
        "collection": _COLLECTION_NAME,
        "vector_collection": _COLLECTION_NAME + "-vector",
    }


async def _run(args: argparse.Namespace) -> int:
    db = _get_firestore()
    if db is None:
        logger.error("firestore not configured (set GCP_PROJECT)")
        return 1

    if args.inline:
        text = args.title_payload or ""
        title_text = args.title  # noqa: F841
    else:
        text = _extract_text(args.bucket, args.object)

    if not text.strip():
        logger.error("empty document")
        return 2
    cleaned = mask_pii(text)
    chunks = _chunk_text(cleaned)
    if not chunks:
        return 3

    metadata = {
        "category": args.category,
        "tag": args.tag,
        "added_by": "scripts/ingest_collective_memory.py",
    }
    reference = f"{args.bucket}/{args.object}" if not args.inline else f"inline:{args.title}"
    kind = "gcs-object" if not args.inline else "inline"
    result = await _index_chunks(
        db,
        chunks,
        title=args.title,
        metadata=metadata,
        kind=kind,
        reference=reference,
    )
    logger.info(
        "ingest_ok title=%s chunks=%s collection=%s reference=%s",
        args.title,
        result.get("chunks"),
        _COLLECTION_NAME,
        reference,
    )
    logger.info(
        "embedding_model=%s dim=%s schema_version=%s superseded_private_collection=%s",
        EMBEDDING_MODEL,
        EMBEDDING_DIM,
        SCHEMA_VERSION,
        PRIVATE_COLLECTION,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestao de memoria coletiva do ChatBotWhatsapp")
    parser.add_argument("--bucket", default="")
    parser.add_argument("--object", default="")
    parser.add_argument("--inline", action="store_true", help="Carrega via --title-payload")
    parser.add_argument("--title-payload", default="")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", default="general")
    parser.add_argument("--tag", default="collective")
    args = parser.parse_args()
    if not args.inline and not (args.bucket and args.object):
        parser.error("--bucket e --object sao obrigatorios sem --inline")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
