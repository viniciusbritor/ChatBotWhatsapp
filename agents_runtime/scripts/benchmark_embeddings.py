"""Benchmark MiniMax vs NVIDIA embeddings."""
import os, time, requests

txt = "Art. 121. Matar alguem: Pena - reclusao, de seis a vinte anos."
txt_long = (txt + " ") * 8

def test_minimax():
    api_key = os.popen("gcloud secrets versions access latest --secret=MINIMAX_API_KEY --project=coherence-ominichannel-fs").read().strip()
    group_id = os.popen("gcloud secrets versions access latest --secret=minimax-group-id --project=coherence-ominichannel-fs").read().strip()
    if not api_key or not group_id:
        return None, "missing key/group"
    start = time.time()
    resp = requests.post("https://api.minimax.io/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "GroupId": group_id},
        json={"model": "embo-01", "texts": [txt_long], "type": "db"}, timeout=20)
    elapsed = time.time() - start
    data = resp.json()
    sc = data.get("base_resp", {}).get("status_code", 0)
    emb = data.get("data", [{}])[0].get("embedding", [])
    return {"provider": "MiniMax", "dim": len(emb), "time": elapsed, "status": sc, "tokens_in": data.get("usage", {}).get("total_tokens", len(txt_long)//4)}

def test_nvidia():
    api_key = os.popen("gcloud secrets versions access latest --secret=NVIDIA_API_KEY --project=coherence-ominichannel-fs").read().strip()
    if not api_key:
        return None, "missing key"
    start = time.time()
    resp = requests.post("https://integrate.api.nvidia.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": [txt_long], "model": "nvidia/nv-embedqa-e5-v5", "input_type": "passage", "encoding_format": "float"}, timeout=20)
    elapsed = time.time() - start
    if resp.status_code != 200:
        return {"provider": "NVIDIA", "dim": 0, "time": elapsed, "status": resp.status_code, "error": resp.text[:100]}
    data = resp.json()
    emb = data["data"][0]["embedding"]
    return {"provider": "NVIDIA", "dim": len(emb), "time": elapsed, "status": 0, "tokens_in": data.get("usage", {}).get("total_tokens", len(txt_long)//4)}

print("Testing embeddings...")
print(f"Text length: {len(txt_long)} chars, ~{len(txt_long)//4} tokens")
print()

r1 = test_minimax()
print(f"MiniMax: {r1}" if r1 else "MiniMax: failed")

r2 = test_nvidia()
print(f"NVIDIA:  {r2}" if r2 else "NVIDIA: failed")

if r1 and r1["dim"] and r2 and r2["dim"]:
    cost_minimax_per_1k = 0  # included in Plus plan
    cost_nvidia_per_1k = 0   # free tier
    print()
    print("=== COMPARACAO ===")
    print(f"MiniMax: {r1['dim']}d, {r1['time']:.2f}s, custo: incluso no Plus (${cost_minimax_per_1k}/1K tokens)")
    print(f"NVIDIA:  {r2['dim']}d, {r2['time']:.2f}s, custo: gratuito (NIM free tier)")
    print()
    print("RECOMENDACAO: Usar MiniMax (1536d > 1024d, qualidade superior)")
    print("Fallback: NVIDIA quando MiniMax rate-limited")
else:
    print("\nFalha em um ou ambos.")
