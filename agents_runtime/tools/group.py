"""Group tools - membership and welcome message management."""
import hashlib
import logging
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Ola pessoal! Sou a Jennifer, assistente do Vinicius na OmniChannel. "
    "Quando precisarem de algo (reunioes, atas, documentos), e so me chamar com @Jennifer. "
    "Estou aqui pra ajudar!"
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as e:
        logger.warning(f"Firestore unavailable: {e}")
        return None


def _is_user_member(db, group_jid: str, phone: str) -> bool:
    """Returns True when ``phone`` is an active member of ``group_jid``."""
    if not phone or not group_jid:
        return False
    try:
        doc = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .document(phone)
            .get()
        )
        if doc.exists:
            return bool(doc.to_dict().get("is_active", False))
    except Exception:
        return False
    return False


async def register_group(
    group_jid: str,
    name: str,
    members: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a new group that Jennifer joined.

    Args:
        group_jid: WhatsApp group JID (e.g., "120363...@g.us")
        name: Group display name
        members: Initial list of member phone numbers

    Returns:
        {"group_jid": str, "members_count": int}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        ref = db.collection("grupos").document(group_jid.replace("/", "_"))
        ref.set({
            "group_jid": group_jid,
            "name": name,
            "joined_at": _now_iso(),
            "members_count": len(members or []),
            "proactive_mode": "normal",
            "welcome_sent": False,
            "is_active": True,
        }, merge=True)

        if members:
            batch = db.batch()
            for phone in members:
                m_ref = db.collection("grupos").document(group_jid.replace("/", "_")).collection("membros").document(phone)
                batch.set(m_ref, {
                    "phone": phone,
                    "joined_group_at": _now_iso(),
                    "is_active": True,
                }, merge=True)
            batch.commit()

        return {
            "group_jid": group_jid,
            "members_count": len(members or []),
        }
    except Exception as e:
        logger.error(f"register_group error: {e}")
        return {"error": str(e)}


async def update_members(group_jid: str, members: List[str]) -> Dict[str, Any]:
    """Update group members list."""
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        doc_ref = db.collection("grupos").document(group_jid.replace("/", "_"))
        doc_ref.update({
            "members_count": len(members),
            "last_member_sync": _now_iso(),
        })

        existing = doc_ref.collection("membros").stream()
        existing_phones = {doc.id for doc in existing}

        current_phones = set(members)
        to_add = current_phones - existing_phones
        to_remove = existing_phones - current_phones

        batch = db.batch()
        for phone in to_add:
            ref = doc_ref.collection("membros").document(phone)
            batch.set(ref, {
                "phone": phone,
                "joined_group_at": _now_iso(),
                "is_active": True,
            })
        for phone in to_remove:
            ref = doc_ref.collection("membros").document(phone)
            batch.update(ref, {"is_active": False, "left_at": _now_iso()})
        batch.commit()

        return {
            "group_jid": group_jid,
            "added": len(to_add),
            "removed": len(to_remove),
        }
    except Exception as e:
        logger.error(f"update_members error: {e}")
        return {"error": str(e)}


async def get_group_members(group_jid: str) -> List[str]:
    """Get active members of a group."""
    db = _get_firestore()
    if db is None:
        return []

    try:
        docs = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .where("is_active", "==", True)
            .stream()
        )
        return [doc.id for doc in docs]
    except Exception as e:
        logger.error(f"get_group_members error: {e}")
        return []


async def mark_welcome_sent(group_jid: str) -> bool:
    """Mark welcome message as sent."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        db.collection("grupos").document(group_jid.replace("/", "_")).update({
            "welcome_sent": True,
            "welcome_sent_at": _now_iso(),
        })
        return True
    except Exception as e:
        logger.error(f"mark_welcome_sent error: {e}")
        return False


async def is_welcome_sent(group_jid: str) -> bool:
    """Check if welcome message was already sent."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if doc.exists:
            return doc.to_dict().get("welcome_sent", False)
        return False
    except Exception:
        return False


def get_welcome_message() -> str:
    """Get the welcome message template."""
    return WELCOME_MESSAGE


