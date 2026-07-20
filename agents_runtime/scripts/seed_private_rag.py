import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

from core.rag import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    PRIVATE_COLLECTION,
    SCHEMA_VERSION,
    _owner_hash,
    _get_firestore,
    embed_query,
)
from google.cloud.firestore_v1.vector import Vector
from core.masker import mask_pii

BRT = timezone(timedelta(hours=-3))


DEFAULT_DOCS = [
    {
        "source_title": "Contatos frequentes",
        "category": "contacts",
        "text_content": (
            "O usuario costuma falar com: Vinicius (owner), "
            "familia, amigos do trabalho e contatos profissionais. "
            "Estilo de comunicacao preferido: direto, caloroso, em portugues brasileiro."
        ),
    },
    {
        "source_title": "Preferencias e contexto pessoal",
        "category": "preferences",
        "text_content": (
            "Horarios tipicos de mensagem: 8h-22h BRT. "
            "Topicos recorrentes: agenda, projetos de IA, infraestrutura, financas pessoais. "
            "Eventos importantes: reunioes, pagamentos, voos."
        ),
    },
    {
        "source_title": "Historico de decisoes",
        "category": "decisions",
        "text_content": (
            "Decisoes recentes: adotar OpenAI text-embedding-3-small para RAG, "
            "manter Whisper local para STT, configurar Pub/Sub para mensagens WhatsApp. "
            "Plano: implementar A+B+C em test antes de promover a main."
        ),
    },
]


def _hash_id(owner: str, source_title: str, index: int) -> str:
    import hashlib

    return hashlib.sha256(f"{owner}:{source_title}:{index}".encode("utf-8")).hexdigest()[:32]


def seed_for_phone(phone: str, docs=DEFAULT_DOCS, dry_run: bool = False):
    owner = _owner_hash(phone)
    db = _get_firestore()
    if db is None:
        print(f"[{phone}] firestore unavailable")
        return 0
    now = datetime.now(BRT).isoformat()
    written = 0
    for index, doc in enumerate(docs):
        text = mask_pii(doc["text_content"])
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            embedding = loop.run_until_complete(embed_query(text))
        else:
            embedding = asyncio.run(embed_query(text))
        if embedding is None:
            print(f"[{phone}] embed failed for '{doc['source_title']}'")
            continue
        if dry_run:
            written += 1
            continue
        document_id = _hash_id(owner, doc["source_title"], index)
        reference = db.collection(PRIVATE_COLLECTION).document(document_id)
        reference.set({
            "owner_hash": owner,
            "text_content": text,
            "vector_embedding": Vector(embedding),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
            "schema_version": SCHEMA_VERSION,
            "source_title": doc["source_title"],
            "category": doc["category"],
            "language": "pt-BR",
            "created_at": now,
        })
        written += 1
    print(f"[{phone}] wrote {written} docs (owner_hash={owner[:8]}...)")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="Master phone in digits only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    count = seed_for_phone(args.phone, dry_run=args.dry_run)
    print(f"Total: {count} documents {'(dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
