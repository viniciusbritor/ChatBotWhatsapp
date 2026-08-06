"""Backfill document_title nos 151 docs existentes em knowledge-database."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys

BATCH_SIZE = 100

_FRONT_MATTER_RE = re.compile(
    r"senado federal|mesa diretora|bi[êe]nio|coordena[çc][ãa]o de edi[çc][õo]es|"
    r"secretaria de editora[çc][ãa]o|ficha catalogr[áa]fica|sum[áa]rio|"
    r"presidente|vice-presidente",
    re.IGNORECASE,
)


def _extract_title(section_titles: list, source_title: str) -> str:
    for sec in section_titles:
        sec = (sec or "").strip()
        if not _FRONT_MATTER_RE.search(sec) and len(sec) > 10:
            return sec[:120]
    base = source_title.rsplit(".", 1)[0]
    base = base.replace("_", " ").strip()
    return base[:120] if base else source_title[:120]


async def main():
    from google.cloud import firestore

    project = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
    db = firestore.Client(project=project)
    coll = db.collection("knowledge-database")

    source_titles: dict[str, list[dict]] = {}
    docs = list(coll.where("scope", "==", "private").stream())
    for doc in docs:
        data = doc.to_dict() or {}
        src = data.get("source_title", "")
        if src not in source_titles:
            source_titles[src] = []
        source_titles[src].append(
            {"id": doc.id, "section_title": data.get("section_title", "")}
        )

    updated = 0
    for src, entries in source_titles.items():
        sections = list(set(e["section_title"] for e in entries if e["section_title"]))
        doc_title = _extract_title(sections, src)
        print(f"  {src[:50]:50s} -> {doc_title[:80]}")

        batch = db.batch()
        batch_count = 0
        for entry in entries:
            batch.update(coll.document(entry["id"]), {"document_title": doc_title})
            batch_count += 1
            if batch_count >= BATCH_SIZE:
                await asyncio.to_thread(batch.commit)
                updated += batch_count
                batch = db.batch()
                batch_count = 0

        if batch_count > 0:
            await asyncio.to_thread(batch.commit)
            updated += batch_count

    print(f"\nTotal: {updated} docs atualizados em {len(source_titles)} documentos")


if __name__ == "__main__":
    asyncio.run(main())
