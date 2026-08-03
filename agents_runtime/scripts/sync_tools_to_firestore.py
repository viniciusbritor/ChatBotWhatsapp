"""Sincroniza tools do tool_registry.py para Firestore.

O bot le tools do Firestore (collection 'tools') via agent_loader.py
tools_cache. Se o cache nao tem 'gmail.search_messages' ou 'drive.search_files',
o bot NAO pode chamar essas tools (mesmo que tool_registry.py as defina).

Este script le tool_registry.py::TOOL_REGISTRY e faz upsert no Firestore
para todas as tools que estao no codigo mas faltam no Firestore.

Uso:
  python scripts/sync_tools_to_firestore.py
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "coherence-ominichannel-fs")

from google.cloud import firestore


def main() -> int:
    # Lazy import para evitar erro se modulo nao disponivel
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    try:
        from tool_registry import TOOL_REGISTRY, get_tool_schema
    except ImportError as e:
        print(f"[ERRO] tool_registry nao importado: {e}")
        return 1

    db = firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])

    synced = 0
    _ = 0
    failed = 0

    for tool_id, entry in TOOL_REGISTRY.items():
        try:
            schema = get_tool_schema(tool_id) or {}
            data: Dict[str, Any] = {
                "name": tool_id,
                "description": schema.get("description", ""),
                "parameters": schema.get("parameters", {}),
                "scopes": list(entry.get("scopes", [])) if isinstance(entry, dict) else [],
                "user_scoped": entry.get("user_scoped", False) if isinstance(entry, dict) else False,
                "synced_at": firestore.SERVER_TIMESTAMP,
            }
            doc_ref = db.collection("tools").document(tool_id)
            doc = doc_ref.get()
            if doc.exists:
                doc_ref.update(data)
            else:
                doc_ref.set(data)
            synced += 1
        except Exception as exc:
            print(f"[FAIL] {tool_id}: {exc}")
            failed += 1

    print(f"Sincronizadas: {synced}")
    print(f"Falharam: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
