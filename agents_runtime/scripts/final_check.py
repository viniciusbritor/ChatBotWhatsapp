import os
os.environ.setdefault('GCP_PROJECT', 'coherence-ominichannel-fs')
from agent_loader import is_user_approved

print('=== Verificacao final pos-simulacao ===')
tests = [
    ('5511900000000', 'Maria (ficticia)', False),
    ('5511900000001', 'Pedro (ficticio - APROVADO via WhatsApp)', True),
    ('5521984843235', 'Rafael (mantido por admin)', True),
    ('5511973391993', 'Vivian (revogada)', False),
    ('558188464546', 'Holding (revogado)', False),
    ('5511966830020', 'Owner', True),
]
all_ok = True
for phone, label, expected in tests:
    actual = is_user_approved(phone)
    status = 'OK' if actual == expected else 'FALHOU'
    if actual != expected:
        all_ok = False
    print(f'  [{status}] {phone} ({label}): {actual} [esperado: {expected}]')

print()
if all_ok:
    print('=== TODOS OS TESTES PASSARAM ===')
else:
    print('=== ALGUNS TESTES FALHARAM ===')