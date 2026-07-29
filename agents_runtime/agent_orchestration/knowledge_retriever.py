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
import unicodedata
import hashlib
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from core.rag import RAG_RETRIEVE_MIN_SCORE, search_legal_knowledge
from tools.group import search_group_knowledge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory retrieval cache (Fase I subfase 2)
# ---------------------------------------------------------------------------
# Lives in the Cloud Run process memory. Max 256 entries; LRU-evicted
# on overflow. TTL 5 min (configurable via RAG_CACHE_TTL_SEC).
# Survives only as long as the container instance is warm.

_RETRIEVAL_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SEC = int(os.getenv("RAG_CACHE_TTL_SEC", "300"))


def _cache_key(
    envelope: Dict[str, Any],
    query: str,
    limit: int,
    min_score: float,
) -> str:
    phone = _extract_phone(envelope) if envelope else ""
    return hashlib.md5(
        f"{phone}|{_normalize(query)}|{limit}|{min_score}".encode("utf-8")
    ).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _RETRIEVAL_CACHE.get(key)
    if not entry:
        return None
    if (time.time() - entry["ts"]) > _CACHE_TTL_SEC:
        _RETRIEVAL_CACHE.pop(key, None)
        return None
    return entry["result"]


def _cache_set(key: str, result: Dict[str, Any]) -> None:
    _RETRIEVAL_CACHE[key] = {"ts": time.time(), "result": result}
    if len(_RETRIEVAL_CACHE) > 256:
        oldest = min(_RETRIEVAL_CACHE.items(), key=lambda kv: kv[1]["ts"])
        _RETRIEVAL_CACHE.pop(oldest[0], None)


def _normalize(text: str) -> str:
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents).strip()


RAG_KEYWORDS_RAW = {
    "memorizei", "memorizado", "memorizada", "memorizou", "memorizaram",
    "indexado", "indexada", "indexados", "no rag", "no vector",
    "base de conhecimento", "knowledge base", "conhecimento",
    "salvou", "salvamos", "gravamos", "guardamos", "armazenamos",
    "ata que", "documento que", "pdf que", "planilha que",
    "docx que", "arquivo que",
    "esse documento", "este documento", "desse documento",
    "deste documento", "o documento", "o arquivo",
    "esse pdf", "esse docx", "essa planilha", "dessa planilha",
    "desse pdf", "desse arquivo", "deste arquivo",
    "sobre o que é", "sobre o que", "do que se trata",
    "qual o tema", "qual é o tema", "de que trata",
    "quem é o autor", "qual o autor", "qual é o autor",
    "quem escreveu", "de quem é", "conteudo do",
    "conteudo da", "conteudo desse", "conteudo deste",
}

RAG_KEYWORDS = frozenset(_normalize(kw) for kw in RAG_KEYWORDS_RAW)

QUESTION_KEYWORDS = {
    "tem alguma coisa sobre",
    "existe algum documento",
}


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


_DOC_HINT = re.compile(
    r"[\w\u00C0-\u017F][\w\-\.\(\)\u00C0-\u017F ]*\.(?:pdf|docx|xlsx|txt|md|csv)",
    re.IGNORECASE,
)


_FILENAME_STOPWORDS = frozenset({
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "pra", "por", "pelo", "pela", "com", "sem",
    "que", "qual", "quais", "quem", "quando", "onde", "como",
    "sobre", "apos", "depois", "antes", "entre",
    "arquivo", "arquivos", "documento", "documentos", "doc", "docs",
    "pdf", "planilha", "planilhas", "relatorio", "relatorios",
    "este", "esta", "esse", "essa", "isto", "isso", "aquilo",
    "tem", "tenho", "tinha", "tens",
    "fala", "fale", "falei", "falam", "me", "te", "se",
    "do", "da", "e", "ou", "mas", "pois",
    "chamado", "chamada", "nome", "titulo", "conteudo",
    "informacao", "informacoes", "dados", "lista",
    "todos", "todas", "todo", "toda", "algum", "alguma",
    "alguns", "algumas", "qualquer", "quaisquer",
})


