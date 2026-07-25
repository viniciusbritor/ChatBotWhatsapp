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
PUBLIC_PATHS = ("/webhook", "/healthz", "/oauth/callback", "/oauth/google", "/pubsub")
FIREBASE_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


def get_sa_token() -> str:
    """Get the expected SA token from env var."""
    return os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "")


def is_path_protected(path: str) -> bool:
    """Check if path requires Bearer SA token."""
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return False
    return any(path.startswith(p) for p in PROTECTED_PATHS)


def _is_valid_firebase_jwt(token: str) -> bool:
    if not token:
        return False
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
        return await call_next(request)

    logger.warning(f"Invalid SA token attempt for path {path}")
    return JSONResponse(
        status_code=403,
        content={"error": "forbidden", "message": "Invalid SA token"},
    )

