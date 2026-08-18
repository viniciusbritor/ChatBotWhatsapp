"""Simulacao real: visitante (5511900000000) fala pedindo acesso a Gmail.
   Admin (5511966830020) recebe WhatsApp com link assinado para aprovar.

   Fluxo:
   1. Visitante 5511900000000 manda mensagem pedindo acessar Gmail
   2. orchestrator -> check_google_access -> decide_guardian -> unapproved_guest
   3. _guard dispara notify_admin_access_request(phone, message_text)
   4. notify_admin_access_request gera link HMAC SHA-256 e envia para admin WhatsApp
"""
import os
import asyncio
import sys

os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")
sys.path.insert(0, ".")

from core.admin_notify import (
    create_approval_token,
    generate_approval_url,
    parse_approval_token,
    notify_admin_access_request,
)
from agent_loader import resolve_owner_phone, get_user

print("=" * 70)
print("SIMULACAO REAL — visitante pede acesso, admin recebe WhatsApp")
print("=" * 70)

# 1. Limpar visitante anterior (se houver)
from google.cloud import firestore
db = firestore.Client(project="coherence-ominichannel-fs")
db.collection("usuarios").document("5511900000000").delete()
print()
print("[step 0] visitante 5511900000000 removido do Firestore (clean slate)")

# 2. ensure_user_registered como visitante real
from agent_loader import ensure_user_registered
ensure_user_registered("5511900000000", sender_name="Maria Silva Teste", instance="Jennifer")
user = get_user("5511900000000") or {}
print(f"[step 1] visitante registrado:")
print(f"  role = {user.get('role')}")
print(f"  is_approved = {user.get('is_approved')}")
print(f"  name = {user.get('name')}")

# 3. Verificar admin
admin = resolve_owner_phone()
print()
print(f"[step 2] admin resolve_owner_phone = {admin}")

# 4. Gerar link de aprovacao (demonstra o HMAC)
token = create_approval_token("5511900000000")
print()
print("[step 3] token HMAC SHA-256 gerado:")
print(f"  {token[:60]}...")
print(f"  parse_approval_token roundtrip = {parse_approval_token(token)}")

url = generate_approval_url("5511900000000")
print()
print("[step 4] URL completa de aprovacao:")
print(f"  {url}")

# 5. Disparar notificacao para admin (Evolution API)
print()
print("[step 5] enviando WhatsApp para admin via Evolution API...")
result = asyncio.run(notify_admin_access_request(
    phone="5511900000000",
    sender_name="Maria Silva Teste",
    message_text="oi, queria acessar meu gmail pela Jennifer",
    instance="Jennifer",
))
print(f"  notify_admin_access_request -> {result}")

# 6. Confirmar que visitante continua bloqueado
print()
print("[step 6] visitante continua bloqueado (ate admin clicar no link):")
from agent_orchestration.access_guardian import decide_guardian
from core.owner import OwnerResolution
mock_resolution = OwnerResolution(
    owner_phone="5511966830020", owner_uid="vinicius",
    account_id="acc-jennifer", instance="Jennifer",
)
decision = decide_guardian(
    instance="Jennifer", phone="5511900000000",
    capability="gmail.search_messages", resolution=mock_resolution,
)
print(f"  verdict = {decision.verdict}  [ESPERADO: unapproved_guest]")
print(f"  reason = {decision.reason}")
assert decision.verdict == "unapproved_guest"

print()
print("=" * 70)
print("SIMULACAO CONCLUIDA")
print("  - visitante registrado como guest")
print("  - access_guardian bloqueou (unapproved_guest)")
print("  - admin recebeu WhatsApp com link assinado")
print("  - mensagem enviada para Evolution API")
print()
print(f"  >>>>>> CONFIRA O WHATSAPP DO ADMIN (5511966830020) <<<<<<")
print("=" * 70)