def _extract_source_title_hint(query: str) -> Optional[str]:
    """Extract the longest filename-like token from the query.

    The regex accepts internal spaces and Latin-1 accented letters so
    that filenames like 'dissertação vinicius.pdf' are captured in full.

    After the regex match, leading stopwords/prepositions are trimmed
    so that phrases like 'me fale sobre dissertação vinicius.pdf' yield
    'dissertação vinicius.pdf' instead of the whole prefix.
    """
    raw = (query or "").strip()
    if not raw:
        return None
    match = _DOC_HINT.search(raw)
    if not match:
        return None
    candidate = match.group(0).strip(".,;:!?()\"' \t\n\r\u00A0")
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate:
        return None

    words = candidate.split(" ")
    while len(words) > 1 and _normalize(words[0]) in _FILENAME_STOPWORDS:
        words.pop(0)
    candidate = " ".join(words)
    return candidate or None


CLASS_HINTS = {
    "legal": ["lei", "cdc", "codigo de defesa", "legislacao", "regulamento"],
    "edital": ["edital", "licitacao", "pregao", "concurso"],
    "jurisprudencia": ["jurisprudencia", "acordao", "sumula", "decisao judicial"],
    "manual": ["manual", "procedimento", "pop", "sop", "runbook"],
    "empresa": ["empresa", "processo interno", "politica interna"],
    "corporativo": ["segmento", "indústria", "setor"],
    "academico": ["livro", "artigo", "paper", "tese", "dissertacao", "probabilidade"],
    "saude": ["saude", "medicina", "bula", "protocolo clinico"],
    "financeiro": ["financeiro", "balanço", "relatorio", "orcamento"],
    "outros": [],
}


def _extract_class_hint(query: str) -> Optional[str]:
    text = _normalize(query)
    scores: Dict[str, int] = {}
    for cls, keywords in CLASS_HINTS.items():
        for kw in keywords:
            if kw in text:
                scores[cls] = scores.get(cls, 0) + 1
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def _extract_query_hints(query: str) -> Dict[str, str]:
    hints: Dict[str, str] = {}
    source_title = _extract_source_title_hint(query)
    if source_title:
        hints["source_title"] = source_title
    cls = _extract_class_hint(query)
    if cls:
        hints["class"] = cls
    return hints


