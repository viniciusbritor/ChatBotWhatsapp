"""Firestore access layer for ChatBotWhatsapp.

Architecture (post 23/07/2026):

- **Every chat turn** is persisted into ``message-history`` (plain
  Firestore) keyed by ``owner_hash`` + ``message_id``. Firestore Vector
  is **not** used for interactions; the conversation log is durable even
  when OpenAI / embeddings fail.
- **Firestore Vector** (``agent-knowledge-v2``,
  ``collective-knowledge-v2`` and ``public-knowledge-v2``) is reserved
  for documents that benefit from semantic search: laws, editais, books
  and publicly distributed knowledge. ``scripts/ingest_*.py`` provide
  the loader; runtime only reads.
- The OpenAI embedding call is only used in the document ingestion
  pipelines (``index_shared_document``, ``index_private_document`` and
  ``ingest_collective_memory``). It is never used on the chat hot path.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from core.masker import mask_pii
from core.secrets import get_secret
from core.timezone import now_brt

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "1536"))
EMBEDDING_BASE_URL = os.getenv(
    "RAG_EMBEDDING_BASE_URL",
    "https://api.openai.com/v1/embeddings",
)
SCHEMA_VERSION = int(os.getenv("RAG_SCHEMA_VERSION", "2"))

# Soft limits for RAG individual ingestion. The hard cap was removed in
# F4d.5 for the group pipeline; the same soft limit semantics now apply
# to private documents so very large files do not blow up embedding
# cost or Firestore quotas. The defaults mirror the group ones but can
# be tuned per environment without code changes.
PRIVATE_CHUNKS_SOFT_LIMIT = int(
    os.getenv("RAG_PRIVATE_CHUNKS_SOFT_LIMIT", "500")
)
PRIVATE_CHARS_SOFT_LIMIT = int(
    os.getenv("RAG_PRIVATE_CHARS_SOFT_LIMIT", "1000000")
)

# Minimum similarity score for retrieval (Phase H). Same default for
# private and group retrievers; tunable via env.
RAG_RETRIEVE_MIN_SCORE = float(
    os.getenv("RAG_RETRIEVE_MIN_SCORE", "0.5")
)

# Plain Firestore collections.
MESSAGE_HISTORY_COLLECTION = os.getenv(
    "RAG_MESSAGE_HISTORY_COLLECTION", "message-history"
)
MESSAGE_HISTORY_RETENTION_DAYS = int(
    os.getenv("RAG_MESSAGE_HISTORY_RETENTION_DAYS", "365")
)

# Firestore Vector collections (documents only, never chat turns).
PRIVATE_COLLECTION = os.getenv("RAG_PRIVATE_COLLECTION", "agent-knowledge-v2")
SHARED_COLLECTION = os.getenv("RAG_SHARED_COLLECTION", "public-knowledge-v2")
COLLECTIVE_COLLECTION = os.getenv("RAG_COLLECTIVE_COLLECTION", "collective-knowledge-v2")
LEGACY_MEMORY_COLLECTION = os.getenv(
    "RAG_MEMORY_COLLECTION", "conversation-memory-v2"
)

EMBEDDING_CONCURRENCY = int(os.getenv("RAG_EMBEDDING_CONCURRENCY", "4"))


def _now_brt() -> datetime:
    return now_brt()


def _owner_hash(phone: str) -> str:
    normalized = "".join(char for char in str(phone) if char.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _validate_embedding(embedding: Optional[Sequence[float]]) -> Optional[List[float]]:
    if embedding is None:
        return None
    vector = list(embedding)
    if len(vector) != EMBEDDING_DIM:
        logger.warning(
            "Embedding rejected: expected_dim=%s actual_dim=%s",
            EMBEDDING_DIM,
            len(vector),
        )
        return None
    return vector


def _embed_direct(text: str) -> Optional[List[float]]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI embedding unavailable: api_key_missing")
        return None
    api_key = api_key.strip().lstrip("\ufeff")
    try:
        response = requests.post(
            EMBEDDING_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"input": text, "model": EMBEDDING_MODEL, "encoding_format": "float"},
            timeout=30,
        )
    except Exception as exc:
        logger.error("OpenAI embedding request failed: %s", exc)
        return None
    if response.status_code >= 400:
        logger.error(
            "OpenAI embedding failed: http_status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        return None
    data = response.json()
    items = data.get("data") or []
    if not items:
        logger.error("OpenAI embedding returned empty data")
        return None
    return _validate_embedding(items[0].get("embedding"))


def embed_best(text: str) -> Optional[List[float]]:
    return _embed_direct(text)


def _get_firestore():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("Firestore unavailable: %s", exc)
        return None


async def embed_query(text: str) -> Optional[List[float]]:
    """Embed a chunk of text via OpenAI. Used only by ingestion pipelines."""
    clean_text = mask_pii(str(text or "")).strip()
    if not clean_text:
        return None
    try:
        return await asyncio.to_thread(embed_best, clean_text)
    except Exception as exc:
        logger.error("Embedding failed: %s", exc)
        return None


async def embed_documents(texts: List[str]) -> Optional[List[List[float]]]:
    semaphore = asyncio.Semaphore(max(1, EMBEDDING_CONCURRENCY))

    async def embed_one(text: str) -> Optional[List[float]]:
        async with semaphore:
            return await embed_query(text)

    vectors = await asyncio.gather(*(embed_one(text) for text in texts))
    if any(vector is None for vector in vectors):
        return None
    return [vector for vector in vectors if vector is not None]


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 180) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for separator in ["\n\n", "\n", ". ", "? ", "! "]:
                last_separator = text.rfind(separator, start, end)
                if last_separator > start + max_chars // 2:
                    end = last_separator + len(separator)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [chunk for chunk in chunks if chunk]


def _vector_filters(owner_hash: Optional[str] = None) -> List[Tuple[str, str, Any]]:
    filters: List[Tuple[str, str, Any]] = [
        ("embedding_model", "==", EMBEDDING_MODEL),
        ("embedding_dim", "==", EMBEDDING_DIM),
        ("schema_version", "==", SCHEMA_VERSION),
    ]
    if owner_hash:
        filters.insert(0, ("owner_hash", "==", owner_hash))
    return filters


async def _find_nearest(
    db: Any,
    collection_name: str,
    query_vector: List[float],
    limit: int,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
) -> List[Any]:
    from google.cloud.firestore_v1.base_query import FieldFilter
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector

    def execute() -> List[Any]:
        query = db.collection(collection_name)
        for field, operator, value in filters or []:
            query = query.where(filter=FieldFilter(field, operator, value))
        vector_query = query.find_nearest(
            vector_field="vector_embedding",
            query_vector=Vector(query_vector),
            limit=max(1, min(int(limit), 50)),
            distance_measure=DistanceMeasure.COSINE,
            distance_result_field="vector_distance",
        )
        return list(vector_query.get())

    return await asyncio.to_thread(execute)


def _score_document(document: Any, data: Dict[str, Any]) -> float:
    distance = data.get("vector_distance")
    if distance is None:
        distance = getattr(document, "distance", None)
    if distance is None:
        return 0.0
    return max(-1.0, min(1.0, 1.0 - float(distance)))


# ----------------------------------------------------------------------
# Conversation persistence (plain Firestore only)
# ----------------------------------------------------------------------


def time_ns() -> int:
    import time

    return time.time_ns()


async def index_conversation_message(
    phone: str,
    text: str,
    direction: str,
    message_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    response_identity: str = "Jennifer",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a chat turn into ``message-history`` (plain Firestore).

    This function never raises: failures in Firestore are recorded and the
    function returns a structured status. The runtime never blocks on
    history writes.
    """
    clean_text = mask_pii(str(text or "")).strip()
    if len(clean_text) < 3:
        return {"status": "skipped", "reason": "empty_text"}

    if not phone or not str(phone).strip():
        # Defensive: refuse to persist a turn that has no owner id (e.g.
        # group message without sender phone). Caller is expected to fall
        # back to a per-account owner phone before reaching here.
        return {"status": "skipped", "reason": "missing_phone"}

    db = _get_firestore()
    if db is None:
        return {"status": "skipped", "reason": "firestore_unavailable"}

    owner_hash = _owner_hash(phone)
    stable_key = message_id or f"{time_ns()}:{direction}:{clean_text}"
    document_id = hashlib.sha256(
        f"history:{owner_hash}:{stable_key}".encode("utf-8")
    ).hexdigest()[:32]
    now = _now_brt()
    payload: Dict[str, Any] = {
        "owner_hash": owner_hash,
        "conversation_id": conversation_id or owner_hash,
        "message_id": message_id or document_id,
        "turn_id": turn_id or document_id,
        "direction": direction,
        "agent_id": agent_id or "jennifier",
        "response_identity": response_identity,
        "text_masked": clean_text[:4000],
        "schema_version": SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=MESSAGE_HISTORY_RETENTION_DAYS)).isoformat(),
        "extra": extra or {},
    }

    try:
        await asyncio.to_thread(
            db.collection(MESSAGE_HISTORY_COLLECTION)
            .document(document_id)
            .set,
            payload,
        )
        status = "indexed"
        error = ""
    except Exception as exc:  # noqa: BLE001
        status = "history_failed"
        error = str(exc)
        logger.error(
            "History persist FAILED phone=%s message_id=%s error=%s",
            phone,
            message_id,
            exc,
        )

    return {
        "status": status,
        "doc_id": document_id,
        "collection": MESSAGE_HISTORY_COLLECTION,
        "error": error,
    }


