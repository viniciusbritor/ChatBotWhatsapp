"""Test NVIDIA models for best embedding."""
import os
import requests
api_key = os.popen("gcloud secrets versions access latest --secret=NVIDIA_API_KEY --project=coherence-ominichannel-fs").read().strip()
tests = [
    ("nvidia/nv-embedqa-e5-v5", "passage"),
    ("nvidia/nv-embedqa-e5-v5", "query"),
    ("nvidia/embed-qa-4", "passage"),
]
for model, itype in tests:
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"input": ["teste de embedding juridico"], "model": model, "input_type": itype, "encoding_format": "float"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            print(f"{model} ({itype}): dim={len(d['data'][0]['embedding'])} - OK")
        else:
            print(f"{model} ({itype}): {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"{model} ({itype}): ERROR {e}")
