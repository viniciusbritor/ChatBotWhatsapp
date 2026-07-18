import asyncio
import hashlib
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

BRT = timezone(timedelta(hours=-3))
PENDING_ACTION_TTL_SEC = int(os.getenv("PENDING_ACTION_TTL_SEC", "300"))
PENDING_ACTION_COLLECTION = os.getenv("PENDING_ACTION_COLLECTION", "pending-actions")
_local_actions: Dict[str, Dict[str, Any]] = {}
_local_lock = threading.RLock()


def _owner_hash(phone: str) -> str:
    normalized = "".join(character for character in str(phone) if character.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _get_firestore():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def _is_expired(action: Dict[str, Any]) -> bool:
    try:
        return datetime.fromisoformat(action["expires_at"]) <= datetime.now(BRT)
    except Exception:
        return True


async def set_pending_action(
    phone: str,
    action_type: str,
    payload: Optional[Dict[str, Any]] = None,
    ttl_sec: int = PENDING_ACTION_TTL_SEC,
) -> Dict[str, Any]:
    owner_hash = _owner_hash(phone)
    now = datetime.now(BRT)
    action = {
        "owner_hash": owner_hash,
        "action_type": action_type,
        "payload": dict(payload or {}),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(1, ttl_sec))).isoformat(),
    }
    with _local_lock:
        _local_actions[owner_hash] = dict(action)
    database = _get_firestore()
    if database is not None:
        await asyncio.to_thread(
            database.collection(PENDING_ACTION_COLLECTION).document(owner_hash).set,
            action,
        )
    return action


async def get_pending_action(phone: str) -> Optional[Dict[str, Any]]:
    owner_hash = _owner_hash(phone)
    database = _get_firestore()
    action = None
    if database is not None:
        document = await asyncio.to_thread(
            database.collection(PENDING_ACTION_COLLECTION).document(owner_hash).get
        )
        if document.exists:
            action = document.to_dict()
    if action is None:
        with _local_lock:
            cached = _local_actions.get(owner_hash)
            action = dict(cached) if cached else None
    if not action:
        return None
    if _is_expired(action):
        await clear_pending_action(phone)
        return None
    return action


async def clear_pending_action(phone: str) -> None:
    owner_hash = _owner_hash(phone)
    with _local_lock:
        _local_actions.pop(owner_hash, None)
    database = _get_firestore()
    if database is not None:
        await asyncio.to_thread(
            database.collection(PENDING_ACTION_COLLECTION).document(owner_hash).delete
        )


async def consume_pending_action(phone: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    action = await get_pending_action(phone)
    if not action:
        return None
    if expected_type and action.get("action_type") != expected_type:
        return None
    await clear_pending_action(phone)
    return action