async def search_conversation_memory(phone: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return the most recent turns for ``phone`` that match ``query``.

    Plain Firestore only (no embeddings). Match is substring on the masked
    text; results are ordered by ``created_at`` desc.
    """
    if not phone or not str(phone).strip():
        logger.warning("search_conversation_memory refused empty phone")
        return []
    db = _get_firestore()
    if db is None:
        return []
    owner_hash = _owner_hash(phone)
    needle = (query or "").strip().lower()
    try:

        def fetch() -> List[Any]:
            query_obj = (
                db.collection(MESSAGE_HISTORY_COLLECTION)
                .where("owner_hash", "==", owner_hash)
                .order_by("created_at", direction="DESCENDING")
                .limit(50)
            )
            return list(query_obj.stream())

        docs = await asyncio.to_thread(fetch)
    except Exception as exc:
        logger.warning("History search failed phone=%s error=%s", phone, exc)
        return []

    results: List[Dict[str, Any]] = []
    for document in docs:
        data = document.to_dict() or {}
        text = str(data.get("text_masked", ""))
        if needle and needle not in text.lower():
            continue
        results.append(
            {
                "text": text,
                "direction": data.get("direction", "in"),
                "agent_id": data.get("agent_id", "jennifier"),
                "response_identity": data.get("response_identity", "Jennifer"),
                "created_at": data.get("created_at"),
                "score": 1.0,
            }
        )
        if len(results) >= limit:
            break
    return results


async def list_message_history(phone: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Return the most recent turns for ``phone`` (no query filter)."""
    if not phone or not str(phone).strip():
        logger.warning("list_message_history refused empty phone")
        return []
    db = _get_firestore()
    if db is None:
        return []
    owner_hash = _owner_hash(phone)
    try:

        def fetch() -> List[Any]:
            query_obj = (
                db.collection(MESSAGE_HISTORY_COLLECTION)
                .where("owner_hash", "==", owner_hash)
                .order_by("created_at", direction="DESCENDING")
                .limit(limit)
            )
            return list(query_obj.stream())

        docs = await asyncio.to_thread(fetch)
    except Exception as exc:
        logger.warning("History list failed phone=%s error=%s", phone, exc)
        return []

    results: List[Dict[str, Any]] = []
    for document in docs:
        data = document.to_dict() or {}
        results.append(
            {
                "doc_id": document.id,
                "direction": data.get("direction"),
                "text": data.get("text_masked", ""),
                "agent_id": data.get("agent_id", "jennifier"),
                "response_identity": data.get("response_identity", "Jennifer"),
                "created_at": data.get("created_at"),
            }
        )
    return results


# ----------------------------------------------------------------------
# Document ingestion (Firestore Vector)
# ----------------------------------------------------------------------


async def index_private_document(
    phone: str,
    text_content: str,
    source_title: str,
    source_url: Optional[str] = None,
    category: str = "legislacao",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Index a private document (book/edital) into ``agent-knowledge-v2``.

    Soft limits mirror the group pipeline (F4d.5). When the input exceeds
    the configured thresholds, the document is still indexed end-to-end
    and the returned payload reports ``truncated=True`` plus the reason.
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}
    clean_content = mask_pii(text_content)
    chars_soft_limit = PRIVATE_CHARS_SOFT_LIMIT
    chunks_soft_limit = PRIVATE_CHUNKS_SOFT_LIMIT
    chunks = _chunk_text(clean_content)
    if not chunks:
        return {"error": "empty_content"}

    truncated = False
    truncated_reason: Optional[str] = None
    if len(text_content) > chars_soft_limit:
        truncated = True
        truncated_reason = "chars_above_soft_limit"
    if len(chunks) > chunks_soft_limit:
        truncated = True
        if truncated_reason is None:
            truncated_reason = "chunks_above_soft_limit"

    plain_batch = db.batch()
    vector_batch = db.batch()
    plain_ids: List[str] = []
    vector_ids: List[str] = []

    owner_hash = _owner_hash(phone)
    now = _now_brt().isoformat()
    protected_fields = {
        "owner_hash",
        "text_content",
        "vector_embedding",
        "embedding_model",
        "embedding_dim",
        "schema_version",
    }
    safe_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if key not in protected_fields
    }

    for index, chunk in enumerate(chunks):
        document_id = hashlib.sha256(
            f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
        ).hexdigest()[:32]
        plain_id = f"{document_id}-plain"
        common = {
            **safe_metadata,
            "owner_hash": owner_hash,
            "text_content": chunk,
            "source_title": mask_pii(source_title),
            "source_url": source_url,
            "category": category,
            "chunk_index": index,
            "language": "pt-BR",
            "created_at": now,
            "schema_version": SCHEMA_VERSION,
        }
        plain_batch.set(
            db.collection(PRIVATE_COLLECTION + "-plain").document(plain_id),
            common,
        )
        plain_ids.append(plain_id)

    await asyncio.to_thread(plain_batch.commit)

    vectors = await embed_documents(chunks)
    if vectors is not None and len(vectors) == len(chunks):
        from google.cloud.firestore_v1.vector import Vector

        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            document_id = hashlib.sha256(
                f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
            ).hexdigest()[:32]
            data = dict(
                common,
                vector_embedding=Vector(vector),
                embedding_model=EMBEDDING_MODEL,
                embedding_dim=EMBEDDING_DIM,
            )
            vector_batch.set(db.collection(PRIVATE_COLLECTION).document(document_id), data)
            vector_ids.append(document_id)
        try:
            await asyncio.to_thread(vector_batch.commit)
        except Exception as exc:
            logger.warning("Vector commit failed (plain kept) error=%s", exc)
            vector_ids = []

    return {
        "doc_ids": plain_ids,
        "vector_doc_ids": vector_ids,
        "owner_hash": owner_hash,
        "chunks": len(chunks),
        "chars": len(text_content),
        "truncated": truncated,
        "truncated_reason": truncated_reason,
        "source_title": mask_pii(source_title),
        "collection": PRIVATE_COLLECTION + "-plain",
        "vector_collection": PRIVATE_COLLECTION,
    }


