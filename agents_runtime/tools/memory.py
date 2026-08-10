"""Fatos estruturados do usuario — memoria persistente de informacoes pessoais.

Jennifer usa estas tools para salvar e recuperar fatos (enderecos, nomes,
preferencias, datas importantes) de forma estruturada, independente do
historico de conversa que expira.

Storage: Firestore ``usuarios/{phone}/facts/{fact_id}``.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

FACTS_SUBCOLLECTION = "facts"


def _get_firestore():
    from google.cloud import firestore
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if not project:
        return None
    return firestore.Client(project=project)


def _normalize_phone(phone: str) -> str:
    return "".join(c for c in str(phone or "") if c.isdigit())


async def save_fact(
    key: str,
    value: str,
    category: str = "",
    phone: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Salva (ou atualiza) um fato estruturado do usuario."""
    if not phone:
        return {"error": "missing_phone", "saved": False}
    key = str(key or "").strip().lower().replace(" ", "_")[:100]
    value = str(value or "").strip()[:2000]
    if not key or not value:
        return {"error": "key_e_value_obrigatorios", "saved": False}

    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable", "saved": False}

    try:
        normalized = _normalize_phone(phone)
        doc_id = key
        ref = db.collection("usuarios").document(normalized).collection(FACTS_SUBCOLLECTION).document(doc_id)
        ref.set({
            "key": key,
            "value": value,
            "category": str(category or "").strip()[:80],
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "updated_at": __import__("datetime").datetime.now().isoformat(),
        }, merge=True)
        return {"saved": True, "key": key, "value": value, "phone": normalized}
    except Exception as exc:
        logger.warning("memory_save_fact_failed phone=%s key=%s error=%s", phone, key, exc)
        return {"error": str(exc)[:200], "saved": False}


async def search_facts(
    query: str = "",
    category: str = "",
    phone: str = "",
    limit: int = 10,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Busca fatos do usuario por keyword ou categoria."""
    if not phone:
        return {"results": [], "count": 0, "error": "missing_phone"}
    db = _get_firestore()
    if db is None:
        return {"results": [], "count": 0, "error": "firestore_unavailable"}

    try:
        normalized = _normalize_phone(phone)
        docs = (
            db.collection("usuarios")
            .document(normalized)
            .collection(FACTS_SUBCOLLECTION)
            .limit(limit)
            .stream()
        )
        results: List[Dict[str, Any]] = []
        needle = str(query or "").strip().lower()
        cat = str(category or "").strip().lower()
        for doc in docs:
            data = doc.to_dict() or {}
            key = str(data.get("key", ""))
            value = str(data.get("value", ""))
            cat_doc = str(data.get("category", "")).lower()
            if needle and needle not in f"{key} {value}".lower():
                continue
            if cat and cat not in cat_doc:
                continue
            results.append({
                "key": key,
                "value": value,
                "category": data.get("category", ""),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
            })
        return {"results": results, "count": len(results), "phone": normalized}
    except Exception as exc:
        logger.warning("memory_search_facts_failed phone=%s error=%s", phone, exc)
        return {"results": [], "count": 0, "error": str(exc)[:200]}


async def list_facts(phone: str = "", limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
    """Lista todos os fatos do usuario (sem filtro)."""
    return await search_facts(query="", phone=phone, limit=limit)


async def delete_fact(key: str = "", phone: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Remove um fato do usuario."""
    if not phone or not key:
        return {"error": "phone_e_key_obrigatorios", "deleted": False}
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable", "deleted": False}
    try:
        normalized = _normalize_phone(phone)
        doc_id = str(key).strip().lower().replace(" ", "_")[:100]
        db.collection("usuarios").document(normalized).collection(FACTS_SUBCOLLECTION).document(doc_id).delete()
        return {"deleted": True, "key": doc_id, "phone": normalized}
    except Exception as exc:
        logger.warning("memory_delete_fact_failed phone=%s key=%s error=%s", phone, key, exc)
        return {"error": str(exc)[:200], "deleted": False}
