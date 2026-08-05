"""Ferramenta transversal de consulta ao historico de conversas.

Qualquer agente (calendar, email, drive, web, jennifer) pode chamar
``search_chat_history`` para buscar contexto relevante sobre o usuario.
Zero custo adicional — keyword search em Firestore plain, sem embeddings.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def search_chat_history(
    phone: str,
    query: str,
    limit: int = 5,
) -> Dict[str, Any]:
    if not phone or not str(phone).strip():
        return {"results": [], "count": 0, "error": "missing_phone"}
    if not query or not str(query).strip():
        return {"results": [], "count": 0, "error": "empty_query"}

    try:
        from core.rag import search_conversation_memory

        raw = await search_conversation_memory(phone, query, limit)
    except Exception as exc:
        logger.warning("search_chat_history_failed phone=%s error=%s", phone, exc)
        return {"results": [], "count": 0, "error": str(exc)[:200]}

    results: List[Dict[str, Any]] = []
    for r in raw:
        results.append({
            "text": r.get("text", "")[:300],
            "direction": r.get("direction", "in"),
            "created_at": r.get("created_at", ""),
        })
    return {"results": results, "count": len(results)}


async def get_chat_context(phone: str, limit: int = 10) -> Dict[str, Any]:
    """Retorna os ultimos N turnos como string + lista estruturada."""
    if not phone or not str(phone).strip():
        return {"text": "", "turns": [], "count": 0}

    try:
        from core.rag import get_conversation_history

        text = await get_conversation_history(phone, limit)
        return {"text": text, "turns": [], "count": len(text.split("\n")) if text else 0}
    except Exception as exc:
        logger.warning("get_chat_context_failed phone=%s error=%s", phone, exc)
        return {"text": "", "turns": [], "count": 0, "error": str(exc)[:200]}
