"""Knowledge retriever (Fase H).

Decides *whether* a user message refers to knowledge previously stored in
Firestore Vector, picks the correct scope (private vs group), and returns
matching chunks. When the message is in a group and the relevant document
is private, creates a ``pending_action`` of type
``share_private_knowledge_in_group`` so the user can explicitly approve
sharing before the content is exposed.

Architecture:

- **Heuristic** (`_looks_like_rag_query`): detects obvious RAG keywords.
- **LLM tie-breaker** (DeepSeek V4 Flash): decides only when the
  heuristic is inconclusive and the message has enough context.
- **Scope decision** (`_decide_scope`): private vs group based on JID.
- **Cross-scope prompt** (`_maybe_request_share`): creates the
  ``pending_action`` payload when needed.

Retrieval reuses ``core.rag.search_legal_knowledge`` (private) and
``tools.group.search_group_knowledge`` (group). Threshold comes from
``RAG_RETRIEVE_MIN_SCORE`` (default 0.5).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

from core.rag import RAG_RETRIEVE_MIN_SCORE, search_legal_knowledge
from tools.group import search_group_knowledge

logger = logging.getLogger(__name__)


RAG_KEYWORDS = {
    "memorizei", "memorizado", "memorizada", "memorizou", "memorizaram",
    "indexado", "indexada", "indexados", "no rag", "no vector",
    "base de conhecimento", "knowledge base", "conhecimento",
    "salvou", "salvamos", "gravamos", "guardamos", "armazenamos",
    "ata que", "documento que", "pdf que", "planilha que",
    "docx que", "arquivo que",
}

QUESTION_KEYWORDS = {
    "?", "qual", "quais", "como", "quando", "onde", "por que", "porque",
    "o que", "me diga", "me conte", "resuma", "explique",
    "tem alguma coisa sobre", "existe algum documento",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _looks_like_rag_query(text: str) -> bool:
    """Heuristic: explicit RAG keyword present, or a question form.

    Returns True when the message clearly refers to previously stored
    knowledge. Returns False when the message is a command, greeting, or
    unrelated question.
    """
    normalized = _normalize(text)
    if not normalized:
        return False
    if any(kw in normalized for kw in RAG_KEYWORDS):
        return True
    if any(kw in normalized for kw in QUESTION_KEYWORDS):
        return True
    return False


async def _llm_is_rag_query(text: str) -> Optional[bool]:
    """Tie-breaker using DeepSeek V4 Flash. Returns True/False/None."""
    if not text.strip():
        return None
    try:
        from langchain_openai import ChatOpenAI

        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or os.getenv("NVIDIA_API_KEY", "").strip()
            or ""
        )
        if not api_key:
            return None
        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        ).strip()
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=4,
            timeout=8,
        )
        prompt = (
            "O usuario esta pedindo algo que foi previamente salvo/armazenado "
            "no Firestore Vector (base de conhecimento da Jennifer)?\n"
            "Responda apenas 'sim' ou 'nao'.\n"
            f"Mensagem: {text.strip()[:400]}\nResposta:"
        )
        result = await asyncio.to_thread(llm.invoke, prompt)
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        cleaned = _normalize(raw).strip(" .!?\":'").lower()
        if cleaned.startswith("sim"):
            return True
        if cleaned.startswith("nao") or cleaned.startswith("não"):
            return False
        return None
    except Exception as exc:
        logger.warning("llm_is_rag_query failed: %s", exc)
        return None


async def is_rag_query(text: str) -> bool:
    """Returns True when the message refers to previously stored knowledge."""
    if _looks_like_rag_query(text):
        return True
    llm_answer = await _llm_is_rag_query(text)
    return bool(llm_answer)


def _is_group(envelope: Dict[str, Any]) -> bool:
    extra = envelope.get("extra", {}) or {}
    return "@g.us" in str(extra.get("remote_jid", ""))


def _is_user_member(db, group_jid: str, phone: str) -> bool:
    """Returns True when ``phone`` is an active member of ``group_jid``."""
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


def _extract_group_jid(envelope: Dict[str, Any]) -> str:
    extra = envelope.get("extra", {}) or {}
    remote_jid = str(extra.get("remote_jid", ""))
    if "@g.us" in remote_jid:
        return remote_jid.split("@")[0] + "@g.us"
    return ""


def _extract_phone(envelope: Dict[str, Any]) -> str:
    return str(envelope.get("phone", "") or "")


async def _retrieve_private(
    phone: str,
    query: str,
    limit: int,
    min_score: float,
) -> Dict[str, Any]:
    result = await search_legal_knowledge(
        phone=phone, query=query, k=limit, min_score=min_score
    )
    chunks = result.get("results", []) if isinstance(result, dict) else []
    return {
        "scope": "private",
        "results": chunks,
        "count": len(chunks),
        "min_score": min_score,
        "owner_hash": result.get("owner_hash") if isinstance(result, dict) else None,
    }


async def _retrieve_group(
    group_jid: str,
    query: str,
    limit: int,
    min_score: float,
) -> Dict[str, Any]:
    result = await search_group_knowledge(
        group_jid=group_jid, query=query, limit=limit
    )
    raw_results = result.get("results", []) if isinstance(result, dict) else []
    filtered = [
        item for item in raw_results
        if float(item.get("score", 0.0)) >= min_score
    ]
    return {
        "scope": "group",
        "results": filtered,
        "count": len(filtered),
        "min_score": min_score,
        "group_jid": group_jid,
    }


async def _maybe_request_share(
    phone: str,
    group_jid: str,
    query: str,
) -> Optional[Dict[str, Any]]:
    """Create the cross-scope pending_action.

    Returns the pending action dict if created, else None.
    """
    if not phone or not group_jid:
        return None
    try:
        from core.pending_actions import (
            PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
            set_pending_action,
        )
        return await set_pending_action(
            phone,
            PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
            {
                "phone": phone,
                "group_jid": group_jid,
                "query": query,
                "source": "knowledge_retriever",
            },
            ttl_sec=300,
        )
    except Exception as exc:
        logger.warning("share_private_knowledge pending_action failed: %s", exc)
        return None


async def retrieve(
    envelope: Dict[str, Any],
    query: str,
    *,
    limit: int = 5,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Decide scope and retrieve. Returns a structured dict.

    Shape::

        {
          "scope": "private" | "group" | "none",
          "decision": "private" | "group" | "group_private_share_pending" | "denied" | "no_results",
          "results": [...],
          "count": int,
          "needs_share_prompt": bool,
          "share_pending_action": dict | None,
          "reason": str | None,
        }
    """
    threshold = float(min_score) if min_score is not None else RAG_RETRIEVE_MIN_SCORE
    is_group = _is_group(envelope)
    phone = _extract_phone(envelope)
    group_jid = _extract_group_jid(envelope) if is_group else ""

    if is_group:
        from core.rag import _get_firestore as _get_db  # type: ignore

        db = _get_db()
        if db is None or not _is_user_member(db, group_jid, phone):
            return {
                "scope": "group",
                "decision": "denied",
                "results": [],
                "count": 0,
                "needs_share_prompt": False,
                "share_pending_action": None,
                "reason": "not_member" if db is not None else "firestore_unavailable",
            }
        group_hits = await _retrieve_group(
            group_jid=group_jid, query=query, limit=limit, min_score=threshold
        )
        if group_hits["count"] > 0:
            return {
                **group_hits,
                "decision": "group",
                "needs_share_prompt": False,
                "share_pending_action": None,
            }
        private_hits = await _retrieve_private(
            phone=phone, query=query, limit=limit, min_score=threshold
        )
        if private_hits["count"] > 0:
            pending = await _maybe_request_share(phone, group_jid, query)
            return {
                **private_hits,
                "decision": "group_private_share_pending",
                "needs_share_prompt": True,
                "share_pending_action": pending,
            }
        return {
            "scope": "none",
            "decision": "no_results",
            "results": [],
            "count": 0,
            "needs_share_prompt": False,
            "share_pending_action": None,
            "reason": "no_matches",
        }

    private_hits = await _retrieve_private(
        phone=phone, query=query, limit=limit, min_score=threshold
    )
    decision = "private" if private_hits["count"] > 0 else "no_results"
    return {
        **private_hits,
        "decision": decision,
        "needs_share_prompt": False,
        "share_pending_action": None,
    }


async def share_pending_action_consume(
    phone: str,
) -> Optional[Dict[str, Any]]:
    """Read and consume a pending share_private_knowledge_in_group action."""
    from core.pending_actions import (
        PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
        consume_pending_action,
    )

    return await consume_pending_action(phone, PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE)


__all__ = [
    "is_rag_query",
    "retrieve",
    "share_pending_action_consume",
    "RAG_RETRIEVE_MIN_SCORE",
]
