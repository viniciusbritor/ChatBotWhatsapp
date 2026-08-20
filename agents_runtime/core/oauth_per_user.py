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
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "coherence-ominichannel-fs"
        from google.cloud import firestore
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("firestore unavailable for oauth per-user: %s", exc)
        return None


def _candidate_phones(phone: str) -> list:
    """Gera variacoes de formato de telefone para busca e persistencia robusta."""
    raw = str(phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return []
    candidates = [digits]
    if digits.startswith("55") and len(digits) > 10:
        candidates.append(digits[2:])
    else:
        candidates.append("55" + digits)
    if not raw.startswith("+") and raw:
        candidates.append("+" + digits)
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


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
    candidates = _candidate_phones(phone)
    target_docs = set()
    for p in candidates:
        try:
            doc = db.collection(OAUTH_USER_COLLECTION).document(p).get()
            if doc.exists:
                target_docs.add(p)
        except Exception:
            pass
    if not target_docs:
        target_docs.add(norm_phone)
    for target in target_docs:
        try:
            db.collection(OAUTH_USER_COLLECTION).document(target).set(
                {"google_oauth_token": persisted},
                merge=True,
            )
        except Exception as exc:
            logger.warning("oauth persist failed for %s: %s", target, exc)


def get_user_oauth(phone: str) -> Optional[Dict[str, Any]]:
    db = _get_firestore()
    if db is None:
        return None
    candidates = _candidate_phones(phone)
    for p in candidates:
        try:
            doc = db.collection(OAUTH_USER_COLLECTION).document(p).get()
            if doc.exists:
                token = (doc.to_dict() or {}).get("google_oauth_token")
                if token and isinstance(token, dict) and (token.get("token") or token.get("access_token") or token.get("refresh_token")):
                    return token
        except Exception as exc:
            logger.warning("oauth fetch failed for %s: %s", p, exc)
    return None


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

    GUARDRAIL §0.7 (19/08/2026): defesa em profundidade — checa
    is_user_connected() antes de retornar credentials, garantindo
    que tokens apos "desconectar" no Portal NAO sejam usados.
    """
    if not is_user_connected(phone):
        logger.info(
            "get_user_credentials blocked: user disconnected phone_suffix=%s",
            re.sub(r"\D", "", str(phone or ""))[-4:],
        )
        return None
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


def is_user_connected(phone: str) -> bool:
    """Verifica se o usuario tem token OAuth Google ativo no Firestore.

    GUARDRAIL §0.7 (19/08/2026): protege contra uso de tokens apos
    desconexao no Portal. Antes desta funcao, get_user_credentials
    retornava o token mesmo apos o usuario "desconectar" na UI
    (que apenas mudava o state React sem chamar backend).
    """
    token_data = get_user_oauth(phone)
    if not token_data:
        return False
    if not token_data.get("token") and not token_data.get("refresh_token"):
        return False
    return True


def revoke_google_token(token: str, timeout: int = 10) -> bool:
    """Revoga um token (access ou refresh) no Google OAuth.

    Endpoint: POST https://oauth2.googleapis.com/revoke?token=<token>
    Resposta 200 = sucesso, retorna True.
    Resposta 400 = token invalido/expirado, ainda retorna True (ja nao serve).
    Falha de rede = retorna False (chamador decide se aborta).
    """
    if not token:
        return False
    try:
        r = requests.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": token},
            timeout=timeout,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # 200 = sucesso; 400 = ja expirado/revogado (considerar sucesso)
        return r.status_code in (200, 400)
    except Exception as exc:
        logger.warning("oauth revoke failed for token suffix=%s: %s", token[-6:], exc)
        return False


def delete_oauth_token(phone: str) -> bool:
    """Apaga o token OAuth do usuario no Firestore.

    GUARDRAIL §0.7 (19/08/2026): o Portal "desconectar" deve chamar
    isto para invalidar de fato o token. Sem isto, o cache _calendar_services
    e o token em si continuam validos e a Jennifier continua a acessar Calendar/Drive/Gmail.
    Retorna True se apagou com sucesso, False se ja nao existia ou Firestore indisponivel.
    """
    from google.cloud import firestore as _fs  # local import para ciclo

    db = _get_firestore()
    if db is None:
        logger.warning("delete_oauth_token: firestore unavailable for phone=%s", phone)
        return False
    norm_phone = re.sub(r"\D", "", str(phone or ""))
    if not norm_phone:
        return False
    candidates = _candidate_phones(phone)
    deleted_any = False
    for target in candidates:
        try:
            doc_ref = db.collection(OAUTH_USER_COLLECTION).document(target)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                if "google_oauth_token" in data or "google_oauth_linked_at" in data:
                    doc_ref.update({
                        "google_oauth_token": _fs.DELETE_FIELD,
                        "google_oauth_linked_at": _fs.DELETE_FIELD,
                        "google_oauth_revoked_at": _fs.SERVER_TIMESTAMP,
                    })
                    logger.info("oauth_token_deleted phone=%s target=%s", phone, target)
                    deleted_any = True
        except Exception as exc:
            logger.warning("delete_oauth_token failed for %s: %s", target, exc)
    return deleted_any


def revoke_user_oauth(phone: str) -> Dict[str, Any]:
    """Revoga todos os tokens do usuario no Google + apaga do Firestore.

    Combina revoke_google_token (revoga access+refresh) + delete_oauth_token
    (limpa Firestore) + clear_all_google_caches (limpa caches em memoria).
    Retorna status detalhado para auditoria.
    """
    token_data = get_user_oauth(phone)
    access_revoked = False
    refresh_revoked = False
    if token_data:
        access_revoked = revoke_google_token(token_data.get("token") or "")
        if token_data.get("refresh_token") and token_data.get("refresh_token") != token_data.get("token"):
            refresh_revoked = revoke_google_token(token_data.get("refresh_token"))
        else:
            refresh_revoked = access_revoked
    deleted = delete_oauth_token(phone)
    caches_cleared = clear_all_google_caches(phone)
    return {
        "phone": phone,
        "access_revoked": access_revoked,
        "refresh_revoked": refresh_revoked,
        "firestore_deleted": deleted,
        "caches_cleared": caches_cleared,
        "revoked_at": now_brt().isoformat(),
    }


def clear_all_google_caches(phone: str) -> Dict[str, bool]:
    """GUARDRAIL §0.7 (19/08/2026): limpa caches de todos os servicos Google
    em todos os tools apos desconexao. Cada tool expoe sua propria funcao
    clear_user_cache; aqui agregamos o resultado para o caller.
    Retorna dict {service: cleared} para auditoria.
    """
    import importlib

    services = [
        ("calendar", "tools.google_calendar"),
        ("drive", "tools.google_drive"),
        ("gmail", "tools.google_gmail"),
        ("tasks", "tools.google_tasks"),
        ("people", "tools.google_people"),
    ]
    cleared: Dict[str, bool] = {}
    for name, module_path in services:
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, "clear_user_cache", None)
            if fn is not None:
                cleared[name] = bool(fn(phone))
        except Exception as exc:
            logger.debug("clear_user_cache skipped for %s: %s", name, exc)
            cleared[name] = False
    return cleared
