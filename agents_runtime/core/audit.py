"""Audit log helper - writes structured events to Firestore audit/ collection.

Used by orchestrator, command handler, admin endpoints, etc.
"""
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def log_action(
    actor: str,
    action: str,
    target: str = "",
    details: Optional[Dict[str, Any]] = None,
    phone_hash: str = "",
) -> bool:
    """Write an audit log entry.

    Args:
        actor: Who performed the action (user email, agent name, system)
        action: Action identifier (e.g., "CHAT_PROCESSED", "AGENT_UPDATED", "PROACTIVE_COMMAND")
        target: What was acted upon (agent_id, phone, etc.)
        details: Additional context (dict)
        phone_hash: SHA256 hash of phone (if PII)

    Returns:
        True if logged successfully, False otherwise
    """
    db = _get_firestore()
    if db is None:
        logger.debug("Firestore unavailable, audit not persisted")
        return False

    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "target": target,
            "phone_hash": phone_hash,
            "details": details or {},
            "module": "omnichannel-agentes",
        }
        db.collection("audit").add(entry)
        return True
    except Exception as e:
        logger.warning(f"audit log failed: {e}")
        return False


def log_chat(phone: str, agent_id: str, message_preview: str, response_preview: str, tokens_in: int = 0, tokens_out: int = 0) -> bool:
    """Convenience helper for chat events."""
    import hashlib
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16]
    return log_action(
        actor="user",
        action="CHAT_PROCESSED",
        target=agent_id,
        phone_hash=phone_hash,
        details={
            "message_preview": message_preview[:100],
            "response_preview": response_preview[:100],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        },
    )
