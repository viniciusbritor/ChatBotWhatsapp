"""Group tools - membership and welcome message management."""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Ola pessoal! Sou a Jennifer, assistente do Vinicius na OmniChannel. "
    "Quando precisarem de algo (reunioes, atas, documentos), e so me chamar com @Jennifer. "
    "Estou aqui pra ajudar!"
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as e:
        logger.warning(f"Firestore unavailable: {e}")
        return None


async def register_group(
    group_jid: str,
    name: str,
    members: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a new group that Jennifer joined.

    Args:
        group_jid: WhatsApp group JID (e.g., "120363...@g.us")
        name: Group display name
        members: Initial list of member phone numbers

    Returns:
        {"group_jid": str, "members_count": int}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        ref = db.collection("grupos").document(group_jid.replace("/", "_"))
        ref.set({
            "group_jid": group_jid,
            "name": name,
            "joined_at": _now_iso(),
            "members_count": len(members or []),
            "proactive_mode": "normal",
            "welcome_sent": False,
            "is_active": True,
        }, merge=True)

        if members:
            batch = db.batch()
            for phone in members:
                m_ref = db.collection("grupos").document(group_jid.replace("/", "_")).collection("membros").document(phone)
                batch.set(m_ref, {
                    "phone": phone,
                    "joined_group_at": _now_iso(),
                    "is_active": True,
                }, merge=True)
            batch.commit()

        return {
            "group_jid": group_jid,
            "members_count": len(members or []),
        }
    except Exception as e:
        logger.error(f"register_group error: {e}")
        return {"error": str(e)}


async def update_members(group_jid: str, members: List[str]) -> Dict[str, Any]:
    """Update group members list."""
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        doc_ref = db.collection("grupos").document(group_jid.replace("/", "_"))
        doc_ref.update({
            "members_count": len(members),
            "last_member_sync": _now_iso(),
        })

        existing = doc_ref.collection("membros").stream()
        existing_phones = {doc.id for doc in existing}

        current_phones = set(members)
        to_add = current_phones - existing_phones
        to_remove = existing_phones - current_phones

        batch = db.batch()
        for phone in to_add:
            ref = doc_ref.collection("membros").document(phone)
            batch.set(ref, {
                "phone": phone,
                "joined_group_at": _now_iso(),
                "is_active": True,
            })
        for phone in to_remove:
            ref = doc_ref.collection("membros").document(phone)
            batch.update(ref, {"is_active": False, "left_at": _now_iso()})
        batch.commit()

        return {
            "group_jid": group_jid,
            "added": len(to_add),
            "removed": len(to_remove),
        }
    except Exception as e:
        logger.error(f"update_members error: {e}")
        return {"error": str(e)}


async def get_group_members(group_jid: str) -> List[str]:
    """Get active members of a group."""
    db = _get_firestore()
    if db is None:
        return []

    try:
        docs = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .where("is_active", "==", True)
            .stream()
        )
        return [doc.id for doc in docs]
    except Exception as e:
        logger.error(f"get_group_members error: {e}")
        return []


async def mark_welcome_sent(group_jid: str) -> bool:
    """Mark welcome message as sent."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        db.collection("grupos").document(group_jid.replace("/", "_")).update({
            "welcome_sent": True,
            "welcome_sent_at": _now_iso(),
        })
        return True
    except Exception as e:
        logger.error(f"mark_welcome_sent error: {e}")
        return False


async def is_welcome_sent(group_jid: str) -> bool:
    """Check if welcome message was already sent."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if doc.exists:
            return doc.to_dict().get("welcome_sent", False)
        return False
    except Exception:
        return False


def get_welcome_message() -> str:
    """Get the welcome message template."""
    return WELCOME_MESSAGE


async def is_jennifer_in_group(group_jid: str) -> bool:
    """Check if Jennifer is registered in this group."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = db.collection("grupos").document(group_jid.replace("/", "_")).get()
        if doc.exists:
            return doc.to_dict().get("is_active", False)
        return False
    except Exception:
        return False


async def list_active_groups() -> List[Dict[str, Any]]:
    """List all active groups Jennifer is in."""
    db = _get_firestore()
    if db is None:
        return []
    try:
        docs = db.collection("grupos").where("is_active", "==", True).stream()
        return [{"group_jid": doc.id, **doc.to_dict()} for doc in docs]
    except Exception:
        return []