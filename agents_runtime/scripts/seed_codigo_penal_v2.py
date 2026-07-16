"""Seed Codigo Penal with NVIDIA embeddings (512 token limit, ~2000 char chunks)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["GCP_PROJECT"] = "coherence-ominichannel-fs"
os.environ["LOG_LEVEL"] = "ERROR"

from google.cloud import firestore
from pypdf import PdfReader
from core.secrets import get_secret

# Read PDF
pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "docs", "codigo_penal_1ed.pdf")
reader = PdfReader(pdf_path)
full_text = "".join(p.extract_text() or "" for p in reader.pages)
print(f"PDF: {len(reader.pages)} pages, {len(full_text)} chars")

# Chunk small: 2000 chars (~500 tokens, fits NVIDIA 512 limit), 15% overlap
CHUNK_SIZE = 2000
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
chunks = [c for c in chunks if len(c) > 50]
print(f"Chunks: {len(chunks)}")

# Embed with NVIDIA
import requests
api_key = os.environ.get("NVIDIA_API_KEY") or get_secret("NVIDIA_API_KEY")
api_key = api_key.strip().lstrip("\ufeff")
print(f"API Key: {'SET' if api_key else 'MISSING'}")

db = firestore.Client(project="coherence-ominichannel-fs")
ok = 0
fail = 0
total_time = 0

for i, chunk in enumerate(chunks):
    titulo = f"Codigo Penal - Artigos {i+1}"
    preview = chunk[:80].replace("\n", " ")

    start = time.time()
    resp = requests.post("https://integrate.api.nvidia.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": [chunk[:1900]], "model": "nvidia/nv-embedqa-e5-v5", "input_type": "passage", "encoding_format": "float"},
        timeout=15)
    elapsed = time.time() - start
    total_time += elapsed

    if resp.status_code == 200 and "data" in resp.json():
        emb = resp.json()["data"][0]["embedding"]
        db.collection("public-Knowledge-Shared").document(f"codigo-penal-{i+1:04d}").set({
            "titulo": titulo, "conteudo": chunk, "categoria": "legislacao",
            "fonte": "Codigo Penal Brasileiro - Edicao 2017",
            "embedding": emb, "provider": "NVIDIA",
            "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        })
        ok += 1
        print(f"  [{i+1:4d}/{len(chunks)}] OK {len(emb):4d}d {elapsed:5.2f}s | {preview}")
    else:
        fail += 1
        err = resp.json().get("error", resp.text[:60]) if resp.status_code != 200 else "unknown"
        print(f"  [{i+1:4d}/{len(chunks)}] FAIL {elapsed:5.2f}s | {err}")

print(f"\n=== ESTATISTICAS ===")
print(f"Chunks: {len(chunks)}")
print(f"OK: {ok} | Fail: {fail}")
print(f"Total time: {total_time:.1f}s | Avg: {total_time/max(ok,1):.2f}s/chunk")
print(f"Dim: 1024d (NVIDIA nv-embedqa-e5-v5)")
print(f"Custo: GRATUITO (NIM free tier)")
print(f"Total docs: {ok} no public-Knowledge-Shared")
