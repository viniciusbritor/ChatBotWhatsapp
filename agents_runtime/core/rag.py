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
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from core.masker import mask_pii
from core.secrets import get_secret
from core.text_cleaner import clean_portuguese
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

# Minimum similarity score for retrieval (Phase F4d.6). Default 0.7
# (precisao ajustavel); tunable via env.
RAG_RETRIEVE_MIN_SCORE = float(
    os.getenv("RAG_RETRIEVE_MIN_SCORE", "0.6")
)

# Plain Firestore collections.
MESSAGE_HISTORY_COLLECTION = os.getenv(
    "RAG_MESSAGE_HISTORY_COLLECTION", "message-history"
)
MESSAGE_HISTORY_RETENTION_DAYS = int(
    os.getenv("RAG_MESSAGE_HISTORY_RETENTION_DAYS", "365")
)

ADAPTIVE_FLOOR = float(os.getenv("RAG_ADAPTIVE_FLOOR", "0.3"))

# Firestore Vector — knowledge-database (documentos, nao chat turns).
# scope="private" + owner_hash | scope="group" + group_hash
KNOWLEDGE_DATABASE = os.getenv("RAG_KNOWLEDGE_DATABASE", "knowledge-database")
PRIVATE_COLLECTION = KNOWLEDGE_DATABASE
SHARED_COLLECTION = None
COLLECTIVE_COLLECTION = None
LEGACY_MEMORY_COLLECTION = os.getenv(
    "RAG_MEMORY_COLLECTION", "conversation-memory-v2"
)
SECTIONS_COLLECTION = None
SECTION_MAX_CHARS = 0
SECTION_MIN_CHARS = 0

EMBEDDING_CONCURRENCY = int(os.getenv("RAG_EMBEDDING_CONCURRENCY", "4"))
EMBED_DOCUMENTS_TIMEOUT_SEC = float(os.getenv("EMBED_DOCUMENTS_TIMEOUT_SEC", "60"))


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


EMBEDDING_MAX_RETRIES = 3
EMBEDDING_BACKOFF_SEC = [1, 2, 4]


async def embed_query(text: str, attempt: int = 0) -> Optional[List[float]]:
    """Embed a chunk of text via OpenAI. Used only by ingestion pipelines.

    PHASE 3: retry com exponential backoff em RateLimitError.
    - 1 retry: 1s
    - 2 retries: 2s
    - 3 retries: 4s
    - Exausted: log error + return None
    """
    clean_text = clean_portuguese(mask_pii(str(text or "")).strip())
    if not clean_text:
        return None
    try:
        return await asyncio.to_thread(embed_best, clean_text)
    except Exception as exc:
        try:
            import openai
            if isinstance(exc, openai.RateLimitError):
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    wait = EMBEDDING_BACKOFF_SEC[attempt]
                    logger.info(
                        "embedding_rate_limit_retry attempt=%d wait=%d text_len=%d",
                        attempt + 1, wait, len(text),
                    )
                    await asyncio.sleep(wait)
                    return await embed_query(text, attempt + 1)
                logger.error(
                    "embedding_rate_limit_exhausted retries=%d text_len=%d",
                    EMBEDDING_MAX_RETRIES, len(text),
                )
                return None
            if isinstance(exc, openai.AuthenticationError):
                key_prefix = (os.getenv("OPENAI_API_KEY", "") or "")[:7] + "***"
                logger.error(
                    "embedding_auth_failed api_key_prefix=%s", key_prefix,
                )
                return None
            if isinstance(exc, openai.APITimeoutError):
                if attempt < EMBEDDING_MAX_RETRIES - 1:
                    wait = EMBEDDING_BACKOFF_SEC[attempt]
                    logger.info(
                        "embedding_timeout_retry attempt=%d wait=%d text_len=%d",
                        attempt + 1, wait, len(text),
                    )
                    await asyncio.sleep(wait)
                    return await embed_query(text, attempt + 1)
                logger.warning("embedding_timeout_exhausted text_len=%d", len(text))
                return None
        except ImportError:
            pass
        logger.warning(
            "embedding_other_error type=%s text_len=%d msg=%s",
            type(exc).__name__, len(text), str(exc)[:100],
        )
        return None


