import asyncio
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from core.masker import mask_pii
from core.secrets import get_secret

logger = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))
EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "1536"))
EMBEDDING_BASE_URL = os.getenv(
    "RAG_EMBEDDING_BASE_URL",
    "https://api.openai.com/v1/embeddings",
)
SCHEMA_VERSION = int(os.getenv("RAG_SCHEMA_VERSION", "2"))
MEMORY_COLLECTION = os.getenv("RAG_MEMORY_COLLECTION", "conversation-memory-v2")
PRIVATE_COLLECTION = os.getenv("RAG_PRIVATE_COLLECTION", "agent-knowledge-v2")
SHARED_COLLECTION = os.getenv("RAG_SHARED_COLLECTION", "public-knowledge-v2")
RETENTION_DAYS = int(os.getenv("RAG_RETENTION_DAYS", "90"))
EMBEDDING_CONCURRENCY = int(os.getenv("RAG_EMBEDDING_CONCURRENCY", "4"))


def _now_brt() -> datetime:
    return datetime.now(BRT)


def _owner_hash(phone: str) -> str:
    normalized = "".join(char for char in str(phone) if char.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _validate_embedding(embedding: Optional[Sequence[float]]) -> Optional[List[float]]:
    if embedding is None:
        return None
    vector = list(embedding)
    if len(vector) != EMBEDDING_DIM:
        logger.error(
            "Embedding rejected: model=%s expected_dim=%s actual_dim=%s",
            EMBEDDING_MODEL,
            EMBEDDING_DIM,
            len(vector),
        )
        return None
    return vector


def _embed_direct(text: str) -> Optional[List[float]]:
    api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")
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
        logger.error("OpenAI embedding returned empty data: %s", data)
        return None
    embedding = items[0].get("embedding")
    validated = _validate_embedding(embedding)
    if validated is not None:
        logger.info("OpenAI embedding generated: model=%s dim=%s", EMBEDDING_MODEL, len(validated))
    return validated


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


async def index_conversation_message(
    phone: str,
    text: str,
    direction: str,
    message_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    response_identity: str = "Jennifer",
) -> Dict[str, Any]:
    clean_text = mask_pii(str(text or "")).strip()
    if len(clean_text) < 3:
        return {"status": "skipped", "reason": "empty_text"}
    embedding = await embed_query(clean_text)
    if embedding is None:
        logger.warning("Conversation indexing skipped: embedding unavailable")
        return {"status": "skipped", "reason": "embedding_unavailable"}
    db = _get_firestore()
    if db is None:
        return {"status": "skipped", "reason": "firestore_unavailable"}
    owner_hash = _owner_hash(phone)
    stable_key = message_id or f"{time_ns()}:{direction}:{clean_text}"
    document_id = hashlib.sha256(f"{owner_hash}:{stable_key}".encode("utf-8")).hexdigest()[:32]
    now = _now_brt()
    from google.cloud.firestore_v1.vector import Vector

    data = {
        "owner_hash": owner_hash,
        "conversation_id": conversation_id or owner_hash,
        "message_id": message_id or document_id,
        "turn_id": turn_id or document_id,
        "direction": direction,
        "agent_id": agent_id or "jennifier",
        "response_identity": response_identity,
        "text_masked": clean_text[:2000],
        "vector_embedding": Vector(embedding),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "schema_version": SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=RETENTION_DAYS)).isoformat(),
    }
    await asyncio.to_thread(db.collection(MEMORY_COLLECTION).document(document_id).set, data)
    logger.info("Conversation memory indexed: doc_id=%s direction=%s", document_id, direction)
    return {"status": "indexed", "doc_id": document_id, "collection": MEMORY_COLLECTION}


def time_ns() -> int:
    import time

    return time.time_ns()


async def search_conversation_memory(phone: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    query_vector = await embed_query(query)
    if query_vector is None:
        return []
    db = _get_firestore()
    if db is None:
        return []
    try:
        documents = await _find_nearest(
            db,
            MEMORY_COLLECTION,
            query_vector,
            limit,
            _vector_filters(_owner_hash(phone)),
        )
        results = []
        for document in documents:
            data = document.to_dict()
            results.append(
                {
                    "text": data.get("text_masked", ""),
                    "direction": data.get("direction", "in"),
                    "agent_id": data.get("agent_id", "jennifier"),
                    "response_identity": data.get("response_identity", "Jennifer"),
                    "score": _score_document(document, data),
                }
            )
        return results
    except Exception as exc:
        logger.warning("Conversation memory search failed: %s", exc)
        return []


async def index_private_document(
    phone: str,
    text_content: str,
    source_title: str,
    source_url: Optional[str] = None,
    category: str = "legislacao",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}
    clean_content = mask_pii(text_content)
    chunks = _chunk_text(clean_content)
    if not chunks:
        return {"error": "empty_content"}
    vectors = await embed_documents(chunks)
    if vectors is None or len(vectors) != len(chunks):
        return {"error": "embedding_failed"}
    from google.cloud.firestore_v1.vector import Vector

    owner_hash = _owner_hash(phone)
    now = _now_brt().isoformat()
    batch = db.batch()
    document_ids = []
    protected_fields = {
        "owner_hash",
        "text_content",
        "vector_embedding",
        "embedding_model",
        "embedding_dim",
        "schema_version",
    }
    safe_metadata = {key: value for key, value in (metadata or {}).items() if key not in protected_fields}
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        document_id = hashlib.sha256(
            f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
        ).hexdigest()[:32]
        reference = db.collection(PRIVATE_COLLECTION).document(document_id)
        data = {
            **safe_metadata,
            "owner_hash": owner_hash,
            "text_content": chunk,
            "vector_embedding": Vector(vector),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
            "schema_version": SCHEMA_VERSION,
            "source_title": mask_pii(source_title),
            "source_url": source_url,
            "category": category,
            "chunk_index": index,
            "language": "pt-BR",
            "created_at": now,
        }
        batch.set(reference, data)
        document_ids.append(document_id)
    await asyncio.to_thread(batch.commit)
    return {
        "doc_ids": document_ids,
        "owner_hash": owner_hash,
        "chunks": len(chunks),
        "source_title": mask_pii(source_title),
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
        results = []
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
    db = _get_firestore()
    if db is None:
        raise RuntimeError("Firestore not configured")
    clean_title = mask_pii(titulo).strip()
    clean_content = mask_pii(conteudo).strip()
    embedding = await embed_query(f"{clean_title}\n{clean_content[:2000]}")
    if embedding is None:
        raise ValueError("embedding_failed")
    from google.cloud.firestore_v1.vector import Vector

    document_id = hashlib.sha256(
        f"{categoria}:{clean_title}:{clean_content}".encode("utf-8")
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
    await asyncio.to_thread(db.collection(SHARED_COLLECTION).document(document_id).set, data)
    logger.info("Shared document indexed: doc_id=%s", document_id)
    return document_id
