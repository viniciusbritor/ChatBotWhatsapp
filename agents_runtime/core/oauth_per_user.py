import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

import requests
from google.oauth2.credentials import Credentials

if TYPE_CHECKING:
    from google.cloud import firestore
else:
    try:
        from google.cloud import firestore
    except ImportError:
        firestore = None

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
TOKEN_REFRESH_BEFORE_SEC = int(os.getenv("OAUTH_REFRESH_BEFORE_SEC", "300"))


def _get_firestore():
    try:
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
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
    try:
        r = requests.post(
            token_uri,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
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
    return {
        "token": new_token,
        "refresh_token": body.get("refresh_token", refresh_token),
        "token_uri": token_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": body.get("scope", "").split() or None,
        "expiry": str(time.time() + body.get("expires_in", 3600)),
    }


def _persist_token(db, phone: str, token_data: Dict[str, Any]) -> None:
    try:
        db.collection("users").document(phone).set(
            {"google_oauth_token": token_data},
            merge=True,
        )
    except Exception as exc:
        logger.warning("oauth persist failed: %s", exc)


def get_user_oauth(phone: str) -> Optional[Dict[str, Any]]:
    db = _get_firestore()
    if db is None or not phone:
        return None
    try:
        doc = db.collection("users").document(phone).get()
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
    if _is_expired(token_data.get("expiry")) and refresh_token:
        refreshed = _refresh_token(
            token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            token_data.get("client_id", ""),
            token_data.get("client_secret", ""),
            refresh_token,
        )
        if refreshed:
            access_token = refreshed["token"]
            db = _get_firestore()
            if db is not None:
                merged = dict(token_data)
                merged.update(refreshed)
                _persist_token(db, phone, merged)
    expiry = token_data.get("expiry")
    try:
        expiry_dt = datetime.fromtimestamp(float(expiry)) if expiry else None
    except (TypeError, ValueError):
        expiry_dt = None
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", ""),
        client_secret=token_data.get("client_secret", ""),
        scopes=token_data.get("scopes") or [],
        expiry=expiry_dt,
    )