async def is_jennifer_in_group(group_jid: str) -> bool:
    """Check if Jennifer is registered in this group."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if doc.exists:
            return doc.to_dict().get("is_active", False)
        return False
    except Exception:
        return False


async def list_active_groups() -> List[Dict[str, Any]]:
    """List all active groups Jennifer is in."""
    db = _get_firestore()
    if db is None:
        return []
    try:
        docs = db.collection("grupos").where("is_active", "==", True).stream()
        return [{"group_jid": doc.id, **doc.to_dict()} for doc in docs]
    except Exception:
        return []


async def get_member_confirmation(group_jid: str, phone: str) -> bool:
    """Check if a member has confirmed data sharing in this group."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .document(phone)
            .get()
        )
        if doc.exists:
            return bool(doc.to_dict().get("confirmed", False))
        return False
    except Exception:
        return False


async def set_member_confirmation(group_jid: str, phone: str, confirmed: bool = True) -> bool:
    """Set member data sharing confirmation in a group."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc_ref = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .document(phone)
        )
        doc_ref.set({
            "phone": phone,
            "confirmed": confirmed,
            "confirmed_at": _now_iso(),
        }, merge=True)
        return True
    except Exception as e:
        logger.error(f"set_member_confirmation error: {e}")
        return False


async def set_group_drive_folder(group_jid: str, folder_id: str, folder_name: str = "") -> bool:
    """Set the Drive folder ID associated with this group."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        db.collection("grupos").document(group_jid.replace("/", "_")).update({
            "drive_folder_id": folder_id,
            "drive_folder_name": folder_name or "Drive do Grupo",
        })
        return True
    except Exception as e:
        logger.error(f"set_group_drive_folder error: {e}")
        return False


async def get_group_drive_folder(group_jid: str) -> Optional[str]:
    """Get the Drive folder ID for this group."""
    db = _get_firestore()
    if db is None:
        return None
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if doc.exists:
            return doc.to_dict().get("drive_folder_id")
        return None
    except Exception:
        return None


async def get_group_info(group_jid: str) -> Dict[str, Any]:
    """Get group info including drive folder, members, settings."""
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if not doc.exists:
            return {"error": "group_not_found"}
        group_data = doc.to_dict()
        members = await get_group_members(group_jid)
        confirmed_count = 0
        for m in members:
            member_doc = (
                db.collection("grupos")
                .document(group_jid.replace("/", "_"))
                .collection("membros")
                .document(m)
                .get()
            )
            if member_doc.exists and member_doc.to_dict().get("confirmed"):
                confirmed_count += 1
        return {
            **group_data,
            "members": members,
            "members_count": len(members),
            "confirmed_count": confirmed_count,
        }
    except Exception as e:
        logger.error(f"get_group_info error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Group RAG (F4): index/search knowledge per group with OpenAI embeddings
# ---------------------------------------------------------------------------

_GROUP_KNOWLEDGE_COLLECTION = "knowledge-database"
_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536
_CHUNK_MAX_CHARS = 1200
_CHUNK_OVERLAP_PCT = 25
_CHUNKS_SOFT_LIMIT_DEFAULT = 500
_CHARS_SOFT_LIMIT_DEFAULT = 1_000_000
_THEME_HEURISTICS = [
    (r"ata|reuniao|minutes", "ata_reuniao"),
    (r"contrato|legal|procuracao", "contrato"),
    (r"planilha|custo|expense|xlsx|csv", "dados_financeiros"),
    (r"apresentacao|pptx|slides", "apresentacao"),
    (r"manual|tutorial|docs|guia", "documentacao"),
]


def _get_chunks_soft_limit() -> int:
    try:
        return int(os.getenv("RAG_GROUP_CHUNKS_SOFT_LIMIT", str(_CHUNKS_SOFT_LIMIT_DEFAULT)))
    except ValueError:
        return _CHUNKS_SOFT_LIMIT_DEFAULT


def _get_chars_soft_limit() -> int:
    try:
        return int(os.getenv("RAG_GROUP_CHARS_SOFT_LIMIT", str(_CHARS_SOFT_LIMIT_DEFAULT)))
    except ValueError:
        return _CHARS_SOFT_LIMIT_DEFAULT


def _group_hash(group_jid: str) -> str:
    return hashlib.sha256(group_jid.encode("utf-8")).hexdigest()[:32]


def _chunk_text_smart(text: str, max_chars: int = _CHUNK_MAX_CHARS,
                       overlap_pct: int = _CHUNK_OVERLAP_PCT) -> List[str]:
    chunks: List[str] = []
    overlap = int(max_chars * overlap_pct / 100)
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", "? ", "! "]:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start + max_chars // 2:
                    end = last_sep + len(sep)
                    break
            else:
                last_space = text.rfind(" ", start, end)
                if last_space > start + max_chars // 2:
                    end = last_space + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else end
    return chunks


def _embed_text(text: str, api_key: str = "",
                 max_retries: int = 3) -> Optional[List[float]]:
    if not text or not text.strip():
        return None
    key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        logger.warning("group_rag: OPENAI_API_KEY not set for embedding")
        return None
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.openai.com/v1/embeddings",
                json={"model": _EMBEDDING_MODEL, "input": text},
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            return list(data["data"][0]["embedding"])
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import time as _t
                _t.sleep(1 * (2 ** attempt))
    logger.warning("group_rag embed failed after retries: %s", last_error)
    return None


def _classify_theme(source_name: str, text: str) -> str:
    fn = (source_name or "").lower()
    for pat, theme in _THEME_HEURISTICS:
        if re.search(pat, fn):
            return theme
    try:
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        base_url = os.getenv("DEEPSEEK_BASE_URL",
                              "https://api.deepseek.com/v1").strip()
        if not api_key:
            return "outros"
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=15,
            timeout=5,
            extra_body={"cache_mode": "default"},
        )
        sample = (text or "")[:500]
        resp = llm.invoke(
            f"Responda apenas com 1-3 palavras em snake_case (ex: ata_reuniao, "
            f"contrato, dados_financeiros, documentacao). Nome: {source_name}. "
            f"Trecho: {sample}"
        )
        raw = (resp.content if hasattr(resp, "content") else str(resp)).strip().lower()
        cleaned = re.sub(r"[^a-z0-9_]", "", raw.replace(" ", "_"))[:30]
        return cleaned or "outros"
    except Exception:
        return "outros"


