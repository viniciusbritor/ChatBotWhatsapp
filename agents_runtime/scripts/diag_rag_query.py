"""Diagnostic script for the RAG retrieval pipeline.

READ-ONLY. Roda `search_legal_knowledge` contra o Firestore real do
projeto `coherence-ominichannel-fs` com `min_score=0.0` (forca
retorno de TODOS os candidatos) e mostra score, source_title e
snippet do top-k. Use este script para diagnosticar por que uma
determinada query RAG retornou "nao encontrei nada".

Cenario de uso:
    python -m scripts.diag_rag_query --phone 5511966830020 --query "cdc"
    python -m scripts.diag_rag_query --phone 5511966830020 --all-docs
    python -m scripts.diag_rag_query --phone 5511966830020 \
        --query "edital" --adaptive

Com `--adaptive` (default), o score e exibido junto do
``min_score`` e do ``ADAPTIVE_FLOOR=0.3`` que o codigo de producao
usa como fallback. Tudo o que estiver entre o floor e o min_score
e entregue com warning estruturado (`retrieval_low_confidence`).

Pre-requisitos:
    gcloud auth application-default login
    export GCP_PROJECT=coherence-ominichannel-fs
    OPENAI_API_KEY no Secret Manager (carregado pelo core.secrets)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from typing import Any, Dict, List, Optional


def _owner_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()[:32]


async def _list_docs(phone: str) -> List[Dict[str, Any]]:
    from core.rag import PRIVATE_COLLECTION, _get_firestore, _owner_hash

    db = _get_firestore()
    if db is None:
        return []

    owner_hash = _owner_hash(phone)

    def fetch():
        return list(
            db.collection(PRIVATE_COLLECTION)
            .where("owner_hash", "==", owner_hash)
            .limit(200)
            .stream()
        )

    docs = await asyncio.to_thread(fetch)
    out = []
    for d in docs:
        data = d.to_dict() or {}
        out.append(
            {
                "doc_id": d.id,
                "source_title": data.get("source_title", ""),
                "chunk_index": data.get("chunk_index"),
                "class": data.get("class", ""),
                "group": data.get("group", ""),
                "theme": data.get("theme", ""),
                "embedding_dim": data.get("embedding_dim"),
                "embedding_model": data.get("embedding_model", ""),
                "schema_version": data.get("schema_version"),
                "text_len": len(data.get("text_content", "") or ""),
                "snippet": (data.get("text_content", "") or "")[:80],
            }
        )
    return out


async def _query(phone: str, query: str, k: int, min_score: float) -> Dict[str, Any]:
    from core.rag import search_legal_knowledge

    return await search_legal_knowledge(
        phone=phone, query=query, k=k, min_score=min_score
    )


async def main_async(args: argparse.Namespace) -> int:
    phone = args.phone

    if args.all_docs or args.query is None:
        print(f"[diag] listando docs de owner_hash={_owner_hash(phone)}")
        docs = await _list_docs(phone)
        if not docs:
            print("[diag] 0 documentos encontrados para este owner_hash.")
            return 1
        by_source: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            by_source.setdefault(d["source_title"] or "(sem titulo)", []).append(d)
        for title, items in sorted(by_source.items()):
            chunks = ", ".join(str(c["chunk_index"]) for c in items)
            klass = items[0].get("class") or "?"
            group = items[0].get("group") or "?"
            theme = items[0].get("theme") or "?"
            print(
                f"  - {title!r:35} chunks=[{chunks}] "
                f"class={klass} group={group} theme={theme}"
            )
        print(f"[diag] total: {len(docs)} docs em {len(by_source)} fontes")
        if args.query is None:
            return 0

    query = args.query
    print(f"\n[diag] query={query!r} (k={args.k}, min_score={args.min_score})")
    result = await _query(phone, query, args.k, args.min_score)

    top_score = result.get("top_score", 0.0)
    adaptive_floor = result.get("adaptive_floor", 0.3)
    print(
        f"[diag] top_score={top_score} min_score={result.get('min_score')} "
        f"adaptive_floor={adaptive_floor}"
    )

    results = result.get("results", [])
    err = result.get("error")
    if err:
        print(f"[diag] erro: {err}")
    if not results:
        print(
            "[diag] 0 resultados. Verifique se a query embedda bate com "
            "o schema (dimension + model) dos docs e se o owner_hash esta "
            "correto."
        )
        return 2
    for i, c in enumerate(results):
        sc = c.get("score", 0)
        src = c.get("source", "?")
        tx = c.get("text", "")[:120].replace("\n", " ")
        flag = ""
        if args.adaptive and sc < (result.get("min_score") or 0.7):
            flag = "  [adaptive: entregue abaixo do min_score]"
        print(f"  [{i}] score={sc:.3f} source={src!r}{flag}")
        print(f"        text={tx!r}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Diagnostic script para retrieval RAG no Firestore Vector."
    )
    p.add_argument("--phone", default="5511966830020")
    p.add_argument(
        "--query",
        help='Query RAG. Omite + usa "--all-docs" para listar inventario.',
    )
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument(
        "--adaptive",
        action="store_true",
        help="Destaca matches entregues abaixo do min_score via adaptive floor.",
    )
    p.add_argument(
        "--all-docs",
        action="store_true",
        help="Lista todos os docs do owner (inventario) antes de query.",
    )
    args = p.parse_args(argv)

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
