"""LGPD cleanup utilities.

Functions:
- cleanup_old_history: delete mensagens > 90 dias
- cleanup_old_audit: audit logs > 5 anos (cron job)
- export_user_data: Art. 18 LGPD - exporta todos os dados de um phone
- delete_user_data: Art. 18 LGPD - esquece um contato completamente
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", str(365 * 5)))
BRT = timezone(timedelta(hours=-3))
RAG_MEMORY_COLLECTION = os.getenv("RAG_MEMORY_COLLECTION", "conversation-memory-v2")
RAG_PRIVATE_COLLECTION = os.getenv("RAG_PRIVATE_COLLECTION", "agent-knowledge-v2")
PENDING_ACTION_COLLECTION = os.getenv("PENDING_ACTION_COLLECTION", "pending-actions")


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def _filtered_query(collection, field: str, operator: str, value):
    from google.cloud.firestore_v1.base_query import FieldFilter

    return collection.where(filter=FieldFilter(field, operator, value))


def _delete_query_documents(db, query, batch_limit: int = 500) -> int:
    documents = list(query.limit(batch_limit).stream())
    if not documents:
        return 0
    batch = db.batch()
    for document in documents:
        batch.delete(document.reference)
    batch.commit()
    return len(documents)


def cleanup_old_history(batch_limit: int = 500) -> Dict[str, Any]:
    """Delete history messages older than RETENTION_DAYS.

    Scans all contatos/{phone}/historico/* documents and deletes
    those with ts < now - RETENTION_DAYS.

    Returns:
        {"deleted": int, "scanned": int, "duration_sec": float}
    """
    start = datetime.now(timezone.utc)
    db = _get_firestore()
    if db is None:
        return {"deleted": 0, "scanned": 0, "error": "firestore_unavailable"}

    cutoff = start - timedelta(days=RETENTION_DAYS)
    cutoff_iso = cutoff.isoformat()

    deleted = 0
    scanned = 0

    try:
        contatos = db.collection("contatos").limit(batch_limit).stream()
        for contato_doc in contatos:
            historico_ref = contato_doc.reference.collection("historico")
            old_msgs = historico_ref.where("ts", "<", cutoff_iso).limit(batch_limit).stream()
            batch = db.batch()
            batch_count = 0
            for msg in old_msgs:
                batch.delete(msg.reference)
                batch_count += 1
                deleted += 1
            if batch_count > 0:
                batch.commit()
            scanned += batch_count

        expires_at = datetime.now(BRT).isoformat()
        memory_query = _filtered_query(
            db.collection(RAG_MEMORY_COLLECTION),
            "expires_at",
            "<=",
            expires_at,
        )
        vector_deleted = _delete_query_documents(db, memory_query, batch_limit)
        deleted += vector_deleted
        scanned += vector_deleted
    except Exception as e:
        logger.exception(f"cleanup_old_history error: {e}")
        return {"deleted": deleted, "scanned": scanned, "error": str(e)}

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(f"cleanup_old_history: deleted={deleted} scanned={scanned} duration={duration:.2f}s")
    return {"deleted": deleted, "scanned": scanned, "duration_sec": duration}


def cleanup_old_audit(batch_limit: int = 500) -> Dict[str, Any]:
    """Delete audit logs older than AUDIT_RETENTION_DAYS (5 years default).

    Returns:
        {"deleted": int, "scanned": int}
    """
    start = datetime.now(timezone.utc)
    db = _get_firestore()
    if db is None:
        return {"deleted": 0, "scanned": 0, "error": "firestore_unavailable"}

    cutoff = start - timedelta(days=AUDIT_RETENTION_DAYS)
    cutoff_iso = cutoff.isoformat()

    deleted = 0
    scanned = 0

    try:
        old_logs = db.collection("audit").where("ts", "<", cutoff_iso).limit(batch_limit).stream()
        batch = db.batch()
        batch_count = 0
        for log in old_logs:
            batch.delete(log.reference)
            batch_count += 1
            deleted += 1
        if batch_count > 0:
            batch.commit()
        scanned = batch_count
    except Exception as e:
        logger.exception(f"cleanup_old_audit error: {e}")
        return {"deleted": deleted, "scanned": scanned, "error": str(e)}

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(f"cleanup_old_audit: deleted={deleted} scanned={scanned} duration={duration:.2f}s")
    return {"deleted": deleted, "scanned": scanned, "duration_sec": duration}


def export_user_data(phone: str) -> Dict[str, Any]:
    """LGPD Art. 18 - export all data for a phone.

    Returns everything we have on this user: contact, history, corrections.

    Args:
        phone: User's phone number

    Returns:
        {
            "phone": str,
            "contact": {...},
            "history": [...],
            "corrections": [...],
            "exported_at": str
        }
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    contact_ref = db.collection("contatos").document(phone)
    contact_doc = contact_ref.get()

    result = {
        "phone": phone,
        "exported_at": datetime.now(BRT).isoformat(),
        "contact": contact_doc.to_dict() if contact_doc.exists else None,
        "history": [],
        "corrections": [],
        "vector_memory": [],
        "private_knowledge": [],
    }

    if contact_doc.exists:
        history_ref = contact_ref.collection("historico")
        for msg in history_ref.stream():
            result["history"].append(msg.to_dict())

        corrections_ref = contact_ref.collection("corrections")
        for corr in corrections_ref.stream():
            result["corrections"].append(corr.to_dict())

    owner_hash = _owner_hash(phone)
    for collection_name, result_key in [
        (RAG_MEMORY_COLLECTION, "vector_memory"),
        (RAG_PRIVATE_COLLECTION, "private_knowledge"),
    ]:
        query = _filtered_query(db.collection(collection_name), "owner_hash", "==", owner_hash)
        for document in query.stream():
            data = document.to_dict()
            data.pop("vector_embedding", None)
            result[result_key].append(data)

    return result


def delete_user_data(phone: str) -> Dict[str, Any]:
    """LGPD Art. 18 - delete all data for a phone (right to be forgotten).

    Args:
        phone: User's phone number

    Returns:
        {"deleted_collections": [...], "phone": str}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    contact_ref = db.collection("contatos").document(phone)
    deleted = []

    try:
        for sub_name in ["historico", "corrections"]:
            sub_ref = contact_ref.collection(sub_name)
            docs = sub_ref.stream()
            batch = db.batch()
            count = 0
            for d in docs:
                batch.delete(d.reference)
                count += 1
            if count > 0:
                batch.commit()
            deleted.append(f"{sub_name}:{count}")

        contact_ref.delete()
        deleted.append("contact:1")

        try:
            db.collection("apelidos_custom").document(_hash_phone(phone)).delete()
            deleted.append("apelidos_custom:1")
        except Exception:
            pass

        owner_hash = _owner_hash(phone)
        for collection_name in [RAG_MEMORY_COLLECTION, RAG_PRIVATE_COLLECTION]:
            query = _filtered_query(db.collection(collection_name), "owner_hash", "==", owner_hash)
            count = _delete_query_documents(db, query)
            deleted.append(f"{collection_name}:{count}")

        db.collection(PENDING_ACTION_COLLECTION).document(owner_hash).delete()
        deleted.append(f"{PENDING_ACTION_COLLECTION}:1")

        return {"phone": phone, "deleted": deleted}
    except Exception as e:
        logger.exception(f"delete_user_data error: {e}")
        return {"error": str(e), "deleted": deleted}


def _hash_phone(phone: str) -> str:
    import hashlib
    return hashlib.sha256(phone.lower().encode("utf-8")).hexdigest()[:32]


def _owner_hash(phone: str) -> str:
    import hashlib
    normalized = "".join(char for char in str(phone) if char.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
