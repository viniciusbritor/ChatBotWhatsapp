"""Bearer SA token middleware for admin/chat/proactive endpoints.

Accepts:
- Authorization: Bearer <SA_TOKEN> header
- ?token=<SA_TOKEN> query string
- ?token=<FIREBASE_JWT> query string (Portal integration)
- session_token cookie (set by server on dashboard page load)
"""
import hmac
import os
import logging
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PROTECTED_PATHS = ("/admin", "/chat", "/proactive/send", "/version")
PUBLIC_PATHS = (
    "/webhook",
    "/healthz",
    "/oauth/callback",
    "/oauth/google",
    "/pubsub",
    "/a",
    "/admin/approve-user",
    "/admin/evolution/auto-webhook",
)
FIREBASE_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


def get_sa_token() -> str:
    """Get the expected SA token from env var."""
    return os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "")


def is_path_protected(path: str) -> bool:
    """Check if path requires Bearer SA token."""
    for p in PUBLIC_PATHS:
        if p == "/a":
            # /a e prefixo de onboarding; nao pode capturar /admin
            if path == "/a" or path.startswith("/a/"):
                return False
            continue
        if path.startswith(p):
            return False
    return any(path.startswith(p) for p in PROTECTED_PATHS)


def _is_valid_firebase_jwt(token: str) -> bool:
    if not token:
        return False
    if token.startswith("ml."):
        from core.magic_link import verify_magic_link_token

        return verify_magic_link_token(token) is not None
    try:
        claims = id_token.verify_firebase_token(
            token,
            GoogleAuthRequest(),
            audience=FIREBASE_PROJECT,
        )
    except Exception as exc:
        logger.warning("firebase_jwt_rejected reason=%s", type(exc).__name__)
        return False
    return bool(claims and claims.get("sub"))


def _firebase_claims(token: str) -> dict:
    """Retorna claims do Firebase JWT validado ou magic link token, ou dict vazio."""
    if not token:
        return {}
    if token.startswith("ml."):
        from core.magic_link import verify_magic_link_token

        return verify_magic_link_token(token) or {}
    try:
        claims = id_token.verify_firebase_token(
            token,
            GoogleAuthRequest(),
            audience=FIREBASE_PROJECT,
        )
    except Exception:
        return {}
    return claims or {}


def resolve_caller(request) -> tuple:
    """Resolve (role, phone) do caller autenticado.

    - SA token (Bearer) -> ("admin", "").
    - Firebase JWT -> phone em 3 fontes, na ordem:
        1. claim ``phone_number`` (custom claim setado pelo Portal).
        2. lookup Firestore por ``email`` (usuarios/{phone}.email).
        3. lookup Firestore por ``sub`` (usuarios/{phone}.firebase_uid).
      Role resolvida via get_user_role(phone).
    - JWT sem phone mas email/UID admin (config/admins) -> ("admin", "").
    - Nenhum identificador -> ("agent_user", "") — seguro.
    """
    token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        token = request.cookies.get("session_token", "")
    if not token:
        return "", ""

    if not token or not isinstance(token, str):
        return "", ""

    expected = get_sa_token()
    if expected and isinstance(expected, str) and hmac.compare_digest(token, expected):
        return "admin", ""

    claims = _firebase_claims(token)
    if not claims:
        return "", ""

    from agent_loader import (
        get_user_role,
        get_coherence_module_role,
        lookup_phone_by_email,
        lookup_phone_by_uid,
        _is_admin_email,
        _is_admin_uid,
        resolve_owner_phone,
        sync_user_profile,
    )

    raw_phone = claims.get("phone_number", "") or ""
    phone = "".join(c for c in str(raw_phone) if c.isdigit())
    email = str(claims.get("email", "") or "").strip().lower()
    uid = str(claims.get("sub", "") or claims.get("user_id", "") or "").strip()

    if not phone and email:
        phone = lookup_phone_by_email(email)
    if not phone and uid:
        phone = lookup_phone_by_uid(uid)

    if not phone and (email or uid):
        if _is_admin_email(email) or _is_admin_uid(uid):
            phone = resolve_owner_phone()

    name = str(claims.get("name", "") or "").strip()
    picture = str(claims.get("picture", "") or "").strip()

    role = "agent_user"
    if email:
        coherence_role = get_coherence_module_role(email, uid)
        if coherence_role:
            role = coherence_role
        else:
            role = get_user_role(email)
    elif phone:
        role = get_user_role(phone)
    elif uid:
        role = get_user_role(uid)

    if phone and (email or uid or (name and name != "user")):
        sync_user_profile(phone, email=email, uid=uid, name=name, picture=picture, role=role)

    return role, phone


