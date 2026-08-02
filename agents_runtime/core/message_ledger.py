"""Distributed message-processing ledger backed by Firestore.

The ledger is the single source of truth for webhook idempotency, transient
retries and delivery state. It replaces the previous in-memory dedupe and the
manual DLQ publish so that every Cloud Run instance converges on the same
result for the same ``message_id``.

States:
- ``received``        - webhook accepted, payload stored.
- ``processing``      - push handler claimed the row.
- ``response_ready``  - orchestrator produced a reply (delivered or pending).
- ``delivered``       - Evolution acknowledged the outbound message.
- ``failed_terminal`` - non-retriable error; never re-processed.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from core.timezone import now_brt

from google.cloud import firestore

logger = logging.getLogger(__name__)

_LEDGER_COLLECTION = os.getenv("PUBSUB_LEDGER_COLLECTION", "message-processing")
_LEASE_SECONDS = int(os.getenv("PUBSUB_LEASE_SECONDS", "120"))
_LEASE_RENEW_SECONDS = int(os.getenv("PUBSUB_LEASE_RENEW_SECONDS", "30"))
_RETENTION_DAYS = int(os.getenv("PUBSUB_LEDGER_RETENTION_DAYS", "7"))

STATES = {
    "received",
    "processing",
    "response_ready",
    "delivered",
    "failed_terminal",
}


@dataclass
class LedgerEntry:
    message_id: str
    state: str = "received"
    instance: str = ""
    remote_jid: str = ""
    phone: str = ""
    request_id: str = ""
    attempts: int = 0
    last_error: str = ""
    response_id: str = ""
    delivery_attempts: int = 0
    last_delivery_error: str = ""
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    reply: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_brt() -> datetime:
    return now_brt()


def _now_iso() -> str:
    return _now_brt().isoformat()


def _expiry_iso() -> str:
    return (_now_brt() + timedelta(days=_RETENTION_DAYS)).isoformat()


def normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def deterministic_request_id(*parts: str) -> str:
    joined = "|".join(str(p) for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def resolve_message_id(envelope: Dict[str, Any]) -> str:
    """Pick a deterministic message id from the envelope.

    Evolution may omit ``key.id`` for some events. We always synthesise a stable
    id from the (instance, remote_jid, publish_time) tuple so retries from
    Evolution or Pub/Sub collapse to a single ledger entry.
    """
    explicit = str(envelope.get("message_id") or "").strip()
    if explicit:
        return explicit
    candidate = deterministic_request_id(
        envelope.get("instance", ""),
        envelope.get("remote_jid", ""),
        envelope.get("publish_time", ""),
        envelope.get("phone", ""),
    )
    envelope["message_id"] = candidate
    envelope["request_id"] = envelope.get("request_id") or candidate
    return candidate


def _get_firestore():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ledger firestore unavailable: %s", exc)
        return None


def _doc_id(message_id: str) -> str:
    return hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:32]


def _owner_token() -> str:
    suffix = os.getenv("HOSTNAME") or os.getenv("K_REVISION") or "local"
    return f"{suffix}:{os.getpid()}"


def register_or_load(message_id: str, envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Idempotently create a ledger entry and return the persisted snapshot.

    Returns None when Firestore is not configured (tests/CI without ADC).
    """
    db = _get_firestore()
    if db is None:
        return None
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    snapshot: Dict[str, Any]
    try:
        snapshot = doc_ref.get(timeout=5).to_dict() or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ledger read failed: %s", exc)
        snapshot = {}
    now = _now_iso()
    payload = envelope.get("payload") or {}
    if not snapshot:
        entry = LedgerEntry(
            message_id=message_id,
            instance=envelope.get("instance", ""),
            remote_jid=envelope.get("remote_jid", ""),
            phone=normalize_phone(envelope.get("phone", "")),
            request_id=envelope.get("request_id", message_id),
            attempts=1,
            created_at=now,
            updated_at=now,
            expires_at=_expiry_iso(),
            payload=payload,
        )
        try:
            doc_ref.set(entry.to_dict())
            snapshot = entry.to_dict()
        except Exception as exc:  # noqa: BLE001
            logger.error("ledger initialise failed: %s", exc)
            return None
    else:
        updates = {"updated_at": now}
        if not snapshot.get("instance"):
            updates["instance"] = envelope.get("instance", "")
        if not snapshot.get("remote_jid"):
            updates["remote_jid"] = envelope.get("remote_jid", "")
        if not snapshot.get("phone"):
            updates["phone"] = normalize_phone(envelope.get("phone", ""))
        try:
            doc_ref.update(updates)
            snapshot.update(updates)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ledger touch failed: %s", exc)
    return snapshot


