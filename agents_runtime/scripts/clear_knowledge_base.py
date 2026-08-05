"""Limpa TODAS as collections de conhecimento do owner no Firestore Vector (batch)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")


async def main():
    from core.rag import (
        PRIVATE_COLLECTION,
        SECTIONS_COLLECTION,
        _get_firestore,
        _owner_hash,
    )

    phone = sys.argv[1] if len(sys.argv) > 1 else "5511966830020"
    db = _get_firestore()
    if db is None:
        print("firestore unavailable")
        return
    owner_hash = _owner_hash(phone)
    print(f"owner_hash={owner_hash} phone={phone}")

    collections = [
        PRIVATE_COLLECTION,
        PRIVATE_COLLECTION + "-plain",
        SECTIONS_COLLECTION,
    ]
    for coll in collections:
        docs = list(
            db.collection(coll).where("owner_hash", "==", owner_hash).stream()
        )
        print(f"  {coll}: {len(docs)} docs")
        # delete em lotes de 100 (batch max 500 ops)
        for i in range(0, len(docs), 100):
            batch = db.batch()
            for d in docs[i:i + 100]:
                batch.delete(d.reference)
            await asyncio.to_thread(batch.commit)
        print(f"  -> {coll} limpo")

    print("done")


if __name__ == "__main__":
    asyncio.run(main())
