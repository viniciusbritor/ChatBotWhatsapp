"""Backfill document_title usando _extract_document_title do core/rag.py."""
from __future__ import annotations

import asyncio
import os

BATCH_SIZE = 100


async def main():
    from google.cloud import firestore
    from core.rag import _extract_document_title

    project = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
    db = firestore.Client(project=project)
    coll = db.collection("knowledge-database")

    source_data: dict[str, dict] = {}
    docs = list(coll.where("scope", "==", "private").stream())
    for doc in docs:
        data = doc.to_dict() or {}
        src = data.get("source_title", "")
        if src not in source_data:
            source_data[src] = {"ids": [], "sections": []}
        source_data[src]["ids"].append(doc.id)
        sec = data.get("section_title", "")
        if sec:
            source_data[src]["sections"].append(sec)

    updated = 0
    for src, entry in source_data.items():
        sections = list(set(entry["sections"]))
        doc_title = _extract_document_title(sections, src)
        print(f"  {src[:50]:50s} -> {doc_title[:100]}")

        batch = db.batch()
        batch_count = 0
        for doc_id in entry["ids"]:
            batch.update(coll.document(doc_id), {"document_title": doc_title})
            batch_count += 1
            if batch_count >= BATCH_SIZE:
                await asyncio.to_thread(batch.commit)
                updated += batch_count
                batch = db.batch()
                batch_count = 0

        if batch_count > 0:
            await asyncio.to_thread(batch.commit)
            updated += batch_count

    print(f"\nTotal: {updated} docs em {len(source_data)} documentos")


if __name__ == "__main__":
    asyncio.run(main())
