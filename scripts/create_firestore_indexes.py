"""Cria indices compostos no Firestore via Admin API REST."""
import json
import urllib.request
import subprocess
import sys

PROJECT = "coherence-ominichannel-fs"
COLLECTION = "agent-knowledge-v2"

INDEXES = [
    {
        "label": "vector_source_title",
        "fields": [
            {"fieldPath": "owner_hash", "order": "ASCENDING"},
            {"fieldPath": "embedding_model", "order": "ASCENDING"},
            {"fieldPath": "embedding_dim", "order": "ASCENDING"},
            {"fieldPath": "schema_version", "order": "ASCENDING"},
            {"fieldPath": "source_title", "order": "ASCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
            {"fieldPath": "vector_embedding", "vectorConfig": {"dimension": 1536, "flat": {}}},
        ],
    },
    {
        "label": "vector_source_title_class",
        "fields": [
            {"fieldPath": "owner_hash", "order": "ASCENDING"},
            {"fieldPath": "embedding_model", "order": "ASCENDING"},
            {"fieldPath": "embedding_dim", "order": "ASCENDING"},
            {"fieldPath": "schema_version", "order": "ASCENDING"},
            {"fieldPath": "source_title", "order": "ASCENDING"},
            {"fieldPath": "class", "order": "ASCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
            {"fieldPath": "vector_embedding", "vectorConfig": {"dimension": 1536, "flat": {}}},
        ],
    },
    {
        "label": "vector_class",
        "fields": [
            {"fieldPath": "owner_hash", "order": "ASCENDING"},
            {"fieldPath": "embedding_model", "order": "ASCENDING"},
            {"fieldPath": "embedding_dim", "order": "ASCENDING"},
            {"fieldPath": "schema_version", "order": "ASCENDING"},
            {"fieldPath": "class", "order": "ASCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
            {"fieldPath": "vector_embedding", "vectorConfig": {"dimension": 1536, "flat": {}}},
        ],
    },
]


def get_token():
    result = subprocess.run(
        ["gcloud.cmd", "auth", "print-access-token", "--quiet"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERRO ao obter token: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    token = get_token()
    print(f"Token obtido: {len(token)} chars")

    for spec in INDEXES:
        label = spec["label"]
        body = {"queryScope": "COLLECTION", "fields": spec["fields"]}
        url = (
            f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
            f"/databases/(default)/collectionGroups/{COLLECTION}/indexes"
        )
        print(f"\nCriando indice: {label}")
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                print(f"  OK: {result.get('name', '?')}")
                print(f"  State: {result.get('state', '?')}")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8")
            try:
                err = json.loads(body_text)
                print(f"  API ERROR: {err.get('error', {}).get('message', body_text[:200])}")
            except json.JSONDecodeError:
                print(f"  HTTP {e.code}: {body_text[:200]}")
        except Exception as e:
            print(f"  ERRO: {e}")


if __name__ == "__main__":
    main()