async def embed_documents(texts: List[str]) -> Optional[List[List[float]]]:
    semaphore = asyncio.Semaphore(max(1, EMBEDDING_CONCURRENCY))

    async def embed_one(text: str) -> Optional[List[float]]:
        async with semaphore:
            return await embed_query(text)

    try:
        vectors = await asyncio.wait_for(
            asyncio.gather(*(embed_one(text) for text in texts)),
            timeout=EMBED_DOCUMENTS_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "embed_documents_timeout timeout_sec=%s chunks=%d",
            EMBED_DOCUMENTS_TIMEOUT_SEC, len(texts),
        )
        return None
    none_count = sum(1 for v in vectors if v is None)
    if none_count > 0:
        logger.warning(
            "embed_documents_partial_failure chunks=%d failures=%d",
            len(texts), none_count,
        )
    if none_count == len(texts):
        return None
    return vectors


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 300) -> List[str]:
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
            else:
                last_space = text.rfind(" ", start, end)
                if last_space > start + max_chars // 2:
                    end = last_space + 1
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [chunk for chunk in chunks if chunk]


_HEADING_PATTERNS = re.compile(
    r"^("
    r"(?:LEI|DECRETO|MEDIDA\s+PROVIS[ÓO]RIA)\s+(?:COMPLEMENTAR\s+)?(?:N[º°]|n[º°])\s*[\d\.\,]+\b[^\n]*"
    r"|"
    r"(?:T[ÍI]TULO|T[ií]tulo)\s+[IVXLCDM\d]+\b[^\n]*"
    r"|"
    r"(?:CAP[ÍI]TULO|Cap[ií]tulo)\s+[IVXLCDM\d]+[^\n]*"
    r"|"
    r"(?:SE[ÇC][ÃA]O|Se[çc][ãa]o)\s+[IVXLCDM\d]+[^\n]*"
    r"|"
    r"(?:PARTE|Parte|ANEXO|Anexo)\s+[IVXLCDM\d]+[^\n]*"
    r"|"
    r"Art\.?\s*[\d]+[º°]?\b[^\n]*"
    r"|"
    r"§\s*[\d]+[º°]?\b[^\n]*"
    r"|"
    r"Par[áa]grafo\s+(?:[úu]nico|[\d]+)\b[^\n]*"
    r"|"
    r"^[IVXLCDM]+\s*[–\-]\s*[^\n]*"
    r"|"
    r"^\d+(?:\.\d+)*[\s\.\-\u2013\u2014]+\s*[A-Z\u00C0-\u00DC][A-Z\u00C0-\u00DC\s]{3,}"
    r"|"
    r"^[A-Z\u00C0-\u00DC][A-Z\u00C0-\u00DC\s\-]{10,}$"
    r"|"
    r"^(?:ABSTRACT|RESUMO|INTRODU[ÇC][ÃA]O|CONCLUS[ÃA]O|REFER[ÊE]NCIAS?|BIBLIOGRAFIA|AP[ÊE]NDICE|AGRADECIMENTOS)"
    r"\s*$"
    r")",
    re.MULTILINE,
)