async def _retrieve_private(
    phone: str,
    query: str,
    limit: int,
    min_score: float,
    source_title: Optional[str] = None,
    class_: Optional[str] = None,
    group: Optional[str] = None,
    language: Optional[str] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    result = await search_legal_knowledge(
        phone=phone,
        query=query,
        k=limit,
        min_score=min_score,
        source_title=source_title,
        class_=class_,
        group=group,
        language=language,
        since=since,
    )
    chunks = result.get("results", []) if isinstance(result, dict) else []
    return {
        "scope": "private",
        "results": chunks,
        "count": len(chunks),
        "min_score": min_score,
        "owner_hash": result.get("owner_hash") if isinstance(result, dict) else None,
        "filters": result.get("filters") if isinstance(result, dict) else None,
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


async def _rerank_with_llm(
    query: str,
    chunks: List[Dict[str, Any]],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """Re-rank retrieved chunks using DeepSeek V4 Flash.

    Takes the top-k (k=10) chunks and re-orders them by relevance to
    the query using a small LLM. Returns the top_n (3) most relevant.
    The LLM does not generate text; it only returns a JSON array of
    indices, e.g., [3, 0, 7, 1, 9].
    """
    if len(chunks) <= top_n:
        return chunks
    if not os.getenv("DEEPSEEK_API_KEY"):
        return chunks
    try:
        from langchain_openai import ChatOpenAI

        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        )
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=base_url,
            temperature=0,
            max_tokens=200,
            timeout=10,
        )
        chunk_lines = []
        for i, c in enumerate(chunks):
            text = (c.get("text") or "")[:500]
            chunk_lines.append(f"[{i}] (score={c.get('score', 0):.2f}) {text}")
        chunks_blob = "\n".join(chunk_lines)
        prompt = (
            "Re-ordene os chunks abaixo por relevancia para a query. "
            "Retorne SOMENTE um JSON array de indices, do mais "
            f"relevante para o menos relevante, max {top_n} itens.\n"
            f"Query: {query}\n\n"
            f"Chunks:\n{chunks_blob}\n\n"
            f"Resposta (JSON array de {top_n} indices):"
        )
        result = await asyncio.to_thread(
            llm.invoke,
            [{"role": "user", "content": prompt}],
        )
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        import json as _json
        match = re.search(r"\[[\d,\s]+\]", raw)
        if not match:
            return chunks[:top_n]
        indices = _json.loads(match.group(0))
        re_ranked = []
        for idx in indices:
            if 0 <= idx < len(chunks):
                re_ranked.append(chunks[idx])
        for c in chunks:
            if c not in re_ranked:
                re_ranked.append(c)
        return re_ranked[:top_n]
    except Exception as exc:
        logger.warning("LLM re-ranking failed: %s", exc)
        return chunks[:top_n]


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


async def _request_feedback(
    phone: str,
    query: str,
) -> Optional[Dict[str, Any]]:
    """Create the retrieval_feedback pending_action.

    Triggered when retrieve() returns needs_clarification=True. The
    bot can then ask the user to refine the query or provide more
    context. Returns the pending action dict if created, else None.
    """
    if not phone:
        return None
    try:
        from core.pending_actions import (
            PENDING_ACTION_RETRIEVAL_FEEDBACK,
            set_pending_action,
        )
        return await set_pending_action(
            phone,
            PENDING_ACTION_RETRIEVAL_FEEDBACK,
            {
                "phone": phone,
                "query": query,
                "source": "knowledge_retriever",
            },
            ttl_sec=180,
        )
    except Exception as exc:
        logger.warning("retrieval_feedback pending_action failed: %s", exc)
        return None


async def retrieve(
    envelope: Dict[str, Any],
    query: str,
    *,
    limit: Optional[int] = None,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Decide scope and retrieve. Returns a structured dict.

    Shape::

        {
          "scope": "private" | "group" | "none",
          "decision": "private" | "group" | "group_private_share_pending"
                     | "denied" | "no_results" | "needs_clarification",
          "results": [...],
          "count": int,
          "needs_share_prompt": bool,
          "needs_clarification": bool,
          "clarification_prompt": str | None,
          "share_pending_action": dict | None,
          "reason": str | None,
          "filters": {...},
        }
    """
    effective_limit = int(limit) if limit is not None else int(
        os.getenv("RAG_RETRIEVE_K", "10")
    )
    threshold = float(min_score) if min_score is not None else float(
        os.getenv("RAG_RETRIEVE_MIN_SCORE", str(RAG_RETRIEVE_MIN_SCORE))
    )
    cache_key = _cache_key(envelope, query, effective_limit, threshold)
    cached = _cache_get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["cache_hit"] = True
        return cached
    is_group = _is_group(envelope)
    phone = _extract_phone(envelope)
    group_jid = _extract_group_jid(envelope) if is_group else ""
    hints = _extract_query_hints(query)
    started = time.monotonic()
    query_hash = hashlib.md5(
        (phone + ":" + _normalize(query)).encode("utf-8")
    ).hexdigest()[:12]
    logger.info(
        "retriever_decision",
        extra={
            "event_name": "retriever_decision",
            "scope": "group" if is_group else "private",
            "query_preview": _normalize(query)[:120],
            "hints": hints,
            "k": effective_limit,
            "min_score": threshold,
        },
    )

    def _log_metrics(decision: str, results: List[Dict[str, Any]]) -> None:
        summary = _summarize_results(results)
        metrics = RetrievalMetrics(
            query_hash=query_hash,
            scope="group" if is_group else "private",
            decision=decision,
            min_score=threshold,
            candidates=len(results),
            returned=len(results),
            classes=summary["classes"],
            sources=summary["sources"],
            top_score=summary["top_score"],
            avg_score=summary["avg_score"],
            needs_clarification=decision == "needs_clarification",
            cache_hit=False,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        _emit_retrieval_metrics(metrics)

    try:
        if is_group:
            from core.rag import _get_firestore as _get_db  # type: ignore

            db = _get_db()
            if db is None or not _is_user_member(db, group_jid, phone):
                try:
                    from core.audit import log_action
                    log_action(
                        actor="agent-knowledge-retriever",
                        action="CROSS_SCOPE_ATTEMPT",
                        target=phone,
                        details={
                            "query_preview": _normalize(query)[:120],
                            "group_jid": group_jid,
                            "reason": "not_member_or_firestore_unavailable",
                        },
                    )
                except Exception:
                    pass
                result = {
                    "scope": "group",
                    "decision": "denied",
                    "results": [],
                    "count": 0,
                    "needs_share_prompt": False,
                    "needs_clarification": False,
                    "share_pending_action": None,
                    "reason": "not_member" if db is not None else "firestore_unavailable",
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            group_hits = await _retrieve_group(
                group_jid=group_jid, query=query, limit=effective_limit, min_score=threshold
            )
            if group_hits["count"] > 0:
                group_hits["results"] = await _rerank_with_llm(
                    query, group_hits["results"], top_n=3
                )
                group_hits["count"] = len(group_hits["results"])
                result = {
                    **group_hits,
                    "decision": "group",
                    "needs_share_prompt": False,
                    "needs_clarification": False,
                    "share_pending_action": None,
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            private_hits = await _retrieve_private(
                phone=phone, query=query, limit=effective_limit, min_score=threshold,
                source_title=hints.get("source_title"),
                class_=hints.get("class"),
            )
            if private_hits["count"] > 0:
                pending = await _maybe_request_share(phone, group_jid, query)
                result = {
                    **private_hits,
                    "decision": "group_private_share_pending",
                    "needs_share_prompt": True,
                    "needs_clarification": False,
                    "share_pending_action": pending,
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            result = {
                "scope": "none",
                "decision": "needs_clarification",
                "results": [],
                "count": 0,
                "needs_share_prompt": False,
                "needs_clarification": True,
                "clarification_prompt": (
                    "Não encontrei nada sobre isso no que memorizei. "
                    "Quer me dar mais detalhes ou outro termo?"
                ),
                "share_pending_action": None,
                "reason": "no_matches",
                "filters": hints,
            }
            _log_metrics(result["decision"], result["results"])
            _cache_set(cache_key, result)
            return result

        private_hits = await _retrieve_private(
            phone=phone, query=query, limit=effective_limit, min_score=threshold,
            source_title=hints.get("source_title"),
            class_=hints.get("class"),
        )
        if private_hits["count"] > 0:
            private_hits["results"] = await _rerank_with_llm(
                query, private_hits["results"], top_n=3
            )
            private_hits["count"] = len(private_hits["results"])
            decision = "private"
            result = {
                **private_hits,
                "decision": decision,
                "needs_share_prompt": False,
                "needs_clarification": False,
                "share_pending_action": None,
                "filters": hints,
            }
            _log_metrics(result["decision"], result["results"])
            _cache_set(cache_key, result)
            return result
        result = {
            **private_hits,
            "decision": "needs_clarification",
            "results": [],
            "count": 0,
            "needs_share_prompt": False,
            "needs_clarification": True,
            "clarification_prompt": (
                "Não encontrei nada sobre isso no que memorizei. "
                "Quer me dar mais detalhes ou outro termo?"
            ),
            "share_pending_action": None,
            "reason": "no_matches",
            "filters": hints,
        }
        _log_metrics(result["decision"], result["results"])
        _cache_set(cache_key, result)
        return result
    except Exception:
        _log_metrics("error", [])
        raise


async def share_pending_action_consume(
    phone: str,
) -> Optional[Dict[str, Any]]:
    """Read and consume a pending share_private_knowledge_in_group action."""
    from core.pending_actions import (
        PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
        consume_pending_action,
    )

    return await consume_pending_action(phone, PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE)


@dataclass
class RetrievalMetrics:
    """Structured log of a single retrieval attempt.

    Emitted at the end of every retrieve() call. Aggregating these
    over time lets you answer questions like: "qual a taxa de
    clarification no grupo X?" or "qual a class mais consultada?".
    """

    query_hash: str
    scope: str
    decision: str
    min_score: float
    candidates: int
    returned: int
    classes: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    top_score: float = 0.0
    avg_score: float = 0.0
    needs_clarification: bool = False
    cache_hit: bool = False
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _emit_retrieval_metrics(metrics: RetrievalMetrics) -> None:
    logger.info(
        "retrieval_quality",
        extra={"event_name": "retrieval_quality", **metrics.to_dict()},
    )


def _summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"classes": [], "sources": [], "top_score": 0.0, "avg_score": 0.0}
    scores = [float(r.get("score", 0.0)) for r in results]
    return {
        "classes": [str(r.get("class", "?")) for r in results],
        "sources": [str(r.get("source", "?")) for r in results],
        "top_score": max(scores),
        "avg_score": sum(scores) / len(scores),
    }


__all__ = [
    "is_rag_query",
    "retrieve",
    "share_pending_action_consume",
    "RAG_RETRIEVE_MIN_SCORE",
    "RetrievalMetrics",
]
