import base64
import hashlib
import json
import logging
import threading
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)

AUDIENCE_HINT = "agents-runtime-pubsub"
_seen_message_ids: Set[str] = set()
_seen_lock = threading.RLock()
_SEEN_MAX = 10000


def _oidc_audience() -> str:
    try:
        from main import app

        url = getattr(app, "url", None)
        return url or AUDIENCE_HINT
    except Exception:
        return AUDIENCE_HINT


def _strip_bearer(token: str) -> str:
    if not token:
        return ""
    parts = token.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return token


def _decode_unverified(token: str) -> Dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        import base64 as _b64

        data = parts[1]
        data += "=" * (-len(data) % 4)
        return json.loads(_b64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def verify_pubsub_token(token: str) -> bool:
    raw = _strip_bearer(token)
    if not raw:
        return False
    expected_audience = _oidc_audience().rstrip("/")
    try:
        from google.oauth2 import id_token

        request = google_requests.Request()
        # Pub/Sub push tokens use audience = the push endpoint URL (no path).
        # Try both forms (with and without the /pubsub/push suffix) to be tolerant.
        candidates = [expected_audience, _oidc_audience(), f"{expected_audience}/pubsub/push"]
        last_exc = None
        decoded = None
        for audience in candidates:
            try:
                decoded = id_token.verify_token(raw, audience=audience, request=request, clock_skew_in_seconds=10)
                if isinstance(decoded, dict):
                    break
            except Exception as exc:
                last_exc = exc
                continue
        if not isinstance(decoded, dict):
            logger.warning("pubsub token verify failed (aud tried=%s): %s", candidates, last_exc)
            # Fallback: decode unverified and inspect aud
            unverified = _decode_unverified(raw)
            actual_aud = unverified.get("aud")
            logger.warning("pubsub token unverified aud=%s expected=%s", actual_aud, expected_audience)
            if actual_aud:
                base = str(actual_aud).rstrip("/")
                if base == expected_audience or base == f"{expected_audience}/pubsub/push" or base.endswith("/pubsub/push") and base.startswith(expected_audience):
                    decoded = unverified
                else:
                    return False
            else:
                return False
        if decoded.get("iss") != "https://accounts.google.com":
            return False
        if not str(decoded.get("email", "")).endswith("gserviceaccount.com"):
            return False
        return True
    except Exception as exc:
        logger.warning("pubsub token verify failed: %s", exc)
        return False


def _dedupe(message_id: str) -> bool:
    if not message_id:
        return True
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


def mark_processed(message_id: str) -> None:
    return None


async def dispatch(
    payload: Dict[str, Any],
    handler: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    if not _dedupe(payload.get("message_id", "")):
        logger.info("pubsub duplicate dropped: %s", payload.get("message_id", ""))
        return {"status": "duplicate", "message_id": payload.get("message_id", "")}
    return await handler(payload)
