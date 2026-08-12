"""Backfill do indice inverso usuarios/{phone}.group_memberships.

Varre ``group_members/*`` (snapshot forward) e reconstroi a relacao inversa
membro->grupos em ``usuarios/{phone}.group_memberships``. Idempotente: usa
``set(merge=True)`` e nunca sobrescreve google_oauth_token/email/role do doc
do usuario.

Uso::

    python scripts/backfill_group_memberships.py --dry-run
    python scripts/backfill_group_memberships.py

Parametros opcionais:

* ``--max-docs`` (default ``0`` = sem limite) — limite de seguranca.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.cloud import firestore  # type: ignore  # noqa: E402

from agent_loader import _canonical_phone  # noqa: E402

logger = logging.getLogger("backfill_group_memberships")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _get_firestore():
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
        return None
    return firestore.Client(project=project)


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _process(db, *, max_docs: int, dry_run: bool) -> dict:
    memberships: dict[str, list] = {}
    scanned = 0
    for doc in db.collection("group_members").stream():
        scanned += 1
        if max_docs and scanned > max_docs:
            break
        data = doc.to_dict() or {}
        gid = data.get("group_jid") or doc.id
        subject = data.get("subject") or ""
        for phone in data.get("member_phones") or []:
            if not phone:
                continue
            memberships.setdefault(str(phone), []).append({"gid": gid, "subject": subject})

    updated = skipped = errors = 0
    for phone, entries in memberships.items():
        canonical = _canonical_phone(phone) or phone
        if not canonical:
            skipped += 1
            continue
        try:
            if dry_run:
                updated += 1
                continue
            db.collection("usuarios").document(canonical).set(
                {
                    "group_memberships": entries,
                    "group_memberships_updated_at": _now_iso(),
                },
                merge=True,
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("membership %s error: %s", canonical, exc)
            errors += 1

    return {
        "group_docs_scanned": scanned,
        "distinct_members": len(memberships),
        "memberships_written": updated,
        "skipped": skipped,
        "errors": errors,
    }


def _run(args) -> int:
    db = _get_firestore()
    if db is None:
        logger.error("firestore not configured (set GCP_PROJECT e desabilite FIRESTORE_EMULATOR_HOST)")
        return 1
    started = time.monotonic()
    result = _process(db, max_docs=args.max_docs, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info("summary dry_run=%s elapsed_sec=%.1f result=%s", args.dry_run, elapsed, result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill do indice inverso group_memberships")
    parser.add_argument("--max-docs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
