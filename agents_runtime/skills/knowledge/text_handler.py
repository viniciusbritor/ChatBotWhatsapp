"""Plain text knowledge handler."""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

from skills.knowledge import register_skill

logger = logging.getLogger(__name__)

MIME_TYPES = [
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/csv",
]


async def extract(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    extra = envelope.get("extra", {})
    mimetype = (extra.get("doc_mimetype") or "text/plain").lower()
    source_name = extra.get("doc_file_name") or "note.txt"
    doc_b64 = extra.get("doc_base64", "")
    if not doc_b64:
        return None
    try:
        text = base64.b64decode(doc_b64).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("text_handler decode failed: %s", exc)
        return None
    return {
        "text": text,
        "source_name": source_name,
        "mimetype": mimetype,
        "raw_size": len(text.encode("utf-8")),
    }


async def persist(
    envelope: Dict[str, Any],
    extracted: Dict[str, Any],
    scope: str = "private",
    metadata=None,
) -> Dict[str, Any]:
    phone = envelope.get("phone", "")
    metadata = metadata or {}
    text = extracted.get("text", "")
    source_name = extracted.get("source_name", "note.txt")
    mimetype = extracted.get("mimetype", "text/plain")
    extra_metadata = {"mimetype": mimetype, "scope": "private", **metadata}
    if not text:
        return {"error": "no_text_extracted", "mimetype": mimetype}

    if scope == "group":
        group_jid = (envelope.get("extra", {}) or {}).get("remote_jid", "")
        if "@g.us" not in str(group_jid):
            return {"error": "group_jid_required"}

    try:
        from core.rag import index_private_document

        result = await index_private_document(
            phone=phone,
            text_content=text,
            source_title=source_name,
            category=extra_metadata.get("class", "legislacao") if extra_metadata.get("class") else "whatsapp_attachment",
            metadata=extra_metadata,
            class_=extra_metadata.get("class"),
            group=extra_metadata.get("group"),
            theme=extra_metadata.get("theme"),
        )
        if result.get("error"):
            return {"error": "rag_index_failed", "detail": result.get("error")}
        if result.get("partial"):
            chunks_idx = result.get("chunks_indexed", 0)
            total = result.get("chunks", 0)
            return {
                "status": "rag_individual_partial",
                "index_result": result,
                "source_name": source_name,
                "scope": "private",
                "category": metadata or {},
                "chunks_indexed": chunks_idx,
                "chunks_total": total,
            }
        chunks_indexed = result.get("chunks_indexed", result.get("chunks", 0))
        return {
            "status": "rag_individual",
            "index_result": result,
            "source_name": source_name,
            "scope": "private",
            "category": metadata,
            "chunks_indexed": chunks_indexed,
        }
    except Exception as exc:
        logger.warning("text_handler private index failed: %s", exc)
        return {"error": "rag_index_failed", "detail": str(exc)}


register_skill("text", type("TextSkill", (), {
    "MIME_TYPES": MIME_TYPES,
    "extract": staticmethod(extract),
    "persist": staticmethod(persist),
})())

__all__ = ["extract", "persist", "MIME_TYPES"]
