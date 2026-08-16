"""Audit Firestore database location for BR-foco compliance.

O projeto usa Firestore collection-group queries + vector search. A latencia
de leitura/escrita depende da REGION do database. Para usuarios 100% BR,
a region deve ser southamerica-east1 (Sao Paulo).

Este script le a location do database Firestore e gera um relatorio
Markdown pronto para colar em PR. NAO altera nada.

Uso:
    python scripts/audit_firestore_location.py
    python scripts/audit_firestore_location.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BRT = timezone(__import__("datetime").timedelta(hours=-3))


def run_gcloud(args: list[str]) -> tuple[int, str, str]:
    """Run gcloud command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["gcloud"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "gcloud CLI not found"
    except subprocess.TimeoutExpired:
        return 1, "", "gcloud timeout"


def get_database_info(project: str, database: str) -> dict | None:
    """Get Firestore database info."""
    code, stdout, stderr = run_gcloud([
        "firestore", "databases", "describe", database,
        f"--project={project}",
        "--format=json",
    ])
    if code != 0:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def get_collections_sample(project: str, database: str) -> list[str]:
    """List first 20 collections."""
    code, stdout, stderr = run_gcloud([
        "firestore", "databases", "collections", "list", database,
        f"--project={project}",
        "--format=value(name)",
        "--limit=20",
    ])
    if code != 0:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit Firestore location")
    parser.add_argument("--project", default="coherence-ominichannel-fs", help="GCP project")
    parser.add_argument("--database", default="(default)", help="Firestore database ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv if argv is not None else [])

    db_info = get_database_info(args.project, args.database)
    if db_info is None:
        print("ERROR: Could not fetch Firestore database info.")
        print("Run: gcloud auth login && gcloud config set project " + args.project)
        return 1

    location = db_info.get("locationId", "unknown")
    type_ = db_info.get("type", "unknown")
    etag = db_info.get("etag", "unknown")
    create_time = db_info.get("createTime", "unknown")
    collections = get_collections_sample(args.project, args.database)

    # Determine BR-compliance
    is_br = location in ("southamerica-east1", "nam5-eur3")  # multi-region with BR region
    br_compliant = location == "southamerica-east1"
    verdict = (
        "✅ BR-COMPLIANT (southamerica-east1)"
        if br_compliant
        else f"⚠️  NAO-BR (location: {location})"
    )

    report = {
        "generated_at": datetime.now(BRT).isoformat(),
        "project": args.project,
        "database": args.database,
        "location_id": location,
        "type": type_,
        "etag": etag,
        "create_time": create_time,
        "br_compliant": br_compliant,
        "verdict": verdict,
        "collections_sample": collections,
        "recommendation": _recommend(location, is_br),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print("FIRESTORE LOCATION AUDIT")
        print("=" * 70)
        print(f"Project:       {args.project}")
        print(f"Database:      {args.database}")
        print(f"Location:      {location}")
        print(f"Type:          {type_}")
        print(f"Created:       {create_time}")
        print(f"Verdict:       {verdict}")
        print()
        print(f"Collections (sample): {len(collections)}")
        for c in collections[:10]:
            print(f"  - {c}")
        if len(collections) > 10:
            print(f"  ... +{len(collections) - 10} more")
        print()
        print(f"Recommendation: {report['recommendation']}")
        print("=" * 70)

    return 0 if br_compliant else 2


def _recommend(location: str, is_br: bool) -> str:
    if is_br:
        return "OK — single-region southamerica-east1. Latencia < 50ms para users BR."
    if location == "nam5":
        return "Multi-region US (nam5). Migrar para single-region southamerica-east1 para users BR (-150ms)."
    if location == "eur3":
        return "Multi-region EU. NAO ideal para users BR. Migrar para southamerica-east1."
    return f"Location '{location}' desconhecida. Avaliar impacto e considerar southamerica-east1."


if __name__ == "__main__":
    sys.exit(main())
