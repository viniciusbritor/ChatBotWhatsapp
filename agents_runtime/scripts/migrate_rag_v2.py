import argparse
import asyncio
import os
import sys

from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag import EMBEDDING_DIM, EMBEDDING_MODEL, SHARED_COLLECTION, _chunk_text, index_shared_document


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..",
            "docs",
            "codigo_penal_1ed.pdf",
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def migrate(pdf_path: str, dry_run: bool = False):
    reader = PdfReader(pdf_path)
    text = "".join(page.extract_text() or "" for page in reader.pages)
    chunks = [chunk for chunk in _chunk_text(text) if len(chunk) > 50]
    result = {
        "collection": SHARED_COLLECTION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "pages": len(reader.pages),
        "chunks": len(chunks),
        "indexed": 0,
        "failed": 0,
    }
    if dry_run:
        return result
    for index, chunk in enumerate(chunks, start=1):
        try:
            await index_shared_document(
                titulo=f"Codigo Penal - Trecho {index}",
                conteudo=chunk,
                categoria="legislacao",
                fonte="Codigo Penal Brasileiro - Edicao 2017",
            )
            result["indexed"] += 1
        except Exception:
            result["failed"] += 1
    return result


def main():
    args = parse_args()
    result = asyncio.run(migrate(args.pdf, args.dry_run))
    for key, value in result.items():
        print(f"{key}: {value}")
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