async def search_legal_knowledge(
    phone: str,
    query: str,
    k: int = 5,
    min_score: float = 0.5,
) -> Dict[str, Any]:
    db = _get_firestore()
    if db is None:
        return {"results": [], "error": "firestore_unavailable"}
    query_vector = await embed_query(query)
    if query_vector is None:
        return {"results": [], "error": "embedding_failed"}
    try:
        documents = await _find_nearest(
            db,
            PRIVATE_COLLECTION,
            query_vector,
            k,
            _vector_filters(_owner_hash(phone)),
        )
        chunks = []
        for document in documents:
            data = document.to_dict()
            score = _score_document(document, data)
            if score < min_score:
                continue
            chunks.append(
                {
                    "text": data.get("text_content", ""),
                    "score": score,
                    "source": data.get("source_title", ""),
                    "source_url": data.get("source_url", ""),
                    "category": data.get("category", ""),
                }
            )
        return {"results": chunks, "query": mask_pii(query), "owner_hash": _owner_hash(phone)}
    except Exception as exc:
        logger.error("Private vector search failed: %s", exc)
        return {"results": [], "error": str(exc)}


async def search_knowledge(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    db = _get_firestore()
    if db is None:
        return []
    query_vector = await embed_query(query)
    if query_vector is None:
        return []
    try:
        documents = await _find_nearest(
            db,
            SHARED_COLLECTION,
            query_vector,
            limit,
            _vector_filters(),
        )
        results: List[Dict[str, Any]] = []
        for document in documents:
            data = document.to_dict()
            results.append(
                {
                    "doc_id": document.id,
                    "titulo": data.get("titulo", ""),
                    "conteudo": data.get("conteudo", "")[:500],
                    "categoria": data.get("categoria", ""),
                    "fonte": data.get("fonte", ""),
                    "similarity": round(_score_document(document, data), 3),
                }
            )
        return results
    except Exception as exc:
        logger.error("Shared vector search failed: %s", exc)
        return []


async def index_shared_document(
    titulo: str,
    conteudo: str,
    categoria: str = "geral",
    fonte: str = "",
) -> str:
    """Index a public document into ``public-knowledge-v2`` (Firestore Vector)."""
    db = _get_firestore()
    if db is None:
        raise RuntimeError("Firestore not configured")
    clean_title = mask_pii(titulo).strip()
    clean_content = mask_pii(conteudo).strip()
    plain_batch = db.batch()
    plain_id = hashlib.sha256(
        f"{categoria}:{clean_title}:{clean_content}".encode("utf-8")
    ).hexdigest()[:32]
    plain_batch.set(
        db.collection(SHARED_COLLECTION + "-plain").document(plain_id),
        {
            "titulo": clean_title,
            "conteudo": clean_content,
            "categoria": categoria,
            "fonte": fonte,
            "schema_version": SCHEMA_VERSION,
            "created_at": _now_brt().isoformat(),
        },
    )
    await asyncio.to_thread(plain_batch.commit)

    embedding = await embed_query(f"{clean_title}\n{clean_content[:2000]}")
    if embedding is None:
        logger.warning(
            "Public document plain-only (embedding unavailable) titulo=%s",
            clean_title,
        )
        return plain_id

    from google.cloud.firestore_v1.vector import Vector

    vector_id = hashlib.sha256(
        f"{categoria}:{clean_title}:{clean_content}:v".encode("utf-8")
    ).hexdigest()[:32]
    data = {
        "titulo": clean_title,
        "conteudo": clean_content,
        "categoria": categoria,
        "fonte": fonte,
        "vector_embedding": Vector(embedding),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "schema_version": SCHEMA_VERSION,
        "created_at": _now_brt().isoformat(),
    }
    try:
        await asyncio.to_thread(
            db.collection(SHARED_COLLECTION).document(vector_id).set, data
        )
        return vector_id
    except Exception as exc:
        logger.warning("Vector shared doc failed (plain kept) error=%s", exc)
        return plain_id


# ----------------------------------------------------------------------
# Compatibility shim for legacy callers
# ----------------------------------------------------------------------


MEMORY_COLLECTION = LEGACY_MEMORY_COLLECTION  # noqa: F401


__all__ = [
    "BRT",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_BASE_URL",
    "SCHEMA_VERSION",
    "MESSAGE_HISTORY_COLLECTION",
    "PRIVATE_COLLECTION",
    "SHARED_COLLECTION",
    "COLLECTIVE_COLLECTION",
    "MEMORY_COLLECTION",
    "embed_query",
    "embed_documents",
    "index_conversation_message",
    "search_conversation_memory",
    "list_message_history",
    "index_private_document",
    "search_legal_knowledge",
    "search_knowledge",
    "index_shared_document",
]  # noqa: F401

# Reference retained for tooling that imports the symbol.
_legacy_default_shim: Dict[str, Any] = {"vector_dim": EMBEDDING_DIM}
