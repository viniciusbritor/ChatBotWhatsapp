"""Check secrets in brasili-ia-news project."""
import subprocess
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

PROJECT = 'brasili-ia-news'

KEY_SECRETS = ['DEEPSEEK_API_KEY', 'NVIDIA_API_KEY', 'MINIMAX_API_KEY',
               'ELEVEN_LABS_API_KEY', 'RUNPOD_API_KEY', 'GEMINI_API_KEY',
               'GITHUB_TOKEN', 'GCP_SA_KEY', 'DOCKERHUB_TOKEN']

PLACEHOLDER_PATTERNS = [b'PLACEHOLDER', b'PLACEHOLDER_', b'PLACEHOLDER_REPLACE', b'', b'\n', b'\r\n', b'\r']

print(f"{'SECRET':<25} | {'VER':<5} | {'SIZE':<8} | {'STATUS'}")
print("-" * 70)

for name in KEY_SECRETS:
    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'list', name,
         f'--project={PROJECT}', '--format=value(name)'],
        capture_output=True
    )
    versions = [v.strip() for v in r.stdout.decode().split('\n') if v.strip()]
    if not versions:
        print(f"{name:<25} | {'N/A':<5} | {'N/A':<8} | NOT FOUND")
        continue

    latest = versions[-1]
    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'access', latest,
         f'--secret={name}', f'--project={PROJECT}'],
        capture_output=True
    )
    value = r.stdout
    clean = value.rstrip(b'\n\r')
    size = len(clean)
    is_ph = any(clean.startswith(p) for p in PLACEHOLDER_PATTERNS)
    has_bom = clean.startswith(bytes([0xef, 0xbb, 0xbf]))
    is_ascii = all(b < 128 for b in clean)
    if is_ph:
        status = "[PLACEHOLDER]"
    elif has_bom:
        status = "[HAS BOM]"
    elif not is_ascii:
        status = "[HAS UNICODE]"
    elif size < 5:
        status = "[EMPTY/TOO SHORT]"
    else:
        status = "[REAL VALUE]"
    print(f"{name:<25} | {latest:<5} | {size:<8} | {status}")
