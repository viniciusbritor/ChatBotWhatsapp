"""Group resolver - email/phone to groups via Firestore.

Phase 1 foundation: resolves identity (phone or email) to a list of group_ids.
The group_policies enforcement happens in core/policy.py (consumer).
"""
import os
import logging
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl_sec = 86400


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception as e:
        logger.warning(f"Firestore unavailable: {e}")
        return None


def _hash_email(email: str) -> str:
    """SHA256 of email, first 16 chars."""
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


def _hash_phone(phone: str) -> str:
    """SHA256 of phone, first 16 chars."""
    return hashlib.sha256(phone.lower().strip().encode("utf-8")).hexdigest()[:16]


def _is_cache_fresh(entry: Dict[str, Any]) -> bool:
    if not entry or "loaded_at" not in entry:
        return False
    age = (datetime.now(timezone.utc) - entry["loaded_at"]).total_seconds()
    return age < _cache_ttl_sec


def resolve_email_for_phone(phone: str) -> Optional[str]:
    """Resolve phone to primary email via phone_to_email collection."""
    if not phone:
        return None

    cache_key = f"phone:{phone}"
    if cache_key in _cache and _is_cache_fresh(_cache[cache_key]):
        return _cache[cache_key].get("value")

    db = _get_firestore()
    if db is None:
        return None

    try:
        phone_hash = _hash_phone(phone)
        doc = db.collection("phone_to_email").document(phone_hash).get()
        if doc.exists:
            data = doc.to_dict()
            email = data.get("primary_email")
            _cache[cache_key] = {
                "value": email,
                "loaded_at": datetime.now(timezone.utc),
            }
            logger.debug(f"Resolved phone {phone} -> email {email}")
            return email
        return None
    except Exception as e:
        logger.error(f"resolve_email_for_phone error: {e}")
        return None


def resolve_groups_for_email(email: str) -> List[str]:
    """Resolve email to list of groups via email_groups collection."""
    if not email:
        return []

    cache_key = f"email:{email}"
    if cache_key in _cache and _is_cache_fresh(_cache[cache_key]):
        return _cache[cache_key].get("value", [])

    db = _get_firestore()
    if db is None:
        return []

    try:
        email_hash = _hash_email(email)
        doc = db.collection("email_groups").document(email_hash).get()
        if doc.exists:
            data = doc.to_dict()
            groups = data.get("groups", [])
            _cache[cache_key] = {
                "value": groups,
                "loaded_at": datetime.now(timezone.utc),
            }
            logger.debug(f"Resolved email {email} -> groups {groups}")
            return groups
        return []
    except Exception as e:
        logger.error(f"resolve_groups_for_email error: {e}")
        return []


def invalidate_cache():
    """Force cache reload."""
    global _cache
    _cache = {}
