"""Popula agent-knowledge-sections agrupando chunks do plain por source_title.

Cada documento (source_title) tem varios chunks no plain collection.
Este script junta todos os chunks de um documento na ordem correta,
detecta secoes e indexa cada secao completa em agent-knowledge-sections.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("populate_sections")


async def main():
    from core.rag import (
        PRIVATE_COLLECTION,
        _get_firestore,
        _owner_hash,
        index_private_sections,
        clean_portuguese,
    )

    phone = sys.argv[1] if len(sys.argv) > 1 else "5511966830020"
    db = _get_firestore()
    if db is None:
        logger.error("firestore unavailable")
        return
    owner_hash = _owner_hash(phone)
    logger.info("phone=%s owner_hash=%s", phone, owner_hash)

    docs = list(
        db.collection(PRIVATE_COLLECTION + "-plain")
        .where("owner_hash", "==", owner_hash)
        .stream()
    )
    logger.info("plain chunks: %d", len(docs))

    from collections import defaultdict
    docs_by_source = defaultdict(list)
    for d in docs:
        data = d.to_dict() or {}
        src = data.get("source_title", "")
        idx = int(data.get("chunk_index", 0))
        docs_by_source[src].append((idx, data.get("text_content", "")))

    for src, items in docs_by_source.items():
        items.sort(key=lambda x: x[0])
        full_text = "\n\n".join(t for _, t in items if t.strip())
        logger.info("source=%s chunks=%d total_chars=%d", src, len(items), len(full_text))
        if len(full_text) < 1000:
            continue
        result = await index_private_sections(
            phone=phone,
            text_content=full_text,
            source_title=src,
            class_="",
            group="",
            theme="",
        )
        logger.info("  sections result=%s", result.get("status"))

    logger.info("done")


if __name__ == "__main__":
    asyncio.run(main())
