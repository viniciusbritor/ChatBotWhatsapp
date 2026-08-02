import subprocess

# Verificar valor real do secret
for secret in ["agents-runtime-sa-token", "agents-runtime-sa-token-clean"]:
    result = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret}",
         "--project=coherence-ominichannel-fs"],
        capture_output=True
    )
    value = result.stdout
    print(f"=== {secret} ===")
    print(f"  Length: {len(value)}")
    print(f"  Value: {repr(value[:80])}")
    print(f"  Has BOM: {value.startswith(b'\\xef\\xbb\\xbf')}")
    print(f"  Is ASCII: {all(b < 128 for b in value.rstrip(b'\\n'))}")
    print("  Versions:")
