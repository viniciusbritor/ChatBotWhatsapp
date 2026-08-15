"""Admin Notification & 1-Click WhatsApp Approval Workflow.

Notifica o WhatsApp do Admin (Vinicius) quando um usuário não autorizado
solicita acesso à Jennifer, gerando link assinado de aprovação em 1 clique.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import Optional

from core.timezone import now_brt

logger = logging.getLogger(__name__)

_NOTIFIED_PHONES_CACHE: dict[str, float] = {}
NOTIFY_COOLDOWN_SEC = 300  # 5 minutos entre alertas do mesmo numero


def _state_secret() -> str:
    key = os.getenv("AGENTS_RUNTIME_SA_TOKEN_SECRET", "") or os.getenv("OAUTH_STATE_SECRET", "") or os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
    return key


def create_approval_token(phone: str) -> str:
    """Gera token assinado via HMAC SHA-256 para aprovação de acesso."""
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    secret = _state_secret()
    if not clean_phone or not secret:
        return ""
    payload = {
        "phone": clean_phone,
        "role": "analyst",
        "action": "approve_user",
        "expires_at": int(time.time()) + (30 * 24 * 3600),  # 30 dias
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


def parse_approval_token(token: str) -> Optional[str]:
    """Valida o token assinado e retorna o telefone aprovado."""
    secret = _state_secret()
    if not token or not secret or "." not in token:
        return None
    encoded, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if int(payload.get("expires_at", 0)) < int(time.time()):
            return None
        if payload.get("action") != "approve_user":
            return None
        return re.sub(r"\D", "", str(payload.get("phone", "")))
    except Exception as exc:
        logger.warning("parse_approval_token failed: %s", exc)
        return None


def generate_approval_url(phone: str) -> str:
    """Gera a URL completa de aprovacao para o WhatsApp do Admin."""
    base = os.getenv(
        "AGENTS_RUNTIME_PUBLIC_URL",
        "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app",
    ).rstrip("/")
    token = create_approval_token(phone)
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    return f"{base}/admin/approve-user?phone={clean_phone}&token={token}"


async def notify_admin_access_request(
    phone: str,
    sender_name: str = "",
    message_text: str = "",
    instance: str = "Jennifer",
) -> bool:
    """Envia notificacao no WhatsApp do Admin quando um visitante pede acesso."""
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    if not clean_phone:
        return False

    # Evita flood de notificacoes para o admin
    now = time.time()
    last_notified = _NOTIFIED_PHONES_CACHE.get(clean_phone, 0)
    if (now - last_notified) < NOTIFY_COOLDOWN_SEC:
        logger.info("Admin notification skipped for %s (cooldown active)", clean_phone)
        return False
    _NOTIFIED_PHONES_CACHE[clean_phone] = now

    from agent_loader import resolve_owner_phone
    admin_phone = resolve_owner_phone()
    if not admin_phone or admin_phone == clean_phone:
        return False

    approval_url = generate_approval_url(clean_phone)
    name_display = sender_name.strip() if sender_name and sender_name != "user" else "Novo Contato"
    snippet = message_text.strip().replace("\n", " ")[:150]
    if len(snippet) == 150:
        snippet += "..."

    msg = (
        f"🔔 *Solicitação de Acesso à Jennifer*\n\n"
        f"👤 *Nome:* {name_display}\n"
        f"📱 *Telefone:* +{clean_phone}\n"
        f"💬 *Mensagem:* \"{snippet}\"\n\n"
        f"Para liberar o acesso como *Analista*, clique no link abaixo:\n"
        f"👉 {approval_url}"
    )

    try:
        from core.evolution_client import send_text
        success = await send_text(
            phone=admin_phone,
            text=msg,
            instance=instance,
        )
        if success:
            logger.info("Admin notified of access request from %s", clean_phone)
            return True
    except Exception as exc:
        logger.warning("Failed to notify admin: %s", exc)
    return False