def _extract_legal_hierarchy(section_title: str) -> Dict[str, str]:
    hierarchy: Dict[str, str] = {}
    t = section_title.strip()

    m = re.match(r"(LEI|DECRETO|MEDIDA\s+PROVIS[ÓO]RIA).*(?:N[º°]?|n[º°]?)\s*([\d\.\,]+)", t, re.IGNORECASE)
    if m:
        hierarchy["level"] = "lei"
        hierarchy["number"] = m.group(2)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"(T[ÍI]TULO|T[ií]tulo)\s+([IVXLCDM\d]+)", t)
    if m:
        hierarchy["level"] = "titulo"
        hierarchy["number"] = m.group(2)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"(CAP[ÍI]TULO|Cap[ií]tulo)\s+([IVXLCDM\d]+)", t)
    if m:
        hierarchy["level"] = "capitulo"
        hierarchy["number"] = m.group(2)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"(SE[ÇC][ÃA]O|Se[çc][ãa]o)\s+([IVXLCDM\d]+)", t)
    if m:
        hierarchy["level"] = "secao"
        hierarchy["number"] = m.group(2)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"Art\.?\s*([\d]+)[º°]?", t)
    if m:
        hierarchy["level"] = "artigo"
        hierarchy["number"] = m.group(1)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"(§)\s*([\d]+)[º°]?", t)
    if m:
        hierarchy["level"] = "paragrafo"
        hierarchy["number"] = m.group(2)
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"Par[áa]grafo\s+(?:[úu]nico|([\d]+))", t, re.IGNORECASE)
    if m:
        hierarchy["level"] = "paragrafo"
        hierarchy["number"] = m.group(1) or "unico"
        hierarchy["title"] = t
        return hierarchy

    m = re.match(r"([IVXLCDM]+)\s*[–\-]", t)
    if m:
        hierarchy["level"] = "inciso"
        hierarchy["number"] = m.group(1)
        hierarchy["title"] = t
        return hierarchy

    return {"level": "texto", "number": "", "title": section_title}


_FRONT_MATTER_RE = re.compile(
    r"senado federal|mesa diretora|bi[êe]nio|coordena[çc][ãa]o de edi[çc][õo]es|"
    r"secretaria de editora[çc][ãa]o|ficha catalogr[áa]fica|sum[áa]rio|"
    r"presidente|vice-presidente",
    re.IGNORECASE,
)


def _extract_document_title(section_titles: List[str], source_title: str, full_text: str = "") -> str:
    for sec in section_titles:
        sec = (sec or "").strip()
        if not sec:
            continue
        if re.match(r"(C[ÓO]DIGO\s+(?:DE\s+)?(?:PROTE[ÇC][ÃA]O\s+E\s+)?DEFESA|LEI\s+N[º°]|DECRETO\s+N[º°])", sec, re.IGNORECASE):
            return re.sub(r"\s+", " ", sec)[:120]

    base = source_title.rsplit(".", 1)[0]
    base = base.replace("_", " ").replace("-", " ").strip()
    base = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:120] if base else source_title[:120]


def _detect_sections(text: str) -> List[tuple[str, str]]:
    matches = list(_HEADING_PATTERNS.finditer(text))
    if not matches:
        return [("", text)]

    sections: List[tuple[str, str]] = []
    prev_title = ""
    prev_start = 0

    for m in matches:
        if prev_start == 0 and m.start() == 0:
            prev_title = m.group(0).strip()
            prev_start = m.end()
            continue
        if prev_start > 0:
            sections.append((prev_title, text[prev_start:m.start()].strip()))
        prev_title = m.group(0).strip()
        prev_start = m.end()

    if prev_start > 0:
        sections.append((prev_title, text[prev_start:].strip()))

    if not sections:
        sections.append(("", text))

    return [(title, body) for title, body in sections if body and len(body) >= 50]


