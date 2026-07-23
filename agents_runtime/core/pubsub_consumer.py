import base64
import hashlib
import logging
import os
import threading
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

_seen_message_ids: Set[str] = set()
_seen_lock = threading.RLock()
_SEEN_MAX = 5000


def _strip_bearer(token: str) -> str:
    if not token:
        return ""
    parts = token.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return token


def verify_pubsub_token(
    token: str,
    audience: Optional[str] = None,
    service_account: Optional[str] = None,
) -> bool:
    raw = _strip_bearer(token)
    expected_audience = audience or os.getenv("PUBSUB_TOKEN_AUDIENCE", "")
    expected_service_account = service_account or os.getenv("PUBSUB_PUSH_SERVICE_ACCOUNT", "")
    if not raw or not expected_audience or not expected_service_account:
        logger.warning("pubsub_token_rejected reason=missing_verification_config")
        return False
    try:
        claims = id_token.verify_oauth2_token(
            raw,
            GoogleAuthRequest(),
            audience=expected_audience,
        )
    except Exception as exc:
        logger.warning("pubsub_token_rejected reason=%s", type(exc).__name__)
        return False
    issuer = claims.get("iss")
    email = str(claims.get("email", ""))
    email_verified = claims.get("email_verified") is True
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        logger.warning("pubsub_token_rejected reason=invalid_issuer")
        return False
    if not email_verified or email != expected_service_account:
        logger.warning("pubsub_token_rejected reason=invalid_service_account")
        return False
    return True


def _dedupe(message_id: str) -> bool:
    """In-process fast path. The ledger remains the source of truth."""
    if not message_id:
        return False
    digest = hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:16]
    with _seen_lock:
        if digest in _seen_message_ids:
            return False
        _seen_message_ids.add(digest)
        if len(_seen_message_ids) > _SEEN_MAX:
            overflow = len(_seen_message_ids) - _SEEN_MAX
            for _ in range(overflow):
                _seen_message_ids.pop()
    return True


def parse_pubsub_push_body(body: Dict[str, Any]) -> Dict[str, Any]:
    if "message" in body and isinstance(body["message"], dict):
        msg = body["message"]
        data_b64 = msg.get("data", "")
        decoded = ""
        if data_b64:
            try:
                decoded = base64.b64decode(data_b64).decode("utf-8", errors="ignore")
            except Exception:
                decoded = data_b64
        return {
            "data": decoded,
            "message_id": msg.get("messageId") or body.get("message_id") or "",
            "attributes": msg.get("attributes") or body.get("attributes") or {},
            "publish_time": msg.get("publishTime") or body.get("publish_time") or "",
        }
    return {
        "data": body.get("data", ""),
        "message_id": body.get("message_id") or "",
        "attributes": body.get("attributes") or {},
        "publish_time": body.get("publish_time") or "",
    }


def _forget(message_id: str) -> None:
    if not message_id:
        return
    digest = hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:16]
    with _seen_lock:
        _seen_message_ids.discard(digest)


async def dispatch(
    payload: Dict[str, Any],
    handler: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    """Compatibility wrapper around the new ledger-based dispatch."""
    from core.pubsub_dispatcher import dispatch_with_ledger

    return await dispatch_with_ledger(payload, handler)
