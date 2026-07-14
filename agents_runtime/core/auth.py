"""Bearer SA token middleware for admin/chat/proactive endpoints."""
import os
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PROTECTED_PATHS = ("/admin", "/chat", "/proactive/send", "/version")


def get_sa_token() -> str:
    """Get the expected SA token from env var."""
    return os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "")


def is_path_protected(path: str) -> bool:
    """Check if path requires Bearer SA token."""
    return any(path.startswith(p) for p in PROTECTED_PATHS)


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

    if provided_token != expected_token:
        logger.warning(f"Invalid SA token attempt for path {path}")
        return JSONResponse(
            status_code=403,
            content={"error": "forbidden", "message": "Invalid SA token"},
        )

    return await call_next(request)