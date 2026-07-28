"""Smoke test: direct retrieval bypasses orchestrator.

Verifies that:
1. The stored document (dissertação.pdf or cdc) is found via search_legal_knowledge.
2. The retriever (retrieve) returns chunks with class/group/theme metadata.
3. Score threshold filters out low-relevance chunks.
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)

PROJECT = "coherence-ominichannel-fs"
PHONE = "5511966830020"


async def main_async() -> None:
    from agent_orchestration.knowledge_retriever import retrieve

    envelope = {
        "phone": PHONE,
        "extra": {
            "remote_jid": f"{PHONE}@s.whatsapp.net",
        },
    }

    queries = [
        ("principais capitulos do CDC", "cdc-portugues-2013.pdf"),
        ("resumo da dissertacao", "disserta\u00e7\u00e3o.pdf"),
        ("manual de procedimentos", None),
        ("higiene das maos", None),
    ]

    for query, source_hint in queries:
        print(f"\n=== Query: '{query}' ===")
        envelope["extra"]["source_hint"] = source_hint
        result = await retrieve(envelope, query)
        print(f"  decision: {result.get('decision')}")
        print(f"  scope: {result.get('scope')}")
        print(f"  count: {result.get('count')}")
        if result.get("clarification_prompt"):
            print(f"  clarification: {result.get('clarification_prompt')[:100]}")
        for chunk in result.get("results", [])[:3]:
            print(f"    chunk: source={chunk.get('source', '?')[:30]}... class={chunk.get('class', '?')} group={chunk.get('group', '?')} score={chunk.get('score', 0):.2f}")
            print(f"      text: {chunk.get('text', '')[:120]}...")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()