def _chunk_text_semantic(
    text: str,
    max_chars: int = 2000,
    min_chars: int = 50,
    overlap_chars: int = 100,
) -> List[tuple[str, str, str]]:
    if not text or not text.strip():
        return []

    sections = _detect_sections(text)
    all_chunks: List[tuple[str, str, str]] = []

    for section_idx, (section_title, section_body) in enumerate(sections):
        paragraphs = re.split(r"\n\s*\n", section_body)
        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text or len(para_text) < 50:
                continue

            if len(para_text) <= max_chars:
                chunk_title = section_title or ""
                all_chunks.append((chunk_title, "paragraph", para_text))
                continue

            sentences = re.split(r"(?<=[.!?])\s+", para_text)
            current = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current) + len(sent) + 1 <= max_chars:
                    current = (current + " " + sent).strip()
                else:
                    if len(current) >= min_chars:
                        all_chunks.append((section_title or "", "sentence_group", current))
                        words = current.split()
                        overlap_words = min(len(words), overlap_chars // 5)
                        current = " ".join(words[-overlap_words:]) if overlap_words else ""
                        current = (current + " " + sent).strip() if current else sent
                    else:
                        current = (current + " " + sent).strip()

            if current and len(current) >= min_chars:
                all_chunks.append((section_title or "", "sentence_group", current))

    if not all_chunks:
        legacy = _chunk_text(text, max_chars=1200, overlap=300)
        return [("", "paragraph", c) for c in legacy]

    return all_chunks


def _build_sections(
    text: str,
    max_chars: int = 8000,
    min_chars: int = 1500,
) -> List[tuple[str, str]]:
    """Gera secoes (capitulos) completas de ate max_chars chars.

    Agrupa paragrafos consecutivos da MESMA secao detectada em unidades
    coerentes. Cada secao e a unidade atomica para embedding e retrieval.
    """
    if not text or not text.strip():
        return []

    sections = _detect_sections(text)
    result: List[tuple[str, str]] = []

    for section_title, section_body in sections:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section_body) if p.strip()]
        if not paragraphs:
            continue

        current_parts: List[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > max_chars and current_parts:
                result.append((section_title, "\n\n".join(current_parts)))
                current_parts = []
                current_len = 0
            current_parts.append(para)
            current_len += len(para) + 2

        if current_parts:
            joined = "\n\n".join(current_parts)
            if len(joined) >= min_chars or not result:
                result.append((section_title, joined))

    if not result:
        result.append(("", text[:max_chars]))

    return [(title, body) for title, body in result if body and len(body) >= min(min_chars, 300)]


def _vector_filters(
    owner_hash: Optional[str] = None,
    extra: Optional[List[Tuple[str, str, Any]]] = None,
) -> List[Tuple[str, str, Any]]:
    filters: List[Tuple[str, str, Any]] = [
        ("embedding_model", "==", EMBEDDING_MODEL),
        ("embedding_dim", "==", EMBEDDING_DIM),
        ("schema_version", "==", SCHEMA_VERSION),
    ]
    if owner_hash:
        filters.insert(0, ("owner_hash", "==", owner_hash))
    if extra:
        filters.extend(extra)
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


async def get_conversation_history(phone: str, limit: int = 10) -> str:
    if not phone or not str(phone).strip():
        return ""
    db = _get_firestore()
    if db is None:
        return ""
    owner_hash = _owner_hash(phone)
    try:

        def fetch():
            query_obj = (
                db.collection(MESSAGE_HISTORY_COLLECTION)
                .where("owner_hash", "==", owner_hash)
                .order_by("created_at", direction="DESCENDING")
                .limit(limit)
            )
            return list(query_obj.stream())

        docs = await asyncio.to_thread(fetch)
    except Exception:
        return ""
    msgs = []
    for d in reversed(list(docs)):
        data = d.to_dict() or {}
        direction = data.get("direction", "in")
        text = (data.get("text_masked") or "")[:80]
        prefix = "Usuario" if direction == "in" else "Jennifer"
        msgs.append(f"{prefix}: {text}")
    return "\n".join(msgs)


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
    class_: Optional[str] = None,
    group: Optional[str] = None,
    theme: Optional[str] = None,
) -> Dict[str, Any]:
    """Index a private document (book/edital) into ``agent-knowledge-v2``.

    Soft limits mirror the group pipeline (F4d.5). When the input exceeds
    the configured thresholds, the document is still indexed end-to-end
    and the returned payload reports ``truncated=True`` plus the reason.
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}
    text_content = clean_portuguese(text_content)
    clean_content = mask_pii(text_content)
    chars_soft_limit = PRIVATE_CHARS_SOFT_LIMIT
    chunks_soft_limit = PRIVATE_CHUNKS_SOFT_LIMIT
    raw_chunks = _chunk_text_semantic(clean_content)
    if not raw_chunks:
        return {"error": "empty_content"}

    chunks = [t[2] for t in raw_chunks]
    section_titles = [t[0] for t in raw_chunks]
    chunk_types = [t[1] for t in raw_chunks]

    truncated = False
    truncated_reason: Optional[str] = None
    if len(text_content) > chars_soft_limit:
        truncated = True
        truncated_reason = "chars_above_soft_limit"
    if len(chunks) > chunks_soft_limit:
        truncated = True
        if truncated_reason is None:
            truncated_reason = "chunks_above_soft_limit"

    vector_batch = db.batch()
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
    class_value = (class_ or safe_metadata.get("class") or "").strip() or None
    group_value = (group or safe_metadata.get("group") or "").strip() or None
    theme_value = (theme or safe_metadata.get("theme") or "").strip() or None

    _doc_title = _extract_document_title(section_titles, source_title, text_content)

    for index, chunk in enumerate(chunks):
        document_id = hashlib.sha256(
            f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
        ).hexdigest()[:32]
        common = {
            **safe_metadata,
            "scope": "private",
            "owner_hash": owner_hash,
            "document_title": _doc_title,
            "text_content": chunk,
            "source_title": mask_pii(source_title),
            "source_url": source_url,
            "category": category,
            "class": class_value,
            "group": group_value,
            "theme": theme_value,
            "chunk_index": index,
            "chunk_type": chunk_types[index],
            "section_title": section_titles[index],
            "language": "pt-BR",
            "created_at": now,
            "schema_version": SCHEMA_VERSION,
        }

    vectors = await embed_documents(chunks)
    partial = False

    if vectors is not None and len(vectors) == len(chunks):
        from google.cloud.firestore_v1.vector import Vector

        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            document_id = hashlib.sha256(
                f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
            ).hexdigest()[:32]
            data = {
                **safe_metadata,
                "scope": "private",
                "owner_hash": owner_hash,
                "text_content": chunk,
                "source_title": mask_pii(source_title),
                "source_url": source_url,
                "category": category,
                "class": class_value,
                "group": group_value,
                "theme": theme_value,
                "chunk_index": index,
                "chunk_type": chunk_types[index],
                "section_title": section_titles[index],
                "hierarchy": _extract_legal_hierarchy(section_titles[index]),
                "language": "pt-BR",
                "created_at": now,
                "schema_version": SCHEMA_VERSION,
                "vector_embedding": Vector(vector),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dim": EMBEDDING_DIM,
            }
            vector_batch.set(db.collection(KNOWLEDGE_DATABASE).document(document_id), data)
            vector_ids.append(document_id)
        try:
            await asyncio.to_thread(vector_batch.commit)
        except Exception as exc:
            logger.warning("Vector commit failed error=%s", exc)
            vector_ids = []
    elif vectors is not None and len(vectors) > 0:
        # PHASE 4: partial success. Indexa o que deu certo.
        partial = True
        logger.info(
            "index_private_document_partial chunks=%d vectors=%d",
            len(chunks), len(vectors),
        )
        from google.cloud.firestore_v1.vector import Vector

        valid_pairs = [
            (i, v) for i, v in enumerate(vectors) if v is not None
        ]
        for index, vector in valid_pairs:
            chunk = chunks[index]
            document_id = hashlib.sha256(
                f"{owner_hash}:{source_title}:{index}:{chunk[:100]}".encode("utf-8")
            ).hexdigest()[:32]
            data = {
                **safe_metadata,
                "scope": "private",
                "owner_hash": owner_hash,
                "document_title": _doc_title,
                "text_content": chunk,
                "source_title": mask_pii(source_title),
                "source_url": source_url,
                "category": category,
                "class": class_value,
                "group": group_value,
                "theme": theme_value,
                "chunk_index": index,
                "chunk_type": chunk_types[index],
                "section_title": section_titles[index],
                "hierarchy": _extract_legal_hierarchy(section_titles[index]),
                "language": "pt-BR",
                "created_at": now,
                "schema_version": SCHEMA_VERSION,
                "vector_embedding": Vector(vector),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dim": EMBEDDING_DIM,
            }
            vector_batch.set(db.collection(KNOWLEDGE_DATABASE).document(document_id), data)
            vector_ids.append(document_id)
        try:
            await asyncio.to_thread(vector_batch.commit)
        except Exception as exc:
            logger.warning("Vector partial commit failed error=%s", exc)
            vector_ids = []
    elif vectors is None or len(vectors) == 0:
        vector_count = 0 if vectors is None else len(vectors)
        logger.warning(
            "index_private_document_vector_skipped chunks=%d vectors=%d",
            len(chunks), vector_count,
        )
        if len(chunks) > 0:
            if vectors is None:
                return {"error": "embedding_failed", "chunks": len(chunks)}
            return {
                "error": "all_embeddings_failed",
                "chunks": len(chunks),
            }

    return {
        "doc_ids": vector_ids,
        "scope": "private",
        "owner_hash": owner_hash,
        "chunks": len(chunks),
        "chunks_indexed": len(vector_ids),
        "chars": len(text_content),
        "truncated": truncated,
        "class": class_value,
        "group": group_value,
        "theme": theme_value,
        "truncated_reason": truncated_reason,
        "source_title": mask_pii(source_title),
        "collection": KNOWLEDGE_DATABASE,
    }


async def index_document(
    scope: str,
    hash_val: str,
    text_content: str,
    source_title: str,
    source_url: Optional[str] = None,
    category: str = "legislacao",
    metadata: Optional[Dict[str, Any]] = None,
    class_: Optional[str] = None,
    group_: Optional[str] = None,
    theme: Optional[str] = None,
) -> Dict[str, Any]:
    if scope not in ("private", "group"):
        return {"error": f"invalid_scope: {scope}"}
    if scope == "private":
        return await index_private_document(
            phone="", text_content=text_content, source_title=source_title,
            source_url=source_url, category=category, metadata=metadata,
            class_=class_, group=group_, theme=theme,
        )


async def index_private_sections(
    phone: str,
    text_content: str,
    source_title: str,
    metadata: Optional[Dict[str, Any]] = None,
    class_: Optional[str] = None,
    group: Optional[str] = None,
    theme: Optional[str] = None,
) -> Dict[str, Any]:
    """Indexa secoes/capitulos em ``agent-knowledge-sections``.

    Cada secao e uma unidade atomica (ate SECTION_MAX_CHARS) com
    embedding proprio. Complementa o chunk-based, nao o substitui.
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    from core.text_cleaner import clean_portuguese
    from core.masker import mask_pii

    clean = clean_portuguese(text_content or "")
    masked = mask_pii(clean)
    sections = _build_sections(masked, max_chars=SECTION_MAX_CHARS, min_chars=SECTION_MIN_CHARS)
    if not sections:
        return {"status": "no_sections", "count": 0}

    owner_hash = _owner_hash(phone)
    now = _now_brt().isoformat()
    protected = {"owner_hash", "text_content", "vector_embedding", "embedding_model", "embedding_dim", "schema_version"}
    safe_metadata = {k: v for k, v in (metadata or {}).items() if k not in protected}
    class_value = (class_ or safe_metadata.get("class") or "").strip() or None
    group_value = (group or safe_metadata.get("group") or "").strip() or None
    theme_value = (theme or safe_metadata.get("theme") or "").strip() or None

    section_texts = [body for _, body in sections]
    vectors = await embed_documents(section_texts)
    if vectors is None or len(vectors) != len(section_texts):
        return {"status": "embedding_failed", "count": 0}

    from google.cloud.firestore_v1.vector import Vector

    batch = db.batch()
    ids = []
    for idx, ((section_title, body), vector) in enumerate(zip(sections, vectors)):
        section_id = hashlib.sha256(
            f"{owner_hash}:{source_title}:section:{idx}".encode("utf-8")
        ).hexdigest()[:32]
        data = {
            **safe_metadata,
            "owner_hash": owner_hash,
            "text_content": body,
            "source_title": mask_pii(source_title),
            "section_title": section_title or f"SECAO {idx + 1}",
            "section_index": idx,
            "total_sections": len(sections),
            "class": class_value,
            "group": group_value,
            "theme": theme_value,
            "language": "pt-BR",
            "created_at": now,
            "schema_version": SCHEMA_VERSION,
            "vector_embedding": Vector(vector),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
        }
        batch.set(db.collection(SECTIONS_COLLECTION).document(section_id), data)
        ids.append(section_id)

    try:
        await asyncio.to_thread(batch.commit)
    except Exception as exc:
        logger.warning("sections_commit_failed error=%s", exc)
        return {"status": "commit_failed", "count": 0}

    return {"status": "ok", "count": len(sections), "section_ids": ids, "collection": SECTIONS_COLLECTION}