async def _detect_duplicate(db, gh: str, source_name: str) -> Optional[str]:
    try:
        docs = (
            db.collection(_GROUP_KNOWLEDGE_COLLECTION)
            .where("group_hash", "==", gh)
            .where("source_name", "==", source_name)
            .limit(1)
            .stream()
        )
        for d in docs:
            return d.id
    except Exception:
        return None
    return None


async def index_group_document(
    phone: str,
    group_jid: str,
    text: str,
    visibility: str,
    source_name: str = "",
    force_overwrite: bool = False,
) -> Dict[str, Any]:
    if not text or not group_jid:
        return {"error": "text_and_group_jid_required"}
    if visibility not in ("group", "public"):
        return {"error": "visibility_must_be_group_or_public"}

    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    if not _is_user_member(db, group_jid, phone):
        return {
            "error": "not_group_member",
            "message": "somente membros ativos do grupo podem indexar conhecimento do grupo",
        }

    chars_soft_limit = _get_chars_soft_limit()
    chunks_soft_limit = _get_chunks_soft_limit()

    gh = _group_hash(group_jid)

    existing_id = await _detect_duplicate(db, gh, source_name)
    if existing_id and not force_overwrite:
        return {"needs_overwrite": True,
                "existing_doc_id": existing_id,
                "source_name": source_name}

    if existing_id and force_overwrite:
        try:
            old_docs = (
                db.collection(_GROUP_KNOWLEDGE_COLLECTION)
                .where("group_hash", "==", gh)
                .where("source_name", "==", source_name)
                .stream()
            )
            for d in old_docs:
                d.reference.delete()
        except Exception as e:
            logger.warning("overwrite delete failed: %s", e)

    chunks = _chunk_text_smart(text)
    if not chunks:
        return {"error": "no_content_to_index"}

    truncated = False
    truncated_reason = None
    truncated_chunks = 0
    if len(text) > chars_soft_limit:
        truncated = True
        truncated_reason = "chars_above_soft_limit"
        truncated_chunks = len(chunks)
        logger.warning(
            "index_group_document_chars_soft_limit chars=%d limit=%d",
            len(text),
            chars_soft_limit,
        )
    if len(chunks) > chunks_soft_limit:
        truncated = True
        if truncated_reason is None:
            truncated_reason = "chunks_above_soft_limit"
        truncated_chunks = len(chunks)
        logger.warning(
            "index_group_document_chunks_soft_limit chunks=%d limit=%d",
            len(chunks),
            chunks_soft_limit,
        )

    theme = _classify_theme(source_name, text)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    indexed = 0
    failed = 0
    step = _CHUNK_MAX_CHARS - int(_CHUNK_MAX_CHARS * _CHUNK_OVERLAP_PCT / 100)

    try:
        from google.cloud.firestore_v1.vector import Vector
    except Exception:
        class Vector:  # pragma: no cover - fallback para ambientes sem Firestore Vector
            def __init__(self, values):
                self.values = values
    for i, chunk in enumerate(chunks):
        embedding = _embed_text(chunk, api_key)
        if embedding is None:
            failed += 1
            continue
        doc_id = hashlib.sha256(
            f"group:{gh}:{source_name}:{i}:{chunk[:40]}".encode("utf-8")
        ).hexdigest()[:32]
        doc = {
            "scope": "group",
            "text": chunk,
            "source_name": source_name,
            "theme": theme,
            "visibility": visibility,
            "group_hash": gh if visibility == "group" else "",
            "group_jid": group_jid if visibility == "group" else "",
            "indexed_by": phone,
            "chunk_index": i,
            "chunk_total": len(chunks),
            "chunk_overlap": int(_CHUNK_MAX_CHARS * _CHUNK_OVERLAP_PCT / 100),
            "char_start": i * step,
            "char_end": i * step + len(chunk),
            "created_at": _now_iso(),
            "vector_embedding": Vector(embedding),
        }
        try:
            db.collection(_GROUP_KNOWLEDGE_COLLECTION).document(doc_id).set(doc)
            indexed += 1
        except Exception as e:
            logger.warning("index_group_document chunk %d error: %s", i, e)
            failed += 1

    return {
        "indexed": indexed,
        "failed": failed,
        "chunks": len(chunks),
        "total_chunks": len(chunks),
        "chars": len(text),
        "truncated": truncated,
        "truncated_reason": truncated_reason,
        "truncated_chunks": truncated_chunks,
        "chunk_overlap": int(_CHUNK_MAX_CHARS * _CHUNK_OVERLAP_PCT / 100),
        "theme": theme,
        "visibility": visibility,
        "collection": _GROUP_KNOWLEDGE_COLLECTION,
        "overwrote": bool(existing_id and force_overwrite),
    }


