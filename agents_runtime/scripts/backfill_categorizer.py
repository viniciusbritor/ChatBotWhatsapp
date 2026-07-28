"""Backfill categorizer metadata for existing documents in agent-knowledge-v2.

Idempotent: only updates docs that do not yet have `class` set.
Run via: python scripts/backfill_categorizer.py
"""
import asyncio
import hashlib
import logging
import os
import sys
from collections import defaultdict
from typing import Any, Dict

PROJECT = "coherence-ominichannel-fs"
BATCH_SIZE = 100


def _owner_hash(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()[:32]


async def _categorize_one(text: str, source_name: str) -> Dict[str, Any]:
    from agent_orchestration.categorizer import categorize

    return await categorize(text, source_name)


async def main_async(target_hash: str | None) -> None:
    from google.cloud import firestore

    db = firestore.Client(project=PROJECT)
    coll = db.collection("agent-knowledge-v2")

    docs = list(coll.limit(2000).stream())
    if target_hash:
        docs = [d for d in docs if d.to_dict().get("owner_hash") == target_hash]

    by_source: Dict[str, list] = defaultdict(list)
    for d in docs:
        data = d.to_dict()
        src = data.get("source_title", "?")
        if data.get("class"):
            continue
        by_source[src].append(d)

    if not by_source:
        print("Nothing to backfill: all docs already have class metadata.")
        return

    print(f"Backfilling {len(by_source)} sources: {list(by_source.keys())}")
    for source_name, doc_list in by_source.items():
        sample_text = (doc_list[0].to_dict().get("text_content") or "")[:2500]
        category = await _categorize_one(sample_text, source_name)
        print(f"  {source_name}: class={category.get('class')}, group={category.get('group')}, theme={category.get('theme')[:60]}")
        for doc in doc_list:
            doc.reference.update({
                "class": category.get("class"),
                "group": category.get("group"),
                "theme": category.get("theme"),
            })


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-hash", default="afafa878e52e6cdc486ab42168e753a4")
    args = parser.parse_args()
    asyncio.run(main_async(args.owner_hash))


if __name__ == "__main__":
    main()