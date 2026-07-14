"""Bearer SA token middleware for admin/chat/proactive endpoints.

Accepts:
- Authorization: Bearer <SA_TOKEN> header
- ?token=<SA_TOKEN> query string
- ?token=<FIREBASE_JWT> query string (Portal integration)
"""
import os
import json
import time
import base64
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PROTECTED_PATHS = ("/admin", "/chat", "/proactive/send", "/version")
FIREBASE_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


def get_sa_token() -> str:
    """Get the expected SA token from env var."""
    return os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "")


def is_path_protected(path: str) -> bool:
    """Check if path requires Bearer SA token."""
    return any(path.startswith(p) for p in PROTECTED_PATHS)


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification (Portal already validated)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return {}


def _is_valid_firebase_jwt(token: str) -> bool:
    """Validate that the token looks like a valid Firebase JWT."""
    if not token or len(token) < 50:
        logger.warning(f"Firebase JWT rejected: too short ({len(token)})")
        return False
    payload = _decode_jwt_payload(token)
    if not payload:
        logger.warning("Firebase JWT rejected: empty payload")
        return False
    try:
        aud = payload.get("aud", "")
        exp = payload.get("exp", 0)
        now = int(time.time())
        firebase_signer = payload.get("firebase", {}).get("sign_in_provider")
        if aud != FIREBASE_PROJECT:
            logger.warning(f"Firebase JWT rejected: aud mismatch ({aud} != {FIREBASE_PROJECT})")
            return False
        if exp < now:
            logger.warning(f"Firebase JWT rejected: expired (exp={exp} < now={now})")
            return False
        if firebase_signer is None:
            logger.warning("Firebase JWT rejected: missing firebase.sign_in_provider")
            return False
        logger.info(f"Firebase JWT accepted for user: {payload.get('email', 'unknown')}")
        return True
    except Exception as e:
        logger.warning(f"Firebase JWT rejected: {e}")
        return False


async def auth_middleware(request: Request, call_next):
    """FastAPI middleware to enforce Bearer SA token on protected paths.

    Accepts token via:
    - Authorization: Bearer <token> header (preferred for API calls)
    - ?token=<token> query string (used by Portal frontend via window.open)
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

    if not provided_token:
        return JSONResponse(
            status_code=403,
            content={"error": "unauthorized", "message": "Bearer token required"},
        )

    if provided_token == expected_token:
        return await call_next(request)

    if _is_valid_firebase_jwt(provided_token):
        return await call_next(request)

    logger.warning(f"Invalid SA token attempt for path {path}")
    return JSONResponse(
        status_code=403,
        content={"error": "forbidden", "message": "Invalid SA token"},
    )