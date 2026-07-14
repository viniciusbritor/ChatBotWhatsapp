"""Update secrets with REAL values found in workspace."""
import subprocess
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

PROJECT = 'coherence-ominichannel-fs'

# Real values found in workspace
REAL_VALUES = {
    'DEEPSEEK_API_KEY': 'sk-acebbaaaa37b4a4da1c31c673a0f3ca7',
    'NVIDIA_API_KEY': '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',
    'MINIMAX_API_KEY': 'sk-cp-kinSP2nIdvAM2RR15GIW3LRkdeAD6q-ZEnGVS1JFSm454VKXDpXhBSte00_pPnucoY9lVWSQGkkLlfvdwgAWDucCA4XVi9BSqU1pjEyHR-ku-q0GglecT2w',
    'EVOLUTION_API_KEY': 'jennifer_secret_2025',
}

# Save to files (binary to avoid BOM)
for name, value in REAL_VALUES.items():
    path = f"C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/secret_{name}.txt"
    with open(path, 'wb') as f:
        f.write(value.encode('utf-8'))
    print(f"Saved {name} ({len(value)} chars) to {path}")

print()
print("=== Adding new versions to secrets ===")
for name, value in REAL_VALUES.items():
    path = f"C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/secret_{name}.txt"
    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'add', name,
         f'--project={PROJECT}', f'--data-file={path}'],
        capture_output=True
    )
    out = r.stdout.decode()
    err = r.stderr.decode()
    if 'Created version' in out or 'Created version' in err:
        print(f"  {name}: NEW version added")
    else:
        print(f"  {name}: {out[:100]} {err[:100]}")

# Verify
print()
print("=== Verifying secrets now have REAL values ===")
for name in REAL_VALUES:
    r = subprocess.run(
        ['gcloud.cmd', 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        capture_output=True
    )
    value = r.stdout
    clean = value.rstrip(b'\n\r')
    is_ph = clean.startswith(b'PLACEHOLDER')
    print(f"  {name}: {len(clean)} bytes, placeholder={is_ph}")