async def search_group_knowledge(
    group_jid: str,
    query: str,
    limit: int = 5,
    phone: str = "",
) -> Dict[str, Any]:
    if not query or not group_jid:
        return {"results": [], "count": 0}
    db = _get_firestore()
    if db is None:
        return {"results": [], "count": 0}
    if phone and not _is_user_member(db, group_jid, phone):
        return {"results": [], "count": 0, "error": "not_group_member"}
    query_embedding = _embed_text(query)
    if query_embedding is None:
        return {"results": [], "count": 0, "error": "embedding_failed"}
    gh = _group_hash(group_jid)
    from google.cloud.firestore import Vector
    vector_value = Vector(query_embedding)
    try:
        results = db.collection(_GROUP_KNOWLEDGE_COLLECTION).find_nearest(
            vector_field="vector_embedding",
            query_vector=vector_value,
            distance_measure="COSINE",
            limit=limit * 3,
            return_document_distance=True,
        ).get()
    except Exception:
        return {"results": [], "count": 0}
    filtered = []
    for doc in results:
        data = doc.to_dict()
        vis = data.get("visibility", "")
        doc_gh = data.get("group_hash", "")
        if vis == "public" or (vis == "group" and doc_gh == gh):
            dist = getattr(doc, "_distance", 1.0)
            filtered.append({
                "text": data.get("text", ""),
                "source_name": data.get("source_name", ""),
                "theme": data.get("theme", ""),
                "score": round(max(0, 1.0 - dist), 3),
            })
        if len(filtered) >= limit:
            break
    return {
        "results": sorted(filtered, key=lambda r: r["score"], reverse=True),
        "count": len(filtered),
    }
