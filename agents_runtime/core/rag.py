"""RAG core - MiniMax embeddings + Firestore Vector search."""
import os
import asyncio
import hashlib
import logging
from typing import Optional, Dict, Any, List

from core.secrets import get_secret

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "embo-01")
EMBEDDING_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "1536"))
COLLECTION_PREFIX = os.getenv("RAG_COLLECTION_PREFIX", "agente-knowledge-")


def _embed_direct(text: str) -> Optional[List[float]]:
    """Embed text directly via MiniMax API (bypass LangChain)."""
    import requests
    api_key = get_secret("MINIMAX_API_KEY") or os.getenv("MINIMAX_API_KEY", "")
    group_id = get_secret("MINIMAX_GROUP_ID") or os.getenv("MINIMAX_GROUP_ID", "")
    if not api_key or not group_id:
        logger.error("MINIMAX_API_KEY or MINIMAX_GROUP_ID not configured")
        return None
    try:
        resp = requests.post(
            "https://api.minimax.io/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "GroupId": group_id.strip(),
            },
            json={"model": "embo-01", "texts": [text], "encoding_format": "float"},
            timeout=30,
        )
        data = resp.json()
        if data.get("base_resp", {}).get("status_code", 0) != 0:
            logger.error(f"MiniMax embedding error: {data.get('base_resp')}")
            return None
        return data.get("data", [{}])[0].get("embedding")
    except Exception as e:
        logger.error(f"MiniMax embed direct failed: {e}")
        return None


def _get_firestore():
    """Get Firestore client."""
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as e:
        logger.warning(f"Firestore unavailable: {e}")
        return None


def _collection_name(phone: str) -> str:
    """Build collection name for a phone."""
    phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "")
    return f"{COLLECTION_PREFIX}{phone_clean}"


async def embed_query(text: str) -> Optional[List[float]]:
    """Embed a query string using MiniMax (direct API call)."""
    try:
        loop = asyncio.get_running_loop()
        vec = await loop.run_in_executor(None, _embed_direct, text)
        return vec
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return None


async def embed_documents(texts: List[str]) -> Optional[List[List[float]]]:
    """Embed multiple documents using MiniMax (direct API)."""
    results = []
    for text in texts:
        vec = await embed_query(text)
        if vec is None:
            return None
        results.append(vec)
    return results


async def index_document(
    phone: str,
    text_content: str,
    source_title: str,
    source_url: Optional[str] = None,
    category: str = "legislacao",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Index a document into the RAG vector store.

    Args:
        phone: Phone of agent-master (used in collection name)
        text_content: Document text to embed
        source_title: Human-readable title
        source_url: Source URL (optional)
        category: Category (legislacao, site_info, youtube_transcript)
        metadata: Additional metadata

    Returns:
        {"doc_id": str, "phone": str, "chunks": int}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    chunks = _chunk_text(text_content)
    if not chunks:
        return {"error": "empty_content"}

    vectors = await embed_documents(chunks)
    if vectors is None or len(vectors) != len(chunks):
        return {"error": "embedding_failed"}

    from google.cloud.firestore_v1.vector import Vector

    collection = _collection_name(phone)
    doc_ids = []

    batch = db.batch()
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        doc_id = hashlib.sha256(f"{source_title}_{i}_{chunk[:50]}".encode()).hexdigest()[:32]
        ref = db.collection(collection).document(doc_id)
        doc_data = {
            "text_content": chunk,
            "vector_embedding": Vector(vec),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
            "source_title": source_title,
            "source_url": source_url,
            "category": category,
            "chunk_index": i,
            "language": "pt",
            "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        if metadata:
            doc_data.update(metadata)
        batch.set(ref, doc_data)
        doc_ids.append(doc_id)
    batch.commit()

    return {
        "doc_ids": doc_ids,
        "phone": phone,
        "chunks": len(chunks),
        "source_title": source_title,
    }


async def search_legal_knowledge(
    phone: str,
    query: str,
    k: int = 5,
    min_score: float = 0.5,
) -> Dict[str, Any]:
    """Search RAG for relevant legal documents.

    Args:
        phone: Phone of agent-master
        query: User query
        k: Number of results to return
        min_score: Minimum similarity score (0-1)

    Returns:
        {"results": [{"text": ..., "score": ..., "source": ...}], "query": str}
    """
    db = _get_firestore()
    if db is None:
        return {"results": [], "error": "firestore_unavailable"}

    query_vec = await embed_query(query)
    if query_vec is None:
        return {"results": [], "error": "embedding_failed"}

    try:
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

        collection = _collection_name(phone)
        results = db.collection(collection).find_neighbors(
            vector_field="vector_embedding",
            query_vector=db.vector(query_vec),
            distance_measure=DistanceMeasure.COSINE,
            limit=k,
        ).get()

        chunks = []
        for doc in results:
            score = 1.0 - (doc.distance / 2.0)
            if score < min_score:
                continue
            data = doc.to_dict()
            chunks.append({
                "text": data.get("text_content", ""),
                "score": score,
                "source": data.get("source_title", ""),
                "source_url": data.get("source_url", ""),
                "category": data.get("category", ""),
            })

        return {"results": chunks, "query": query, "phone": phone}
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"results": [], "error": str(e)}


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 180) -> List[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", "? ", "! "]:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start + max_chars // 2:
                    end = last_sep + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [c for c in chunks if c]


SHARED_COLLECTION = "public-Knowledge-Shared"


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def search_knowledge(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Semantic search in the shared knowledge base (public data)."""
    try:
        embedding = await embed_query(query)
        if not embedding:
            return []
        db = _get_firestore()
        if db is None:
            return []
        results = []
        docs = db.collection(SHARED_COLLECTION).limit(limit * 3).stream()
        for doc in docs:
            data = doc.to_dict()
            stored_embedding = data.get("embedding", [])
            if stored_embedding:
                sim = _cosine_similarity(embedding, stored_embedding)
                if sim > 0.5:
                    results.append({
                        "doc_id": doc.id,
                        "titulo": data.get("titulo", ""),
                        "conteudo": data.get("conteudo", "")[:500],
                        "categoria": data.get("categoria", ""),
                        "fonte": data.get("fonte", ""),
                        "similarity": round(sim, 3),
                    })
        results.sort(key=lambda r: r["similarity"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return []


async def index_document(titulo: str, conteudo: str, categoria: str = "geral", fonte: str = "") -> str:
    """Index a document in the shared knowledge base with embedding."""
    db = _get_firestore()
    if db is None:
        raise RuntimeError("Firestore not configured")
    import uuid
    doc_id = f"{categoria}-{uuid.uuid4().hex[:8]}"
    embedding = await embed_query(f"{titulo}\n{conteudo[:2000]}")
    data = {
        "titulo": titulo,
        "conteudo": conteudo,
        "categoria": categoria,
        "fonte": fonte,
        "embedding": embedding or [],
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    db.collection(SHARED_COLLECTION).document(doc_id).set(data)
    logger.info(f"Document indexed: {doc_id} ({titulo})")
    return doc_id