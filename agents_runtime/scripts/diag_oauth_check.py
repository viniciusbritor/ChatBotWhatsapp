"""Diagnostico OAuth — verifica estado do usuario no Firestore. READ-ONLY."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")


async def main(phone: str, instance: str) -> int:
    print(f"=== OAuth Check para phone={phone} instance={instance} ===\n")

    from agent_loader import get_user

    user = get_user(phone)
    print(f"[1] get_user({phone}): {'OK' if user else 'NAO ENCONTRADO'}")
    if user:
        print(f"    user_email: {user.get('user_email', 'N/A')}")
        print(f"    scopes: {user.get('scopes', [])}")
    else:
        print("    -> OAuth nunca foi configurado para este telefone")

    from core.owner import resolve_owner

    resolution = resolve_owner(instance, fallback_phone=phone)
    print(f"\n[2] resolve_owner({instance}): {'OK' if resolution else 'FALHOU'}")
    if resolution:
        print(f"    owner_phone: {resolution.owner_phone}")
        print(f"    candidates: {list(resolution.owner_candidates)}")
        print(f"    instance: {resolution.instance}")

    from core.oauth_per_user import get_user_oauth

    token = get_user_oauth(phone)
    print(f"\n[3] get_user_oauth({phone}): {'OK' if token else 'NAO ENCONTRADO'}")
    if token:
        print(f"    has_token: {bool(token.get('token'))}")
        print(f"    has_refresh: {bool(token.get('refresh_token'))}")
        scopes = token.get("scopes", [])
        print(f"    scopes ({len(scopes)}): {scopes[:5]}")
        print(f"    expiry: {token.get('expiry', 'N/A')}")
        user_email = token.get("user_email", "")
        print(f"    user_email: {user_email}")

        required = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
        ]
        print("\n[4] Verificacao de escopos:")
        drive_scope = None
        for s in scopes:
            if "drive" in s:
                drive_scope = s
                break
        print(f"    drive scope: {drive_scope or 'AUSENTE'}")
        for req in required:
            short = req.replace("https://www.googleapis.com/auth/", "")
            found = any(short in s for s in scopes) or any(
                s.endswith(short) for s in scopes
            )
            print(f"    {short:30s} {'OK' if found else 'FALTA'}")
    else:
        print("    -> Nenhum token OAuth encontrado no Firestore")

    return 0 if (user and token) else 1


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else "5511966830020"
    instance = sys.argv[2] if len(sys.argv) > 2 else "Jennifer"
    sys.exit(asyncio.run(main(phone, instance)))
