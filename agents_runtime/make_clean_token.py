import secrets
import subprocess
import os
import sys

print(f"Python version: {sys.version}")
print(f"Default encoding: {sys.getdefaultencoding()}")
print(f"FS encoding: {sys.getfilesystemencoding()}")

# Token ASCII puro
token = secrets.token_hex(32)
print(f"\nToken: {repr(token)}")
print(f"Bytes: {len(token.encode('ascii'))} (all ASCII)")

# Save to file using binary mode
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/sa_token_clean.txt", "wb") as f:
    f.write(token.encode("ascii"))

# Read back and verify
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/sa_token_clean.txt", "rb") as f:
    saved = f.read()
print(f"Saved: {repr(saved)}")
print(f"Saved bytes: {len(saved)} (expected 64)")

# Now create a new secret
print("\n=== Creating new secret ===")
result = subprocess.run(
    ["gcloud", "secrets", "create", "agents-runtime-sa-token-clean",
     "--project=coherence-ominichannel-fs", "--replication-policy=automatic",
     "--data-file=C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/sa_token_clean.txt"],
    capture_output=True
)
print("STDOUT:", result.stdout.decode())
print("STDERR:", result.stderr.decode())
print("RC:", result.returncode)

if result.returncode == 0:
    print("Secret created. Adding first version.")
    # Add value as version
    result = subprocess.run(
        ["gcloud", "secrets", "versions", "add", "agents-runtime-sa-token-clean",
         "--project=coherence-ominichannel-fs", "--data-file=C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/sa_token_clean.txt"],
        capture_output=True
    )
    print("STDOUT:", result.stdout.decode())
    print("STDERR:", result.stderr.decode())
    print("RC:", result.returncode)

print(f"\nToken value: {token}")
print("Use this in --set-secrets=AGENTS_RUNTIME_SA_TOKEN_SECRET=agents-runtime-sa-token-clean:latest")
