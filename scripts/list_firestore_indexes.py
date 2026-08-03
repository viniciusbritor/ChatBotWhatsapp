"""Lista indices do Firestore para um collection group."""
import json
import urllib.request
import urllib.error
import subprocess
import sys

PROJECT = "coherence-ominichannel-fs"
COLLECTION = "agent-knowledge-v2"


def get_token():
    result = subprocess.run(
        ["gcloud.cmd", "auth", "print-access-token", "--quiet"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def main():
    token = get_token()
    url = (
        f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
        f"/databases/(default)/collectionGroups/{COLLECTION}/indexes"
    )
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            indexes = data.get("indexes", [])
            print(f"Total indexes: {len(indexes)}\n")
            for idx in indexes:
                name = idx.get("name", "").split("/")[-1]
                state = idx.get("state", "?")
                fields = [f["fieldPath"] + (f" ({f.get('vectorConfig',{}).get('dimension','')})" if "vectorConfig" in f else "") for f in idx.get("fields", [])]
                print(f"  [{state}] {name}")
                print(f"    Fields: {', '.join(fields[:8])}")
                if len(fields) > 8:
                    print(f"            ...+{len(fields)-8} more")
                print()
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        print(f"HTTP {e.code}: {body_text[:500]}")


if __name__ == "__main__":
    main()
