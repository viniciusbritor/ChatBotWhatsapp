"""Smoke test with mocked embeddings (no API key required).

Verifies:
1. Retriever with class/group/source_title filters.
2. Score threshold filtering.
3. Clarification prompt.
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

PROJECT = "coherence-ominichannel-fs"
PHONE = "5511966830020"


async def main_async() -> None:
    from unittest.mock import patch

    # Mock OpenAI embedding to return a deterministic vector based on text length
    async def fake_embed(text):
        # Use a stable hash to make embeddings somewhat meaningful
        import hashlib
        h = hashlib.md5(text.encode("utf-8")).digest()
        vec = [((h[i % 16] - 128) / 128.0) for i in range(1536)]
        return vec

    with patch("core.rag.embed_query", side_effect=fake_embed), patch("core.rag.embed_documents", side_effect=lambda texts: asyncio.gather(*[fake_embed(t) for t in texts]) if texts else []):
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
            print(f"\n=== Query: '{query}' (source_hint={source_hint}) ===")
            result = await retrieve(envelope, query)
            print(f"  decision: {result.get('decision')}")
            print(f"  scope: {result.get('scope')}")
            print(f"  count: {result.get('count')}")
            print(f"  min_score: {result.get('min_score')}")
            print(f"  filters: {result.get('filters')}")
            if result.get("clarification_prompt"):
                print(f"  clarification: {result.get('clarification_prompt')[:100]}")
            for chunk in result.get("results", [])[:3]:
                print(f"    chunk: source={chunk.get('source', '?')[:30]}... class={chunk.get('class', '?')} group={chunk.get('group', '?')} score={chunk.get('score', 0):.2f}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
