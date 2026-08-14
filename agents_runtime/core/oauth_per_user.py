import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from core.timezone import now_brt

import requests
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
TOKEN_REFRESH_BEFORE_SEC = int(os.getenv("OAUTH_REFRESH_BEFORE_SEC", "300"))
OAUTH_STATE_TTL_SEC = int(os.getenv("OAUTH_STATE_TTL_SEC", str(7 * 24 * 60 * 60)))
OAUTH_USER_COLLECTION = os.getenv("OAUTH_USER_COLLECTION", "usuarios")
_CACHED_CLIENT_ID: Optional[str] = None
_CACHED_CLIENT_SECRET: Optional[str] = None


def _oauth_client_id() -> str:
    global _CACHED_CLIENT_ID
    if _CACHED_CLIENT_ID:
        return _CACHED_CLIENT_ID
    val = os.getenv("OAUTH_CLIENT_ID", "").strip()
    if val:
        _CACHED_CLIENT_ID = val
        return val
    _CACHED_CLIENT_ID = "894828119087-goo6lcl6vgm5bdq5qgafscb8qbr4ueet.apps.googleusercontent.com"
    return _CACHED_CLIENT_ID


def _oauth_client_secret() -> str:
    global _CACHED_CLIENT_SECRET
    if _CACHED_CLIENT_SECRET:
        return _CACHED_CLIENT_SECRET
    val = os.getenv("OAUTH_CLIENT_SECRET", "").strip()
    if val:
        _CACHED_CLIENT_SECRET = val
        return val
    try:
        from core.secrets import get_secret
        sec = get_secret("oauth-client-secret") or get_secret("OAUTH_CLIENT_SECRET") or ""
        if sec:
            _CACHED_CLIENT_SECRET = sec
            return sec
    except Exception:
        pass
    return ""


def _state_secret() -> str:
    return (os.getenv("OAUTH_STATE_SECRET") or _oauth_client_secret()).strip()


def create_oauth_state(phone: str) -> str:
    normalized_phone = re.sub(r"\D", "", phone)
    secret = _state_secret()
    if not normalized_phone or not secret:
        raise ValueError("oauth_state_configuration_invalid")
    payload = {
        "phone": normalized_phone,
        "nonce": secrets.token_urlsafe(16),
        "expires_at": int(time.time()) + OAUTH_STATE_TTL_SEC,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


def parse_oauth_state(state: str) -> Optional[str]:
    secret = _state_secret()
    if not state or not secret or "." not in state:
        return None
    encoded, signature = state.rsplit(".", 1)
    expected = hmac.new(
        secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        phone = re.sub(r"\D", "", str(payload.get("phone", "")))
        expires_at = int(payload.get("expires_at", 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not phone or expires_at < int(time.time()):
        return None
    return phone


def _get_firestore():
    try:
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        from google.cloud import firestore
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("firestore unavailable for oauth per-user: %s", exc)
        return None


def _is_expired(expiry: Any) -> bool:
    try:
        expiry_ts = float(expiry)
    except (TypeError, ValueError):
        return True
    return (expiry_ts - TOKEN_REFRESH_BEFORE_SEC) <= time.time()


def _refresh_token(
    token_uri: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    effective_client_id = client_id or _oauth_client_id()
    effective_client_secret = client_secret or _oauth_client_secret()
    if not effective_client_id or not effective_client_secret or not refresh_token:
        return None
    try:
        r = requests.post(
            token_uri,
            data={
                "client_id": effective_client_id,
                "client_secret": effective_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=timeout,
        )
        body = r.json()
    except Exception as exc:
        logger.warning("oauth refresh failed: %s", exc)
        return None
    if "error" in body:
        logger.warning("oauth refresh error: %s", body.get("error"))
        return None
    new_token = body.get("access_token")
    if not new_token:
        return None
    result = {
        "token": new_token,
        "refresh_token": body.get("refresh_token", refresh_token),
        "token_uri": token_uri,
        "expiry": str(time.time() + body.get("expires_in", 3600)),
    }
    scopes = body.get("scope", "").split()
    if scopes:
        result["scopes"] = scopes
    return result


def _persist_token(db, phone: str, token_data: Dict[str, Any]) -> None:
    norm_phone = re.sub(r"\D", "", str(phone or ""))
    if not norm_phone:
        return
    persisted = {
        key: value
        for key, value in token_data.items()
        if key not in {"client_id", "client_secret"}
    }
    persisted["updated_at"] = now_brt().isoformat()
    try:
        db.collection(OAUTH_USER_COLLECTION).document(norm_phone).set(
            {"google_oauth_token": persisted},
            merge=True,
        )
    except Exception as exc:
        logger.warning("oauth persist failed: %s", exc)


def get_user_oauth(phone: str) -> Optional[Dict[str, Any]]:
    db = _get_firestore()
    norm_phone = re.sub(r"\D", "", str(phone or ""))
    if db is None or not norm_phone:
        return None
    try:
        doc = db.collection(OAUTH_USER_COLLECTION).document(norm_phone).get()
    except Exception as exc:
        logger.warning("oauth fetch failed: %s", exc)
        return None
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get("google_oauth_token")


def get_valid_user_token(phone: str) -> Optional[str]:
    """Return a valid access_token for the user, refreshing if expired.

    Returns None if the user has not connected or refresh failed.
    """
    token_data = get_user_oauth(phone)
    if not token_data:
        return None
    if not _is_expired(token_data.get("expiry")):
        return token_data.get("token")
    refresh = token_data.get("refresh_token")
    if not refresh:
        return None
    new_token = _refresh_token(
        token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        token_data.get("client_id", ""),
        token_data.get("client_secret", ""),
        refresh,
    )
    if not new_token:
        return None
    db = _get_firestore()
    if db is not None:
        merged = dict(token_data)
        merged.update(new_token)
        _persist_token(db, phone, merged)
    return new_token.get("token")


def get_user_credentials(phone: str) -> Optional[Credentials]:
    """Return a valid google.oauth2.credentials.Credentials for the user.

    Refreshes the access token if expired, persists the new token, and returns
    a Credentials object that can be used with googleapiclient.discovery.build.
    Returns None if the user has not connected or refresh failed.
    """
    token_data = get_user_oauth(phone)
    if not token_data:
        return None
    access_token = token_data.get("token")
    refresh_token = token_data.get("refresh_token")
    if not access_token:
        return None
    if _is_expired(token_data.get("expiry")):
        if not refresh_token:
            return None
        refreshed = _refresh_token(
            token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            token_data.get("client_id", ""),
            token_data.get("client_secret", ""),
            refresh_token,
        )
        if not refreshed:
            return None
        access_token = refreshed["token"]
        merged = dict(token_data)
        merged.update(refreshed)
        token_data = merged
        db = _get_firestore()
        if db is not None:
            _persist_token(db, phone, merged)
    expiry = token_data.get("expiry")
    try:
        dt = datetime.fromtimestamp(float(expiry), tz=timezone.utc) if expiry else None
        expiry_dt = dt.replace(tzinfo=None) if dt else None
    except (TypeError, ValueError):
        expiry_dt = None
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id") or _oauth_client_id(),
        client_secret=token_data.get("client_secret") or _oauth_client_secret(),
        scopes=token_data.get("scopes") or [],
        expiry=expiry_dt,
    )
