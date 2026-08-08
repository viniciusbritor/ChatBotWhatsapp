import subprocess, os, asyncio

r = subprocess.run(
    'gcloud secrets versions access latest --secret=COMPOSIO_API_KEY --project=coherence-ominichannel-fs',
    shell=True, capture_output=True, text=True,
)
key = r.stdout.strip()
if not key:
    for line in r.stderr.splitlines():
        l = line.strip()
        if l and not l.startswith("WARNING") and "service account" not in l:
            key = l
            break

os.environ["COMPOSIO_API_KEY"] = key

print(f"Key: {len(key)} chars, starts with: {key[:7]}...")
print(f"Has BOM: {chr(0xFEFF) in key}")

from tools.youtube_composio import search_videos

result = asyncio.run(search_videos("marvin gaye sexual healing", max_results=2))
if "error" in result:
    print(f"ERROR: {result['error'][:200]}")
else:
    items = result.get("items", [])
    print(f"OK: {len(items)} results")
    for i in items[:2]:
        sn = i.get("snippet", {})
        print(f"  - {sn.get('title', '?')[:80]}")
