"""Seed Codigo Penal - NVIDIA embeddings, 1200 char chunks (fits 512 token limit)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["GCP_PROJECT"] = "coherence-ominichannel-fs"
os.environ["LOG_LEVEL"] = "ERROR"

from google.cloud import firestore
from pypdf import PdfReader
from core.secrets import get_secret
import requests

pdf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "docs", "codigo_penal_1ed.pdf")
reader = PdfReader(pdf_path)
full_text = "".join(p.extract_text() or "" for p in reader.pages)
print(f"PDF: {len(reader.pages)} pages, {len(full_text)} chars")

CHUNK_SIZE = 1200
OVERLAP = 180
chunks = []
start = 0
while start < len(full_text):
    end = min(start + CHUNK_SIZE, len(full_text))
    if end < len(full_text):
        for sep in ["\n\n", "\n", ". "]:
            last = full_text.rfind(sep, start, end)
            if last > start + CHUNK_SIZE // 2:
                end = last + len(sep)
                break
    chunks.append(full_text[start:end].strip())
    start = end - OVERLAP if end < len(full_text) else end
chunks = [c for c in chunks if len(c) > 50]
print(f"Chunks: {len(chunks)}")

api_key = os.environ.get("NVIDIA_API_KEY") or get_secret("NVIDIA_API_KEY")
api_key = api_key.strip().lstrip("\ufeff")

db = firestore.Client(project="coherence-ominichannel-fs")
ok = fail = 0
total_time = 0
first_ok = None

for i, chunk in enumerate(chunks):
    preview = chunk[:80].replace("\n", " ")
    text = chunk[:1200]

    start = time.time()
    resp = requests.post("https://integrate.api.nvidia.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": [text], "model": "nvidia/nv-embedqa-e5-v5", "input_type": "passage", "encoding_format": "float"},
        timeout=15)
    elapsed = time.time() - start
    total_time += elapsed

    if resp.status_code == 200 and "data" in resp.json():
        emb = resp.json()["data"][0]["embedding"]
        if not first_ok:
            first_ok = {"dim": len(emb), "time": elapsed}
        db.collection("public-Knowledge-Shared").document(f"codigo-penal-{i+1:04d}").set({
            "titulo": f"Codigo Penal - Artigos {i+1}",
            "conteudo": chunk,
            "categoria": "legislacao",
            "fonte": "Codigo Penal Brasileiro - Edicao 2017",
            "embedding": emb,
            "provider": "NVIDIA",
            "dim": 1024,
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        })
        ok += 1
        if ok % 15 == 0:
            print(f"  [{i+1:4d}/{len(chunks)}] {ok} OK, {fail} fail | {preview}")
    else:
        fail += 1
        err = resp.json().get("error", str(resp.status_code))
        print(f"  [{i+1:4d}/{len(chunks)}] FAIL | {err[:60]}")

print(f"\n=== ESTATISTICAS ===")
print(f"Chunks: {len(chunks)} | OK: {ok} | Fail: {fail}")
print(f"Total time: {total_time:.1f}s | Avg: {total_time/max(ok,1):.2f}s/chunk")
print(f"Provider: NVIDIA nv-embedqa-e5-v5 | Dim: 1024d")
print(f"Custo: GRATUITO (NIM free tier)")
print(f"Collection: public-Knowledge-Shared | Docs: {ok}")
if first_ok:
    print(f"First embed: {first_ok['dim']}d, {first_ok['time']:.2f}s")
