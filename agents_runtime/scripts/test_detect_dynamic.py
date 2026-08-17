import os
import asyncio
os.environ.setdefault('GCP_PROJECT', 'coherence-ominichannel-fs')

from tools.api_registry import api_registry
from orchestrator import _detect_dynamic_toolkit

asyncio.run(api_registry.discover_all())

test_phrases = [
    'Meu perfil do LinkedIn',
    'Quero que vc me mostre ele',
    'busque meu perfil no linkedin',
    'meu linkedin',
    'me de meu perfil do linkedin',
]
print('=== Testando _detect_dynamic_toolkit ===')
for phrase in test_phrases:
    slug = _detect_dynamic_toolkit(phrase)
    print(f'  {phrase!r:50} -> {slug}')

print()
print('=== api_registry status ===')
print(f'  is_allowed(linkedin): {api_registry.is_allowed("linkedin")}')
print(f'  linkedin in _composio_toolkits: {"linkedin" in api_registry._composio_toolkits}')
if 'linkedin' in api_registry._composio_toolkits:
    meta = api_registry._composio_toolkits['linkedin']
    print(f'  linkedin module_path: {meta.module_path}')

print()
print('=== KEYWORD_TO_TOOLKIT ===')
from orchestrator import _KEYWORD_TO_TOOLKIT
for kw, slug in _KEYWORD_TO_TOOLKIT.items():
    print(f'  {kw!r:30} -> {slug}')