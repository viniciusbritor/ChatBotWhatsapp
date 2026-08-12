"""Cleanup one-off: converte/deleta docs legacy de message-history.

Antes do R2 (12/08/2026), o campo ``expires_at`` era gravado como string ISO.
A Firestore TTL policy exige campo do tipo Timestamp. Este script:
1. Atualiza docs antigos (expires_at string) para o campo datetime
   equivalente (Timestamp), preservando o TTL.
2. Opcionalmente deleta docs ja vencidos.

Uso:
    python -m scripts.cleanup_legacy_expires --dry-run
    python -m scripts.cleanup_legacy_expires --apply
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="nao altera nada")
    parser.add_argument("--apply", action="store_true", help="aplica mudancas")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("informe --dry-run ou --apply")

    project = os.getenv("GCP_PROJECT") or "coherence-ominichannel-fs"
    db = firestore.Client(project=project)
    coll = db.collection("message-history")
    now = datetime.now().astimezone()

    converted = 0
    deleted = 0
    scanned = 0
    for doc in coll.stream():
        data = doc.to_dict() or {}
        scanned += 1
        expires = data.get("expires_at")
        # Se ja for Timestamp (datetime), ok
        if isinstance(expires, datetime):
            continue
        if isinstance(expires, str):
            try:
                ts = datetime.fromisoformat(expires)
            except ValueError:
                continue
            # Vencido -> deletar
            if ts <= now:
                deleted += 1
                if args.apply:
                    doc.reference.delete()
                continue
            # Nao vencido -> converter para Timestamp
            converted += 1
            if args.apply:
                doc.reference.update({"expires_at": ts})
    print(
        f"message-history: scanned={scanned} converted={converted} deleted={deleted} "
        f"mode={'dry-run' if args.dry_run else 'apply'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
