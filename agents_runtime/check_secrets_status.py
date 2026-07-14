"""Check which secrets are placeholders vs real values."""
import subprocess
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

PROJECT = 'coherence-ominichannel-fs'

# Secrets we care about for agents_runtime + whatsapp-agente
SECRETS_TO_CHECK = [
    'DEEPSEEK_API_KEY', 'NVIDIA_API_KEY', 'MINIMAX_API_KEY', 'MINIMAX_GROUP_ID',
    'SERPER_API_KEY', 'GOOGLE_OAUTH_TOKEN', 'EVOLUTION_API_KEY',
    'AGENTS_RUNTIME_SA_TOKEN', 'AGENTS_RUNTIME_SA_TOKEN_CLEAN',
    'ELEVEN_LABS_API_KEY', 'RUNPOD_API_KEY', 'GEMINI_API_KEY', 'GITHUB_TOKEN',
]

PLACEHOLDER_PATTERNS = [
    b'PLACEHOLDER', b'PLACEHOLDER_', b'PLACEHOLDER_REPLACE',
    b'', b'\n', b'\r\n', b'\r',
]

print(f"{'SECRET':<35} | {'VERSION':<8} | {'SIZE':<8} | {'STATUS'}")
print("-" * 80)

for name in SECRETS_TO_CHECK:
    # Get all versions
    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'list', name,
         f'--project={PROJECT}', '--format=value(name)'],
        capture_output=True
    )
    versions = r.stdout.decode().strip().split('\n') if r.stdout else []
    if not versions or not versions[0]:
        print(f"{name:<35} | {'N/A':<8} | {'N/A':<8} | NOT FOUND")
        continue

    # Get latest version
    latest_v = versions[-1].strip()

    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'access', latest_v,
         f'--secret={name}', f'--project={PROJECT}'],
        capture_output=True
    )
    value = r.stdout

    size = len(value.rstrip(b'\n\r'))
    is_placeholder = any(value.rstrip(b'\n\r').startswith(p) for p in PLACEHOLDER_PATTERNS)
    has_bom = value.startswith(bytes([0xef, 0xbb, 0xbf]))
    is_ascii = all(b < 128 for b in value.rstrip(b'\n\r'))

    if is_placeholder:
        status = "[PLACEHOLDER]"
    elif has_bom:
        status = "[HAS BOM]"
    elif not is_ascii:
        status = "[HAS UNICODE]"
    elif size < 5:
        status = "[EMPTY/TOO SHORT]"
    else:
        status = "[REAL VALUE]"

    print(f"{name:<35} | {latest_v:<8} | {size:<8} | {status}")
