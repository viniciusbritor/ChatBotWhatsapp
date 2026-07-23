"""Create the composite Firestore index required by ``message-history``.

The runtime reads ``message-history`` ordered by ``created_at`` DESC
and filtered by ``owner_hash == owner_hash(phone)``. Firestore requires a
composite index for that combination; this script ensures it exists
without requiring manual clicks in the console.

Usage::

    python scripts/ensure_message_history_index.py
    python scripts/ensure_message_history_index.py --collection message-history
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ensure_message_history_index")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=os.getenv("RAG_MESSAGE_HISTORY_COLLECTION", "message-history"))
    parser.add_argument("--project", default=os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"))
    args = parser.parse_args()

    try:
        from google.cloud import firestore_admin
    except Exception as exc:  # noqa: BLE001
        logger.error("firestore_admin not available: %s", exc)
        return 1

    client = firestore_admin.FirestoreAdminClient()
    parent = f"projects/{args.project}/databases/(default)/collectionGroups/{args.collection}"
    index_id = "owner_hash_asc_created_at_desc"

    index = firestore_admin.Index(
        query_scope=firestore_admin.Index.QueryScope.COLLECTION,
        fields=[
            firestore_admin.Index.IndexField(
                field_path="owner_hash",
                order=firestore_admin.Index.IndexField.Order.ASCENDING,
            ),
            firestore_admin.Index.IndexField(
                field_path="created_at",
                order=firestore_admin.Index.IndexField.Order.DESCENDING,
            ),
        ],
    )

    request = firestore_admin.CreateIndexRequest(
        parent=parent,
        index=index,
    )
    try:
        operation = client.create_index(request=request)
        result = operation.result()
        logger.info("index created: %s", result.name)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "ALREADY_EXISTS" in msg or "already exists" in msg.lower():
            logger.info("index already exists: %s/%s", parent, index_id)
            return 0
        logger.error("create_index failed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
