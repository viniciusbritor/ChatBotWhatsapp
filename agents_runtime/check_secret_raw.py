import subprocess

for secret in ["agents-runtime-sa-token", "agents-runtime-sa-token-clean"]:
    print(f"\n=== {secret} ===")
    r = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         f"--secret={secret}", "--project=coherence-ominichannel-fs"],
        capture_output=True
    )
    raw = r.stdout
    print(f"  raw bytes: {len(raw)}")
    print(f"  raw hex (first 20): {raw[:20].hex()}")
    print(f"  Has UTF-8 BOM (efbbbf)? {raw.startswith(b'\\xef\\xbb\\xbf')}")
    print(f"  raw text repr: {raw[:80]!r}")
    # Decode and check
    try:
        text = raw.decode("utf-8")
        print(f"  decoded text repr: {text[:80]!r}")
        print(f"  Has unicode BOM (ufeff)? {text.startswith('\\ufeff')}")
        clean = text.lstrip("\ufeff").strip()
        print(f"  CLEAN (no BOM): {clean[:80]!r}")
    except Exception as e:
        print(f"  decode error: {e}")