def claim(message_id: str) -> Optional[Dict[str, Any]]:
    """Acquire a lease so only one instance processes the message.

    Uses a Firestore transaction to atomically read-then-write,
    preventing the race condition where two Cloud Run instances
    both claim the same message simultaneously.
    """
    db = _get_firestore()
    if db is None:
        return None
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    owner = _owner_token()
    lease_expires = time.time() + _LEASE_SECONDS
    transaction = db.transaction()

    @firestore.transactional
    def _claim_in_transaction(txn):
        try:
            snapshot = doc_ref.get(transaction=txn, timeout=5).to_dict() or {}
        except Exception:
            return None
        state = snapshot.get("state")
        if state in {"response_ready", "delivered", "failed_terminal"}:
            return snapshot
        if (
            state == "processing"
            and snapshot.get("lease_expires_at", 0) > time.time()
            and snapshot.get("lease_owner")
            and snapshot.get("lease_owner") != owner
        ):
            return None
        updates = {
            "state": "processing",
            "attempts": (snapshot.get("attempts") or 0) + 1,
            "lease_owner": owner,
            "lease_expires_at": lease_expires,
            "updated_at": _now_iso(),
            "last_error": "",
        }
        txn.update(doc_ref, updates)
        snapshot.update(updates)
        return snapshot

    try:
        return _claim_in_transaction(transaction)
    except Exception as exc:
        logger.warning("ledger claim transaction failed: %s", exc)
        return None


def renew_lease(message_id: str) -> None:
    db = _get_firestore()
    if db is None:
        return
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    try:
        doc_ref.update({
            "lease_expires_at": time.time() + _LEASE_SECONDS,
            "updated_at": _now_iso(),
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("ledger lease renew failed: %s", exc)


def release_lease(message_id: str) -> None:
    db = _get_firestore()
    if db is None:
        return
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    try:
        doc_ref.update({
            "lease_owner": "",
            "lease_expires_at": 0.0,
            "updated_at": _now_iso(),
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("ledger lease release failed: %s", exc)


def mark_response(message_id: str, reply: Dict[str, Any]) -> None:
    db = _get_firestore()
    if db is None:
        return
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    updates = {
        "state": "response_ready",
        "reply": reply or {},
        "response_id": (reply or {}).get("request_id", message_id),
        "lease_owner": "",
        "lease_expires_at": 0.0,
        "updated_at": _now_iso(),
        "last_error": "",
    }
    try:
        doc_ref.update(updates)
    except Exception as exc:  # noqa: BLE001
        logger.error("ledger mark_response failed: %s", exc)


def mark_delivered(message_id: str, *, delivery_attempts: int = 1, error: str = "") -> None:
    db = _get_firestore()
    if db is None:
        return
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    updates = {
        "state": "delivered" if not error else "response_ready",
        "delivery_attempts": delivery_attempts,
        "last_delivery_error": error,
        "updated_at": _now_iso(),
    }
    try:
        doc_ref.update(updates)
    except Exception as exc:  # noqa: BLE001
        logger.error("ledger mark_delivered failed: %s", exc)


def mark_failed(message_id: str, error: str, *, terminal: bool = True) -> None:
    db = _get_firestore()
    if db is None:
        return
    doc_ref = db.collection(_LEDGER_COLLECTION).document(_doc_id(message_id))
    updates = {
        "state": "failed_terminal" if terminal else "processing",
        "last_error": error,
        "lease_owner": "" if terminal else _owner_token(),
        "lease_expires_at": 0.0 if terminal else time.time() + _LEASE_SECONDS,
        "updated_at": _now_iso(),
    }
    try:
        doc_ref.update(updates)
    except Exception as exc:  # noqa: BLE001
        logger.error("ledger mark_failed failed: %s", exc)


def is_terminal(snapshot: Optional[Dict[str, Any]]) -> bool:
    if not snapshot:
        return False
    state = snapshot.get("state")
    return state in {"response_ready", "delivered", "failed_terminal"}


def lease_alive(snapshot: Optional[Dict[str, Any]]) -> bool:
    if not snapshot:
        return False
    return float(snapshot.get("lease_expires_at", 0)) > time.time()
