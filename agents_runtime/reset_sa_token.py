import secrets
import subprocess

# 64 chars hex (256 bits de entropia) - puro ASCII
new_token = secrets.token_hex(32)
print(f"Novo token: {new_token}")
print(f"Tamanho: {len(new_token)} chars (ASCII safe)")

with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/sa_token.txt", "w") as f:
    f.write(new_token)

# Use echo to pipe
result = subprocess.run(
    ["gcloud", "secrets", "versions", "add", "agents-runtime-sa-token",
     "--project=coherence-ominichannel-fs", "--data-file=-"],
    input=new_token.encode(),
    capture_output=True
)
print("STDOUT:", result.stdout.decode())
print("STDERR:", result.stderr.decode())
print("Return code:", result.returncode)
