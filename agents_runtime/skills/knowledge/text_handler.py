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
    scope: str,
) -> Dict[str, Any]:
    phone = envelope.get("phone", "")
    text = extracted.get("text", "")
    source_name = extracted.get("source_name", "note.txt")
    mimetype = extracted.get("mimetype", "text/plain")
    if not text:
        return {"error": "no_text_extracted", "mimetype": mimetype}

    if scope == "group":
        try:
            from tools.group import index_group_document

            group_jid = envelope.get("extra", {}).get("remote_jid", "")
            if "@g.us" not in group_jid:
                return {"error": "group_jid_required"}
            result = await index_group_document(
                phone=phone,
                group_jid=group_jid,
                text=text,
                visibility="group",
                source_name=source_name,
            )
            return {
                "status": "rag_group",
                "index_result": result,
                "source_name": source_name,
                "scope": scope,
            }
        except Exception as exc:
            logger.warning("text_handler group index failed: %s", exc)
            return {"error": "rag_index_failed", "detail": str(exc)}

    try:
        from core.rag import index_private_document

        result = await index_private_document(
            phone=phone,
            text_content=text,
            source_title=source_name,
            category="whatsapp_attachment",
            metadata={"mimetype": mimetype, "scope": scope},
        )
        if result.get("error"):
            return {"error": "rag_index_failed", "detail": result.get("error")}
        return {
            "status": "rag_individual",
            "index_result": result,
            "source_name": source_name,
            "scope": scope,
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
