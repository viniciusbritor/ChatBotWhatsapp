"""Magic link token generation and verification for self-service WhatsApp user onboarding."""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def _get_signing_key() -> bytes:
    key = os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "") or os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
    return key.encode("utf-8")


def generate_magic_link_token(phone: str, ttl_seconds: int = 86400 * 7) -> str:
    """Gera um token assinado (HMAC-SHA256) para o phone com validade configurável (padrão 7 dias)."""
    canonical = "".join(c for c in str(phone or "") if c.isdigit())
    payload = {
        "phone": canonical,
        "phone_number": canonical,
        "sub": canonical,
        "role": "agent_user",
        "type": "magic_link",
        "exp": int(time.time()) + ttl_seconds,
        "iat": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    sig = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"ml.{payload_b64}.{sig_b64}"


def verify_magic_link_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida um magic link token. Retorna dict de claims se válido, ou None."""
    if not token or not isinstance(token, str) or not token.startswith("ml."):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    _, payload_b64, sig_b64 = parts
    try:
        expected_sig = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")
        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            return None
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += "=" * (4 - rem)
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            return None
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception as exc:
        logger.debug("verify_magic_link_token failed: %s", exc)
        return None


def build_magic_link_url(phone: str, base_url: str = "") -> str:
    """Constrói a URL completa para o usuário acessar suas conexões na Landing Page de Onboarding."""
    if not base_url:
        base_url = os.getenv("PORTAL_PUBLIC_URL", "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app")
    token = generate_magic_link_token(phone)
    canonical = "".join(c for c in str(phone or "") if c.isdigit())
    clean_base = base_url.rstrip("/")
    return f"{clean_base}/a/{canonical}/conectar?token={token}"
