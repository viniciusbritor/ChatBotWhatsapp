"""Smoke test do GUARDRAIL §0.7 — simula visitante pedindo acesso."""
import os
import sys

os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

sys.path.insert(0, ".")

print("=" * 70)
print("SMOKE TEST — GUARDRAIL §0.7 (Anti Auto-Aprovacao)")
print("=" * 70)

from agent_orchestration.access_guardian import decide_guardian
from core.owner import OwnerResolution
from agent_loader import ensure_user_registered, get_user, is_user_approved

mock_resolution = OwnerResolution(
    owner_phone="5511966830020",
    owner_uid="vinicius",
    account_id="acc-jennifer",
    instance="Jennifer",
)

print()
print("--- 1. decide_guardian para visitante SEM OAuth (5511900000000) ---")
decision = decide_guardian(
    instance="Jennifer",
    phone="5511900000000",
    capability="calendar.list_events",
    resolution=mock_resolution,
)
print(f"  verdict: {decision.verdict}")
print(f"  reason: {decision.reason}")
print(f"  phone: {decision.phone}")

print()
print("--- 2. ensure_user_registered para visitante ---")
ensure_user_registered("5511900000000", sender_name="Visitante Teste", instance="Jennifer")
user = get_user("5511900000000") or {}
print(f"  user.role = {user.get('role')}")
print(f"  user.is_approved = {user.get('is_approved')}")
print(f"  user.name = {user.get('name')}")
print(f"  user.google_oauth_token = {bool(user.get('google_oauth_token'))}")

print()
print("--- 3. is_user_approved (politica estrita) ---")
approved = is_user_approved("5511900000000")
print(f"  is_user_approved(5511900000000) = {approved}  [ESPERADO: False]")
assert approved is False, "BUG: visitante foi aprovado sem admin clicar!"
print("  [OK] visitante NAO foi aprovado")

print()
print("--- 4. Rafael Oliveira (preservado por decisao admin) ---")
rafael = get_user("5521984843235") or {}
print(f"  rafael.role = {rafael.get('role')}")
print(f"  rafael.is_approved = {rafael.get('is_approved')}")
print(f"  rafael.approved_by = {rafael.get('approved_by')}")
print(f"  rafael.approved_at = {rafael.get('approved_at')}")
print(f"  is_user_approved(5521984843235) = {is_user_approved('5521984843235')}  [ESPERADO: True]")
assert is_user_approved("5521984843235") is True
print("  [OK] Rafael mantido por admin_kept_2026_08_16")

print()
print("--- 5. Vivian (revogada + token deletado) ---")
vivian = get_user("5511973391993") or {}
print(f"  vivian.is_approved = {vivian.get('is_approved')}  [ESPERADO: False]")
print(f"  vivian.google_oauth_token = {bool(vivian.get('google_oauth_token'))}  [ESPERADO: False]")
print(f"  vivian.revoked_reason = {vivian.get('revoked_reason')}")
print(f"  is_user_approved(5511973391993) = {is_user_approved('5511973391993')}  [ESPERADO: False]")
assert is_user_approved("5511973391993") is False
print("  [OK] Vivian bloqueada apos revogacao")

print()
print("--- 6. Holding Auditchain (revogado) ---")
holding = get_user("558188464546") or {}
print(f"  holding.is_approved = {holding.get('is_approved')}  [ESPERADO: False]")
print(f"  holding.revoked_reason = {holding.get('revoked_reason')}")
assert is_user_approved("558188464546") is False
print("  [OK] Holding revogado")

print()
print("--- 7. Admin (owner) sempre aprovado ---")
assert is_user_approved("5511966830020") is True
print("  [OK] owner 5511966830020 sempre aprovado")

print()
print("--- 8. Limpar visitante de teste ---")
db_path_cleanup = None  # nao removemos do Firestore (intencional)
print("  visitante 5511900000000 mantido no Firestore (guest)")

print()
print("=" * 70)
print("TODOS OS TESTES PASSARAM — GUARDRAIL §0.7 ATIVO")
print("=" * 70)