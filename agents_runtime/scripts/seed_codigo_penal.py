"""Seed public-Knowledge-Shared with Codigo Penal from PDF.
Chunk: 1000-1200 tokens (~4000-4800 chars), 15% overlap.
Embed: MiniMax (1536d) primary, NVIDIA (1024d) fallback.
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["GCP_PROJECT"] = "coherence-ominichannel-fs"
os.environ["LOG_LEVEL"] = "ERROR"

from google.cloud import firestore
from pypdf import PdfReader

# Read PDF
pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "docs", "codigo_penal_1ed.pdf")
reader = PdfReader(pdf_path)
full_text = "".join(p.extract_text() or "" for p in reader.pages)
print(f"PDF: {len(reader.pages)} pages, {len(full_text)} chars, ~{len(full_text)//4} tokens")

# Chunk with 15% overlap, 1100 token target (~4400 chars)
CHUNK_SIZE = 4400
OVERLAP = int(CHUNK_SIZE * 0.15)

chunks = []
start = 0
while start < len(full_text):
    end = min(start + CHUNK_SIZE, len(full_text))
    if end < len(full_text):
        for sep in ["\n\n", "\n", ". ", " "]:
            last = full_text.rfind(sep, start, end)
            if last > start + CHUNK_SIZE // 2:
                end = last + len(sep)
                break
    chunks.append(full_text[start:end].strip())
    start = end - OVERLAP if end < len(full_text) else end
chunks = [c for c in chunks if len(c) > 100]
print(f"Chunks: {len(chunks)}")

# Embed with MiniMax fallback NVIDIA
from core.rag import _embed_direct, _embed_nvidia

db = firestore.Client(project="coherence-ominichannel-fs")
stats = {"minimax_ok": 0, "minimax_fail": 0, "nvidia_ok": 0, "total_time": 0}

for i, chunk in enumerate(chunks):
    titulo = f"Codigo Penal - Chunk {i+1}/{len(chunks)}"
    preview = chunk[:80].replace("\n", " ")

    start = time.time()
    emb = _embed_direct(chunk)
    provider = "MiniMax"

    if emb and len(emb) > 0:
        stats["minimax_ok"] += 1
    else:
        emb = _embed_nvidia(chunk)
        provider = "NVIDIA"
        if emb and len(emb) > 0:
            stats["nvidia_ok"] += 1

    elapsed = time.time() - start
    stats["total_time"] += elapsed

    dim = len(emb) if emb else 0
    if emb:
        doc = {
            "titulo": titulo,
            "conteudo": chunk,
            "categoria": "legislacao",
            "fonte": "Codigo Penal Brasileiro - Edicao 2017",
            "embedding": emb,
            "provider": provider,
            "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
        db.collection("public-Knowledge-Shared").document(f"codigo-penal-{i+1:04d}").set(doc)

    print(f"  [{i+1:3d}/{len(chunks)}] {provider:7s} | {dim:5d}d | {elapsed:5.2f}s | {preview}")

print(f"\n=== ESTATISTICAS ===")
print(f"Chunks: {len(chunks)}")
print(f"MiniMax OK: {stats['minimax_ok']}")
print(f"MiniMax Fail (fallback NVIDIA): {stats['minimax_fail']}")
print(f"NVIDIA OK: {stats['nvidia_ok']}")
print(f"Total time: {stats['total_time']:.1f}s")
print(f"Avg time/chunk: {stats['total_time']/len(chunks):.2f}s")
print(f"Total docs indexed: {stats['minimax_ok'] + stats['nvidia_ok']}")
