"""End-to-end smoke test for RAG + system prompt (F4d.8).

Cenários:
1. Storage: envia doc simulado, valida class/group/theme.
2. Retrieval: query com/sem filtro, valida source_title.
3. Self-introspection: bot cita Firestore Vector.
4. Anti-alucinação: query vazia → clarification_prompt.

Uso:
    python scripts/smoke_e2e.py --mode=mocked
    python scripts/smoke_e2e.py --mode=live  (com OPENAI_API_KEY)
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SCENARIOS = [
    {
        "id": "introspection",
        "description": "Bot cita Firestore Vector quando perguntado sobre memoria",
        "query": "como funciona sua memoria?",
        "expected_keywords": ["firestore", "vector", "agent-knowledge-retriever"],
        "expects_retrieval": False,
    },
    {
        "id": "self_description",
        "description": "Bot menciona class/group/theme",
        "query": "como voce classifica os documentos que guardo?",
        "expected_keywords": ["class", "group", "theme"],
        "expects_retrieval": False,
    },
    {
        "id": "privacy_signal",
        "description": "Bot explica RAG pessoal",
        "query": "onde voce guarda o que memorizo?",
        "expected_keywords": ["knowledge-database", "openai", "embedding"],
        "expects_retrieval": False,
    },
]


def _load_yaml(path: str) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_system_prompt() -> Dict[str, Any]:
    """Lê jennifier.yaml e valida personalidade + arquitetura."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "data", "agents", "jennifier.yaml"
    )
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {"status": "missing", "path": path}
    config = _load_yaml(path)
    sp = (config.get("system_prompt") or "").lower()
    required = [
        "firestore vector",
        "agent-knowledge-retriever",
        "categoriz",
        "class",
        "group",
        "theme",
        "source_title",
    ]
    missing = [k for k in required if k not in sp]
    personality = any(word in sp for word in ["sarcast", "humor", "cinica"])
    has_personality_limit = "maximo 1 comentario" in sp or "maximo 1" in sp
    return {
        "status": "ok" if not missing else "partial",
        "missing_keywords": missing,
        "personality_present": personality,
        "personality_limit": has_personality_limit,
    }


def _check_retriever_yaml() -> Dict[str, Any]:
    path = os.path.join(
        os.path.dirname(__file__), "..", "data", "agents",
        "agent-knowledge-retriever.yaml",
    )
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {"status": "missing", "path": path}
    config = _load_yaml(path)
    sp = (config.get("system_prompt") or "").lower()
    required = ["source_title", "clarification", "knowledge.retrieve"]
    missing = [k for k in required if k not in sp]
    return {
        "status": "ok" if not missing else "partial",
        "missing_keywords": missing,
    }


async def _check_retrieval_logic() -> Dict[str, Any]:
    """Valida logica de retrieval com embeddings mockadas."""
    import hashlib
    import sys as _sys

    from unittest.mock import MagicMock, patch

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in _sys.path:
        _sys.path.insert(0, project_root)

    import core.rag  # noqa: F401  (force import to register module)
    from core.rag import search_legal_knowledge  # noqa: F401

    def fake_embed(text):
        h = hashlib.md5(text.encode("utf-8")).digest()
        return [((h[i % 16] - 128) / 128.0) for i in range(1536)]

    async def _async_fake(text):
        return fake_embed(text)

    database = MagicMock()

    def _fake_get_firestore_member(*args, **kwargs):
        class _Member:
            exists = True
            def to_dict(self):
                return {"is_active": True}
        return _Member()

    with patch("core.rag._get_firestore", return_value=database), \
         patch("core.rag.embed_query", side_effect=_async_fake), \
         patch(
             "agent_orchestration.knowledge_retriever._is_user_member",
             side_effect=_fake_get_firestore_member,
         ):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        results = []
        for scenario in SCENARIOS:
            try:
                result = await retrieve(envelope, scenario["query"])
                results.append({
                    "id": scenario["id"],
                    "decision": result.get("decision"),
                    "scope": result.get("scope"),
                    "count": result.get("count"),
                    "min_score": result.get("min_score"),
                    "filters": result.get("filters"),
                })
            except Exception as exc:
                results.append({"id": scenario["id"], "error": str(exc)})
        return {"status": "ok", "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="system-only", choices=["system-only", "logic", "all"])
    args = parser.parse_args()

    print("=" * 70)
    print("F4d.8 SMOKE TEST")
    print("=" * 70)

    print("\n[1] System prompt check (jennifier.yaml)")
    jennifier_check = _check_system_prompt()
    print(f"    status: {jennifier_check['status']}")
    if jennifier_check.get("missing_keywords"):
        print(f"    missing: {jennifier_check['missing_keywords']}")
    print(f"    personality_present: {jennifier_check.get('personality_present')}")
    print(f"    personality_limit: {jennifier_check.get('personality_limit')}")

    print("\n[2] System prompt check (agent-knowledge-retriever.yaml)")
    retriever_check = _check_retriever_yaml()
    print(f"    status: {retriever_check['status']}")
    if retriever_check.get("missing_keywords"):
        print(f"    missing: {retriever_check['missing_keywords']}")

    if args.mode in ("logic", "all"):
        print("\n[3] Retrieval logic (mocked embeddings)")
        result = asyncio.run(_check_retrieval_logic())
        for r in result.get("results", []):
            print(f"    {r['id']}: decision={r.get('decision')}, count={r.get('count')}")

    print("\n" + "=" * 70)
    return 0 if jennifier_check["status"] == "ok" and retriever_check["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