async def search_legal_knowledge(
    phone: str,
    query: str,
    k: int = 5,
    min_score: float = 0.5,
    source_title: Optional[str] = None,
    class_: Optional[str] = None,
    group: Optional[str] = None,
    language: Optional[str] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    db = _get_firestore()
    if db is None:
        return {"results": [], "error": "firestore_unavailable"}
    query_vector = await embed_query(query)
    if query_vector is None:
        return {"results": [], "error": "embedding_failed"}
    extra_filters: List[Tuple[str, str, Any]] = [("scope", "==", "private")]
    if source_title:
        extra_filters.append(("source_title", "==", source_title))
    if class_:
        extra_filters.append(("class", "==", class_))
    if group:
        extra_filters.append(("group", "==", group))
    if language:
        extra_filters.append(("language", "==", language))
    if since:
        extra_filters.append(("created_at", ">=", since))
    try:
        documents = await _find_nearest(
            db,
            KNOWLEDGE_DATABASE,
            query_vector,
            k,
            _vector_filters(_owner_hash(phone), extra_filters or None),
        )
        chunks = []
        scores = []
        for document in documents:
            data = document.to_dict()
            score = _score_document(document, data)
            scores.append(score)
            if score < min_score or score < ADAPTIVE_FLOOR:
                continue
            chunks.append(
                {
                    "text": clean_portuguese(data.get("text_content", "")),
                    "score": score,
                    "source": data.get("source_title", ""),
                    "source_url": data.get("source_url", ""),
                    "category": data.get("category", ""),
                    "class": data.get("class", ""),
                    "group": data.get("group", ""),
                    "theme": data.get("theme", ""),
                    "language": data.get("language", ""),
                    "created_at": data.get("created_at", ""),
                    "chunk_type": data.get("chunk_type", ""),
                    "section_title": data.get("section_title", ""),
                }
            )
            if len(chunks) >= k:
                break
        top_score = scores[0] if scores else 0.0
        if chunks and chunks[0]["score"] < min_score:
            logger.info(
                "retrieval_low_confidence owner_hash=%s top_score=%.3f min_score=%.3f delivered=%d",
                _owner_hash(phone), top_score, min_score, len(chunks),
            )
        if not chunks and scores:
            top_preview = []
            for document, score in list(zip(documents, scores))[:3]:
                data = document.to_dict() or {}
                top_preview.append(
                    {
                        "score": round(score, 3),
                        "source": data.get("source_title", ""),
                        "snippet": (data.get("text_content", "") or "")[:100],
                    }
                )
            logger.info(
                "retrieval_zero_hits owner_hash=%s query_preview=%s top_preview=%s",
                _owner_hash(phone),
                mask_pii(query)[:120],
                top_preview,
            )
        return {
            "results": chunks,
            "query": mask_pii(query),
            "owner_hash": _owner_hash(phone),
            "min_score": min_score,
            "adaptive_floor": ADAPTIVE_FLOOR,
            "top_score": round(top_score, 3) if top_score else 0.0,
            "filters": {
                "source_title": source_title,
                "class": class_,
                "group": group,
                "language": language,
                "since": since,
            },
        }
    except Exception as exc:
        logger.error("Private vector search failed: %s", exc)
        return {"results": [], "error": str(exc)}


async def search_sections(
    phone: str,
    query: str,
    k: int = 3,
    min_score: float = 0.3,
    source_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Busca em ``agent-knowledge-sections`` (capitulos inteiros).

    Fallback silencioso: se a collection nao existe ou falha, devolve
    vazio para o caller cair no chunk-based.
    """
    db = _get_firestore()
    if db is None:
        return {"results": [], "error": "firestore_unavailable"}
    query_vector = await embed_query(query)
    if query_vector is None:
        return {"results": [], "error": "embedding_failed"}

    extra_filters: List[Tuple[str, str, Any]] = []
    if source_title:
        extra_filters.append(("source_title", "==", source_title))

    try:
        documents = await _find_nearest(
            db,
            SECTIONS_COLLECTION,
            query_vector,
            k,
            _vector_filters(_owner_hash(phone), extra_filters or None),
        )
        chunks = []
        scores = []
        for document in documents:
            data = document.to_dict() or {}
            score = _score_document(document, data)
            scores.append(score)
            if score < min_score:
                continue
            chunks.append(
                {
                    "text": clean_portuguese(data.get("text_content", "")),
                    "score": score,
                    "source": data.get("source_title", ""),
                    "section_title": data.get("section_title", ""),
                    "section_index": data.get("section_index", 0),
                    "total_sections": data.get("total_sections", 0),
                    "class": data.get("class", ""),
                    "group": data.get("group", ""),
                    "theme": data.get("theme", ""),
                }
            )
        return {
            "results": chunks,
            "query": mask_pii(query),
            "owner_hash": _owner_hash(phone),
            "min_score": min_score,
            "top_score": round(scores[0], 3) if scores else 0.0,
            "collection": SECTIONS_COLLECTION,
        }
    except Exception as exc:
        logger.warning("sections_search_failed error=%s — falling back to chunks", exc)
        return {"results": [], "error": str(exc), "fallback": True}


async def search_with_context(
    phone: str,
    query: str,
    k: int = 5,
    expand: int = 2,
    min_score: float = 0.5,
    source_title: Optional[str] = None,
) -> Dict[str, Any]:
    base = await search_legal_knowledge(
        phone=phone, query=query, k=k,
        min_score=min_score, source_title=source_title,
    )
    results = base.get("results", []) if isinstance(base, dict) else []
    if not results:
        return base

    db = _get_firestore()
    if db is None:
        return base

    owner_hash = _owner_hash(phone)
    enriched = []
    for r in results:
        ctx_before = ""
        ctx_after = ""
        src = r.get("source", "")
        idx = r.get("chunk_index", 0) if isinstance(r, dict) else 0

        if src and isinstance(idx, int):
            try:
                for delta in range(expand, 0, -1):
                    def fetch_before():
                        return list(
                            db.collection(KNOWLEDGE_DATABASE)
                            .where("scope", "==", "private")
                            .where("owner_hash", "==", owner_hash)
                            .where("source_title", "==", src)
                            .where("chunk_index", "==", idx - delta)
                            .limit(1)
                            .stream()
                        )
                    before = await asyncio.to_thread(fetch_before)
                    if before:
                        d = before[0].to_dict() or {}
                        ctx_before = d.get("text_content", "")[:500] + "\n" + ctx_before
            except Exception:
                pass

            try:
                for delta in range(1, expand + 1):
                    def fetch_after():
                        return list(
                            db.collection(KNOWLEDGE_DATABASE)
                            .where("scope", "==", "private")
                            .where("owner_hash", "==", owner_hash)
                            .where("source_title", "==", src)
                            .where("chunk_index", "==", idx + delta)
                            .limit(1)
                            .stream()
                        )
                    after = await asyncio.to_thread(fetch_after)
                    if after:
                        d = after[0].to_dict() or {}
                        ctx_after += d.get("text_content", "")[:500] + "\n"
            except Exception:
                pass

        enriched.append({**r, "context_before": ctx_before.strip(), "context_after": ctx_after.strip()})

    return {**base, "results": enriched, "mode": "context_expanded", "expand": expand}


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
