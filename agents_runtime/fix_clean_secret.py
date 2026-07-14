import subprocess
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

# Token limpo
token = "764db1dde013737b2abf60d683f2e2d1a22dd709c864b600de25eedf7bb75a60"

# Escrever em modo binário
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean.bin", "wb") as f:
    f.write(token.encode("ascii"))

# Verificar
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean.bin", "rb") as f:
    raw = f.read()
print(f"File size: {len(raw)}, starts with BOM? {raw.startswith(bytes([0xef, 0xbb, 0xbf]))}")

# Atualizar versao (criar nova) com token limpo
print("\n=== Adding version 2 to agents-runtime-sa-token-clean ===")
r = subprocess.run(
    ["gcloud.cmd", "secrets", "versions", "add", "agents-runtime-sa-token-clean",
     "--project=coherence-ominichannel-fs",
     "--data-file=C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean.bin"],
    capture_output=True
)
print("STDOUT:", r.stdout.decode())
print("STDERR:", r.stderr.decode())

# Verificar
print("\n=== Verifying ===")
r = subprocess.run(
    ["gcloud.cmd", "secrets", "versions", "access", "latest",
     "--secret=agents-runtime-sa-token-clean", "--project=coherence-ominichannel-fs"],
    capture_output=True
)
raw = r.stdout
print(f"Size: {len(raw)}")
print(f"Starts with BOM? {raw.startswith(bytes([0xef, 0xbb, 0xbf]))}")
print(f"Repr: {raw[:80]!r}")
