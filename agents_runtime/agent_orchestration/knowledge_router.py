"""Knowledge router (Fase G).

Decides *how* to persist an attachment: which skill, which scope (private vs
group), and whether the user explicitly asked for Google Drive instead of
Firestore Vector.

The router uses two layers:

1. **Heuristic** (deterministic): MIME match and keyword match. Always runs.
2. **LLM tie-breaker** (DeepSeek V4 Flash): only when the heuristic returns
   ambiguous and the attachment text is non-empty. Avoids unnecessary LLM
   calls on the hot path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

from skills.knowledge import find_skill_by_mime, get_skill

logger = logging.getLogger(__name__)


KEYWORDS_RAG = {
    "memorizar", "memorize", "memorizando", "indexar", "indexe",
    "armazenar", "armazene", "cache", "vector", "firestore",
    "base de conhecimento", "knowledge base", "no conhecimento",
    "rag", "salvar", "salve", "gravar", "grava", "guardar", "guarde",
}

KEYWORDS_DRIVE = {
    "drive", "gdrive", "manda pra mim", "envia pra mim",
    "guarda no drive", "salva no drive", "quero no meu drive",
    "quero no gdrive",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _detect_intent_keywords(text: str) -> str:
    """Returns one of: 'drive', 'rag', 'ambiguous'."""
    normalized = _normalize(text)
    if not normalized:
        return "ambiguous"
    has_drive = any(kw in normalized for kw in KEYWORDS_DRIVE)
    has_rag = any(kw in normalized for kw in KEYWORDS_RAG)
    if has_drive and not has_rag:
        return "drive"
    if has_rag and not has_drive:
        return "rag"
    if has_drive and has_rag:
        return "drive"
    return "ambiguous"


def _detect_scope(envelope: Dict[str, Any]) -> str:
    """Returns 'group' if the envelope comes from a WhatsApp group JID."""
    extra = envelope.get("extra", {})
    remote_jid = extra.get("remote_jid", "")
    if "@g.us" in str(remote_jid):
        return "group"
    return "private"


async def _llm_classify_intent(text: str) -> Optional[str]:
    """Use DeepSeek V4 Flash to disambiguate RAG vs Drive when keywords tie.

    Returns 'rag', 'drive' or None on failure.
    """
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
            max_tokens=8,
            timeout=8,
            model_kwargs={"extra_body": {"cache_mode": "default"}},
        )
        prompt = (
            "Classifique o pedido do usuario sobre um arquivo anexo em UMA palavra:\n"
            "- 'rag' se o usuario quer armazenar no Firestore Vector (base de conhecimento).\n"
            "- 'drive' se o usuario quer salvar no Google Drive.\n"
            f"Pedido: {text.strip()[:300]}\nResposta:"
        )
        result = await asyncio.to_thread(llm.invoke, prompt)
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        cleaned = _normalize(raw).strip(" .!?\":'").lower()
        if "rag" in cleaned:
            return "rag"
        if "drive" in cleaned:
            return "drive"
        return None
    except Exception as exc:
        logger.warning("llm_classify_intent failed: %s", exc)
        return None


async def route_attachment(
    envelope: Dict[str, Any],
    user_text: str,
) -> Dict[str, Any]:
    """Decide which skill to use and persist the attachment.

    Returns a dict ready to be used by ``orchestrator._handle_attachment``:

        {
          "decision": "rag" | "drive" | "ambiguous",
          "scope": "private" | "group",
          "skill_name": str | None,
          "skill": object | None,
          "extracted": dict | None,
          "persist_result": dict | None,
        }
    """
    decision = _detect_intent_keywords(user_text)
    if decision == "ambiguous":
        llm_decision = await _llm_classify_intent(user_text)
        if llm_decision:
            decision = llm_decision

    scope = _detect_scope(envelope)

    mime = (envelope.get("extra", {}) or {}).get("doc_mimetype", "") or ""
    skill = find_skill_by_mime(mime)
    skill_name = None
    if skill is not None:
        for name, registered in _iter_skills():
            if registered is skill:
                skill_name = name
                break

    if decision == "drive":
        drive_skill = get_skill("drive")
        if drive_skill is None:
            return {
                "decision": decision,
                "scope": scope,
                "skill_name": None,
                "skill": None,
                "extracted": None,
                "persist_result": {"error": "drive_skill_missing"},
            }
        return {
            "decision": decision,
            "scope": scope,
            "skill_name": "drive",
            "skill": drive_skill,
            "extracted": None,
            "persist_result": None,
        }

    if skill is None:
        return {
            "decision": decision,
            "scope": scope,
            "skill_name": None,
            "skill": None,
            "extracted": None,
            "persist_result": {"error": "no_skill_for_mime", "mime": mime},
        }

    return {
        "decision": decision,
        "scope": scope,
        "skill_name": skill_name,
        "skill": skill,
        "extracted": None,
        "persist_result": None,
        "category": None,
    }


async def categorize_and_extract(
    envelope: Dict[str, Any],
    skill: Any,
) -> Dict[str, Any]:
    """Extrai texto e categoriza o documento. Devolve dict com extracted + category."""
    source_name = (
        (envelope.get("extra", {}) or {}).get("doc_file_name")
        or envelope.get("source_name", "")
        or "document"
    )
    extracted = await skill.extract(envelope)
    if not extracted:
        return {"extracted": None, "category": None}

    from agent_orchestration.categorizer import categorize

    text = (extracted.get("text") or "").strip()
    category = await categorize(text, source_name)
    return {"extracted": extracted, "category": category}


def _iter_skills():
    from skills.knowledge import SKILLS as _SKILLS

    return _SKILLS.items()


__all__ = [
    "route_attachment",
    "_detect_intent_keywords",
    "_detect_scope",
    "_llm_classify_intent",
]
