import hashlib
import subprocess
import os

# Token ASCII puro (sem BOM)
clean_token = "764db1dde013737b2abf60d683f2e2d1a22dd709c864b600de25eedf7bb75a60"

# Salvar em arquivo binário para evitar BOM do Windows
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean_sa.bin", "wb") as f:
    f.write(clean_token.encode("ascii"))

# Verificar
with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean_sa.bin", "rb") as f:
    content = f.read()
print(f"File bytes ({len(content)}): {repr(content)}")
print(f"Has BOM? {content.startswith(b'\\xef\\xbb\\xbf')}")
print(f"Is ASCII? {all(b < 128 for b in content)}")

# Recriar secret agents-runtime-sa-token (versao 2 = clean, sem BOM)
print("\n=== Adding version 2 to agents-runtime-sa-token (clean) ===")
result = subprocess.run(
    ["gcloud", "secrets", "versions", "add", "agents-runtime-sa-token",
     "--project=coherence-ominichannel-fs",
     "--data-file=C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/clean_sa.bin"],
    capture_output=True
)
print("STDOUT:", result.stdout.decode())
print("STDERR:", result.stderr.decode())
print("RC:", result.returncode)