def resolve_caller_profile(request) -> dict:
    """Retorna profile estruturado do caller autenticado (role, phone, email, name, picture, is_admin)."""
    token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        token = request.cookies.get("session_token", "")

    expected = get_sa_token()
    if expected and isinstance(expected, str) and hmac.compare_digest(token, expected):
        return {
            "role": "admin",
            "phone": "5511967389901",
            "email": "admin@coherence.ai",
            "name": "Service Account",
            "picture": "",
            "is_admin": True,
        }

    claims = _firebase_claims(token)
    role, phone = resolve_caller(request)
    name = str(claims.get("name", "") or "").strip()
    email = str(claims.get("email", "") or "").strip().lower()
    picture = str(claims.get("picture", "") or "").strip()
    return {
        "role": role or "agent_user",
        "phone": phone or "",
        "email": email or "",
        "name": name or ("Administrador" if role == "admin" else "Usuário"),
        "picture": picture or "",
        "is_admin": role == "admin",
    }


AGENT_USER_ALLOWED_PREFIXES = (
    "/admin/dashboard",
    "/admin/ping",
    "/admin/status",
    "/admin/me",
    "/admin/accounts",
    "/admin/agents",
    "/admin/users",
    "/admin/knowledge",
    "/api/v1/composio/status",
    "/api/v1/composio/authorize",
    "/api/v1/composio/connect-all",
)


def _agent_user_allowed(path: str) -> bool:
    """Paths que um agent_user pode acessar (admin tem acesso a tudo)."""
    if path in ("/admin/dashboard", "/admin/ping", "/admin/status"):
        return True
    return any(path.startswith(p) for p in AGENT_USER_ALLOWED_PREFIXES)


async def auth_middleware(request: Request, call_next):
    """FastAPI middleware to enforce Bearer SA token on protected paths.

    Accepts token via:
    - Authorization: Bearer <token> header (preferred for API calls)
    - ?token=<token> query string (used by Portal frontend via window.open)
    - session_token cookie (set by server when serving dashboard HTML)
    """
    path = request.url.path

    if not is_path_protected(path):
        return await call_next(request)

    expected_token = get_sa_token()
    if not expected_token:
        logger.error("AGENTS_RUNTIME_SA_TOKEN_SECRET not configured")
        return JSONResponse(
            status_code=500,
            content={"error": "server_misconfigured", "message": "SA token not set"},
        )

    provided_token = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided_token = auth_header[7:]
    else:
        query_token = request.query_params.get("token")
        if query_token:
            provided_token = query_token
        else:
            cookie_token = request.cookies.get("session_token")
            if cookie_token:
                provided_token = cookie_token

    if not provided_token:
        return JSONResponse(
            status_code=403,
            content={"error": "unauthorized", "message": "Bearer token required"},
        )

    if hmac.compare_digest(provided_token, expected_token):
        return await call_next(request)

    jwt_valid = _is_valid_firebase_jwt(provided_token)
    logger.warning("auth_token_mismatch firebase_valid=%s path=%s", jwt_valid, path)
    if jwt_valid:
        role, _ = resolve_caller(request)
        if role == "agent_user" and not _agent_user_allowed(path):
            logger.warning("agent_user_forbidden path=%s", path)
            return JSONResponse(
                status_code=403,
                content={"error": "forbidden", "message": "admin_required"},
            )
        return await call_next(request)

    logger.warning(f"Invalid SA token attempt for path {path}")
    return JSONResponse(
        status_code=403,
        content={"error": "forbidden", "message": "Invalid SA token"},
    )

