"""Migration script: update whatsapp_accounts owner_phone to correct value.

The seed config had +5511966830020 (incorrect). Real Jennifer owner is
+55 11 91738-9901 = 5511967389901.

Idempotent: re-runnable. Updates only docs where owner_phone differs.

Usage:
    python scripts/migrate_owner_phone_to_9901.py --dry-run
    python scripts/migrate_owner_phone_to_9901.py --apply
"""

from __future__ import annotations

import argparse
import sys

from agent_loader import _get_firestore_client


OLD_PHONE = "5511966830020"
NEW_PHONE = "5511967389901"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migrate owner_phone in whatsapp_accounts")
    parser.add_argument("--apply", action="store_true", help="Apply migration (default: dry-run)")
    args = parser.parse_args(argv if argv is not None else [])

    db = _get_firestore_client()
    if db is None:
        print("ERROR: Firestore client not available.")
        return 1

    coll = db.collection("whatsapp_accounts")
    docs = list(coll.stream())
    print(f"Found {len(docs)} whatsapp_accounts docs.\n")

    to_update = []
    for doc in docs:
        data = doc.to_dict() or {}
        phone = "".join(c for c in str(data.get("owner_phone", "") or "") if c.isdigit())
        if phone == OLD_PHONE:
            to_update.append((doc.id, data.get("instance", ""), OLD_PHONE))

    if not to_update:
        print("Nothing to migrate. All phones already correct.")
        return 0

    print(f"Found {len(to_update)} accounts to migrate:\n")
    for doc_id, instance, old in to_update:
        print(f"  {doc_id:30s} instance={instance:20s} {old} -> {NEW_PHONE}")

    if not args.apply:
        print("\n[DRY-RUN] Re-run with --apply to actually patch.")
        return 0

    # Apply
    batch = db.batch()
    for doc_id, _, _ in to_update:
        ref = coll.document(doc_id)
        batch.update(ref, {
            "owner_phone": NEW_PHONE,
            "owner_uid": NEW_PHONE,
        })
    batch.commit()
    print(f"\n[APPLIED] Patched {len(to_update)} accounts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
