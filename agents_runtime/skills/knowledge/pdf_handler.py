"""PDF knowledge handler.

Extracts text from a PDF attachment and persists chunks with OpenAI
embeddings into either ``agent-knowledge-v2`` (individual) or
``group-knowledge-v2`` (group), respecting soft limits.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, Optional

from skills.knowledge import register_skill

logger = logging.getLogger(__name__)

MIME_TYPES = ["application/pdf"]


async def extract(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    extra = envelope.get("extra", {})
    mimetype = (extra.get("doc_mimetype") or "application/pdf").lower()
    source_name = extra.get("doc_file_name") or "document.pdf"
    raw_bytes = await _download_bytes(envelope)
    if raw_bytes is None:
        return None
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw_bytes))
        text = "\n".join(
            (page.extract_text() or "") for page in reader.pages
        )
    except Exception as exc:
        logger.warning("pdf_handler extract failed: %s", exc)
        return None
    return {
        "text": text,
        "source_name": source_name,
        "mimetype": mimetype,
        "raw_size": len(raw_bytes),
    }


async def _download_bytes(envelope: Dict[str, Any]) -> Optional[bytes]:
    """Fetch the file bytes from the envelope (base64 inline first, then API)."""
    import base64

    extra = envelope.get("extra", {})
    doc_b64 = extra.get("doc_base64", "")
    if doc_b64:
        try:
            return base64.b64decode(doc_b64)
        except Exception as exc:
            logger.warning("pdf_handler base64 decode failed: %s", exc)
    message_id = envelope.get("message_id", "")
    instance = envelope.get("instance", "")
    remote_jid = extra.get("remote_jid", "")
    if message_id and instance:
        try:
            from core.evolution_client import get_base64_from_media_message

            result = await get_base64_from_media_message(
                instance=instance,
                message_id=message_id,
                remote_jid=remote_jid,
            )
            media_b64 = result.get("base64", "")
            if media_b64:
                return base64.b64decode(media_b64)
        except Exception as exc:
            logger.warning("pdf_handler get_base64 failed: %s", exc)
    return None


async def persist(
    envelope: Dict[str, Any],
    extracted: Dict[str, Any],
    scope: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    phone = envelope.get("phone", "")
    text = extracted.get("text", "")
    source_name = extracted.get("source_name", "document.pdf")
    mimetype = extracted.get("mimetype", "application/pdf")
    extra_metadata = {"mimetype": mimetype, "scope": scope, **(metadata or {})}
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
                "category": metadata or {},
            }
        except Exception as exc:
            logger.warning("pdf_handler group index failed: %s", exc)
            return {"error": "rag_index_failed", "detail": str(exc)}

    try:
        from core.rag import index_private_document

        result = await index_private_document(
            phone=phone,
            text_content=text,
            source_title=source_name,
            category=extra_metadata.get("class", "legislacao") if extra_metadata.get("class") else "whatsapp_attachment",
            metadata=extra_metadata,
        )
        if result.get("error"):
            return {"error": "rag_index_failed", "detail": result.get("error")}
        return {
            "status": "rag_individual",
            "index_result": result,
            "source_name": source_name,
            "scope": scope,
            "category": metadata or {},
        }
    except Exception as exc:
        logger.warning("pdf_handler private index failed: %s", exc)
        return {"error": "rag_index_failed", "detail": str(exc)}


register_skill("pdf", type("PDFSkill", (), {
    "MIME_TYPES": MIME_TYPES,
    "extract": staticmethod(extract),
    "persist": staticmethod(persist),
})())

__all__ = ["extract", "persist", "MIME_TYPES"]
