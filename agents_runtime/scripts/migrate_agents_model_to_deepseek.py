"""Migrate legacy MiniMax models to deepseek-v4-flash in Firestore agents/.

Idempotent: safe to re-run. Updates only documents whose model field
matches one of the LEGACY_MODELS set.

Usage:
    python scripts/migrate_agents_model_to_deepseek.py           # dry-run (default)
    python scripts/migrate_agents_model_to_deepseek.py --apply   # actually patches
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from google.cloud import firestore

PROJECT = "coherence-ominichannel-fs"
TARGET_MODEL = "deepseek-v4-flash"
LEGACY_MODELS = [
    "minimax:MiniMax-M3",
    "MiniMax-M3",
    "MiniMax-M2.7-highspeed",
    "MiniMax-M2.7",
    "minimax",
    "minimax:MiniMax-M2.7-highspeed",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate agents model to deepseek-v4-flash")
    parser.add_argument("--apply", action="store_true", help="Apply migrations (default: dry-run)")
    args = parser.parse_args()

    db = firestore.Client(project=PROJECT)
    coll = db.collection("agents")
    print(f"Querying agents with model in {LEGACY_MODELS} ...\n")

    # `in` query supports up to 30 values — we have 6, safe.
    docs = list(coll.where("model", "in", LEGACY_MODELS).stream())
    print(f"Found {len(docs)} agents with legacy models.\n")

    if not docs:
        print("No legacy agents found. Done.")
        return 0

    if not args.apply:
        print("[DRY-RUN] Would patch the following agents:")
        for d in docs:
            data = d.to_dict() or {}
            print(f"  {d.id:30s}  model={data.get('model')!r}  -> {TARGET_MODEL}")
        print(f"\nRe-run with --apply to actually patch.")
        return 0

    # Apply
    batch = db.batch()
    now = datetime.now(timezone.utc).isoformat()
    for d in docs:
        batch.update(d.reference, {"model": TARGET_MODEL, "updated_at": now})
    batch.commit()
    print(f"[APPLIED] Patched {len(docs)} agents:\n")
    for d in docs:
        data = d.to_dict() or {}
        print(f"  {d.id:30s}  {data.get('model')!r} -> {TARGET_MODEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
