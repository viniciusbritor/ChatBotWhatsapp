"""Google Drive saver skill.

Used only when the user explicitly requests Drive storage
(e.g., "salvar no drive", "manda pra mim", "guardar no gdrive").
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from skills.knowledge import register_skill

logger = logging.getLogger(__name__)

MIME_TYPES: list = []


async def extract(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Drive saver does not need its own extraction; the orchestrator already
    extracted text for the candidate skill. We reuse that text here."""
    return envelope.get("_drive_extracted")


async def persist(
    envelope: Dict[str, Any],
    extracted: Dict[str, Any],
    scope: str,
) -> Dict[str, Any]:
    phone = envelope.get("phone", "")
    text = (extracted or {}).get("text", "")
    source_name = (extracted or {}).get("source_name", "document")
    mimetype = (extracted or {}).get("mimetype", "application/octet-stream")

    if scope == "group":
        try:
            from tools.google_drive import get_group_drive_folder, upload_file

            group_jid = envelope.get("extra", {}).get("remote_jid", "")
            if "@g.us" not in group_jid:
                return {"error": "group_jid_required"}
            folder_id = await get_group_drive_folder(group_jid)
            if not folder_id:
                return {"error": "no_group_folder", "group_jid": group_jid}
            result = await upload_file(
                phone=phone,
                folder_id=folder_id,
                filename=source_name,
                content=text,
                mime_type=mimetype,
            )
            return {
                "status": "drive_group",
                "upload_result": result,
                "source_name": source_name,
                "scope": scope,
            }
        except Exception as exc:
            logger.warning("drive_saver group upload failed: %s", exc)
            return {"error": "drive_upload_failed", "detail": str(exc)}

    try:
        from tools.google_drive import upload_file

        result = await upload_file(
            phone=phone,
            folder_id="root",
            filename=source_name,
            content=text,
            mime_type=mimetype,
        )
        return {
            "status": "drive_individual",
            "upload_result": result,
            "source_name": source_name,
            "scope": scope,
        }
    except Exception as exc:
        logger.warning("drive_saver individual upload failed: %s", exc)
        return {"error": "drive_upload_failed", "detail": str(exc)}


register_skill("drive", type("DriveSkill", (), {
    "MIME_TYPES": MIME_TYPES,
    "extract": staticmethod(extract),
    "persist": staticmethod(persist),
})())

__all__ = ["extract", "persist", "MIME_TYPES"]
