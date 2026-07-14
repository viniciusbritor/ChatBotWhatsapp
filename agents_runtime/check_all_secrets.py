"""Check ALL secrets with lowercase names."""
import subprocess
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

PROJECT = 'coherence-ominichannel-fs'

# Get all secrets
r = subprocess.run(
    ['gcloud.cmd', 'secrets', 'list', f'--project={PROJECT}', '--format=value(name)'],
    capture_output=True
)
all_secrets = sorted([s.strip() for s in r.stdout.decode().split('\n') if s.strip()])

PLACEHOLDER_PATTERNS = [
    b'PLACEHOLDER', b'PLACEHOLDER_', b'PLACEHOLDER_REPLACE',
    b'', b'\n', b'\r\n', b'\r',
]

# Only show secrets related to our use case
KEYWORDS = ['deepseek', 'nvidia', 'minimax', 'serper', 'google', 'evolution',
            'agents-runtime', 'whatsapp', 'avatar', 'api', 'key', 'token']

print(f"{'SECRET':<40} | {'VERSION':<8} | {'SIZE':<8} | {'STATUS'}")
print("-" * 90)

for name in all_secrets:
    if not any(kw in name.lower() for kw in KEYWORDS):
        continue

    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'list', name,
         f'--project={PROJECT}', '--format=value(name)'],
        capture_output=True
    )
    versions = [v.strip() for v in r.stdout.decode().split('\n') if v.strip()]
    if not versions:
        continue

    latest_v = versions[-1]

    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'access', latest_v,
         f'--secret={name}', f'--project={PROJECT}'],
        capture_output=True
    )
    value = r.stdout
    clean = value.rstrip(b'\n\r')

    size = len(clean)
    is_placeholder = any(clean.startswith(p) for p in PLACEHOLDER_PATTERNS)
    has_bom = clean.startswith(bytes([0xef, 0xbb, 0xbf]))
    is_ascii = all(b < 128 for b in clean)

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

    print(f"{name:<40} | {latest_v:<8} | {size:<8} | {status}")
