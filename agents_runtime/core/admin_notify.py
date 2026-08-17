"""Admin Notification & WhatsApp Approval Workflow.

GUARDRAIL (17/08/2026): aprovação por mensagem explícita no WhatsApp.
Admin responde "OK, APROVADO" ou "NÃO, REJEITADO" direto no chat,
substituindo o link HMAC como mecanismo primário.

O link HMAC continua disponível como fallback (Portal Rich-Path).
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

from core.approval_store import create_pending_approval
from core.timezone import now_brt

logger = logging.getLogger(__name__)

_NOTIFIED_PHONES_CACHE: dict[str, float] = {}
NOTIFY_COOLDOWN_SEC = 300  # 5 minutos entre alertas do mesmo numero
OAUTH_LINKED_NOTIFY_COOLDOWN_SEC = 86400  # 24h entre alertas do mesmo phone (caso serio)


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
    """Envia solicitacao ao admin com instrucoes para responder por WhatsApp.

    GUARDRAIL (17/08/2026): substitui o link HMAC por mensagem explicita.
    Admin responde DIRETO no WhatsApp (sem sair do app).

    Returns:
        True se enviou mensagem, False caso contrario.
    """
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    if not sender_name or sender_name.strip().lower() in ("user", "usuario", "usuário", "none", "null") or sender_name.startswith("+") or sender_name.isdigit():
        try:
            from core.owner_name import resolve_owner_name
            sender_name = resolve_owner_name(clean_phone)
        except Exception:
            sender_name = ""
    if not clean_phone:
        logger.warning(
            "notify_admin_skipped_invalid_phone phone=%s",
            phone,
            extra={"event_name": "notify_admin_skipped_invalid_phone", "reason": "empty_or_invalid"},
        )
        return False

    # Evita flood de notificacoes para o admin
    now = time.time()
    last_notified = _NOTIFIED_PHONES_CACHE.get(clean_phone, 0)
    if (now - last_notified) < NOTIFY_COOLDOWN_SEC:
        logger.info(
            "notify_admin_skipped_cooldown phone=%s seconds_until_retry=%d",
            clean_phone,
            int(NOTIFY_COOLDOWN_SEC - (now - last_notified)),
            extra={"event_name": "notify_admin_skipped_cooldown", "reason": "cooldown_active"},
        )
        return False
    _NOTIFIED_PHONES_CACHE[clean_phone] = now

    from agent_loader import resolve_owner_phone
    admin_phone = resolve_owner_phone()
    if not admin_phone:
        logger.warning(
            "notify_admin_skipped_no_admin_phone phone=%s instance=%s",
            clean_phone, instance,
            extra={"event_name": "notify_admin_skipped_no_admin_phone", "reason": "resolve_owner_phone_returned_none"},
        )
        return False
    if admin_phone == clean_phone:
        logger.warning(
            "notify_admin_skipped_same_phone phone=%s admin_phone=%s",
            clean_phone, admin_phone,
            extra={"event_name": "notify_admin_skipped_same_phone", "reason": "user_is_admin_themselves"},
        )
        return False

    # Cria registro pending no Firestore e obtem run_id
    # (create_pending_approval importado no topo do modulo)
    name_display = sender_name.strip() if sender_name else "Usuario"
    intent = "unknown"  # sera inferido do context na fase 5
    try:
        run_id = create_pending_approval(
            phone=clean_phone,
            name=name_display,
            intent=intent,
            message=message_text,
        )
    except Exception as exc:
        logger.warning(
            "create_pending_approval_failed phone=%s exc=%s",
            clean_phone, exc,
            extra={"event_name": "create_pending_approval_failed"},
        )
        return False

    snippet = message_text.strip().replace("\n", " ")[:150]
    if len(snippet) == 150:
        snippet += "..."

    # Mensagem dual-path: fast (WhatsApp) + rich (Portal)
    portal_url = "portal.coherence-ai.com.br/admin/approvals"
    msg = (
        f"🔔 *Nova Solicitação de Acesso*\n\n"
        f"👤 *Nome:* {name_display}\n"
        f"📱 *Telefone:* +{clean_phone}\n"
        f"💬 *Mensagem:* \"{snippet}\"\n\n"
        f"*Responda com:*\n"
        f"✅ *OK, APROVADO*\n"
        f"❌ *NÃO, REJEITADO*\n\n"
        f"💡 Ou responda 'ok {run_id}' para uma específica\n"
        f"🌐 Ou gerencie em lote: {portal_url}\n\n"
        f"Run ID: {run_id}"
    )

    try:
        from core.evolution_client import send_text
        success = await send_text(
            phone=admin_phone,
            text=msg,
            instance=instance,
        )
        if success:
            logger.info(
                "notify_admin_send_ok phone=%s admin_phone=%s run_id=%s instance=%s",
                clean_phone, admin_phone, run_id, instance,
                extra={
                    "event_name": "notify_admin_send_ok",
                    "decision": "notified",
                    "run_id": run_id,
                },
            )
            return True
        logger.warning(
            "notify_admin_send_returned_false phone=%s admin_phone=%s run_id=%s instance=%s",
            clean_phone, admin_phone, run_id, instance,
            extra={"event_name": "notify_admin_send_failed", "decision": "send_returned_false"},
        )
        return False
    except Exception as exc:
        logger.warning(
            "notify_admin_send_exception phone=%s run_id=%s exc=%s",
            clean_phone, run_id, exc,
            extra={"event_name": "notify_admin_send_failed", "reason": "exception"},
        )
        return False


def create_unblock_token(phone: str) -> str:
    """Gera token assinado via HMAC SHA-256 para desbloqueio/liberação de usuário."""
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    secret = _state_secret()
    if not clean_phone or not secret:
        return ""
    payload = {
        "phone": clean_phone,
        "action": "unblock_user",
        "expires_at": int(time.time()) + (7 * 24 * 3600),  # 7 dias
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


def parse_unblock_token(token: str) -> Optional[str]:
    """Valida o token assinado de desbloqueio e retorna o telefone liberado."""
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
        if payload.get("action") != "unblock_user":
            return None
        return re.sub(r"\D", "", str(payload.get("phone", "")))
    except Exception as exc:
        logger.warning("parse_unblock_token failed: %s", exc)
        return None


def generate_unblock_url(phone: str) -> str:
    """Gera a URL completa de liberacao/desbloqueio para o WhatsApp do Admin."""
    base = os.getenv(
        "AGENTS_RUNTIME_PUBLIC_URL",
        "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app",
    ).rstrip("/")
    token = create_unblock_token(phone)
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    return f"{base}/admin/unblock-user?phone={clean_phone}&token={token}"


async def notify_admin_flood_alert(
    phone: str,
    sender_name: str = "",
    group_name: str = "",
    burst_count: int = 0,
    cost_usd: float = 0.0,
    cost_brl: float = 0.0,
    instance: str = "Jennifer",
    text_preview: str = "",
) -> bool:
    """Envia alerta de seguranca e FinOps no WhatsApp do Admin quando um ataque/flood e bloqueado."""
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    if not clean_phone:
        return False

    now = time.time()
    cache_key = f"flood_{clean_phone}"
    last_notified = _NOTIFIED_PHONES_CACHE.get(cache_key, 0)
    if (now - last_notified) < NOTIFY_COOLDOWN_SEC:
        logger.info("Flood alert skipped for %s (cooldown active)", clean_phone)
        return False
    _NOTIFIED_PHONES_CACHE[cache_key] = now

    from agent_loader import resolve_owner_phone
    admin_phone = resolve_owner_phone()
    if not admin_phone or admin_phone == clean_phone:
        return False

    unblock_url = generate_unblock_url(clean_phone)
    name_display = sender_name.strip() if sender_name else "Usuário/Bot"
    origin_display = f"Grupo: {group_name}" if group_name and not group_name.endswith("@s.whatsapp.net") else "Conversa Privada (DM)"
    snippet = (text_preview or "").strip().replace("\n", " ")[:120]

    msg = (
        f"🚨 *ALERTA DE SEGURANÇA & FINOPS — FLOOD / BOT DETECTADO*\n\n"
        f"Um usuário disparou uma rajada sequencial de mensagens e foi *bloqueado automaticamente* para proteger seus créditos e a estabilidade do sistema.\n\n"
        f"👤 *Contato:* {name_display}\n"
        f"📱 *Telefone:* +{clean_phone}\n"
        f"👥 *Origem:* {origin_display}\n"
        f"📊 *Mensagens na Rajada:* {burst_count} mensagens\n"
        f"💰 *Custo Estimado Gerado:* {cost_usd:.4f} USD (~{cost_brl:.2f} reais)\n"
        f"💬 *Última Mensagem:* \"{snippet}\"\n"
        f"⚙️ *Instância:* {instance}\n\n"
        f"A Jennifer parou de responder a este contato imediatamente.\n"
        f"Para *liberar o usuário* a voltar a interagir, clique no link:\n"
        f"👉 {unblock_url}"
    )

    try:
        from core.evolution_client import send_text
        success = await send_text(
            phone=admin_phone,
            text=msg,
            instance=instance,
        )
        if success:
            logger.info("Admin notified of flood attack from %s", clean_phone)
            return True
    except Exception as exc:
        logger.warning("Failed to notify admin of flood attack: %s", exc)
    return False


async def notify_admin_oauth_linked_without_approval(
    phone: str,
    email: str = "",
    instance: str = "Jennifer",
) -> bool:
    """Alerta serio: alguem completou OAuth Google SEM estar pre-aprovado pelo admin.

    GUARDRAIL §0.7 (16/08/2026): este caminho era o Vetor #1 de auto-aprovacao
    antes do fix. Apos o fix, o OAuth nao aprova mais - mas o token ESTA salvo.
    Precisamos do admin revisar e aprovar/revogar manualmente.

    Cooldown: 24h por phone (caso de seguranca, nao spam).
    """
    clean_phone = re.sub(r"\D", "", str(phone or ""))
    if not clean_phone:
        return False

    now = time.time()
    cache_key = f"oauth_linked_{clean_phone}"
    last_notified = _NOTIFIED_PHONES_CACHE.get(cache_key, 0)
    if (now - last_notified) < OAUTH_LINKED_NOTIFY_COOLDOWN_SEC:
        logger.info(
            "oauth_linked_alert_cooldown phone=%s seconds_until_retry=%d",
            clean_phone,
            int(OAUTH_LINKED_NOTIFY_COOLDOWN_SEC - (now - last_notified)),
            extra={"event_name": "oauth_linked_alert_cooldown"},
        )
        return False
    _NOTIFIED_PHONES_CACHE[cache_key] = now

    from agent_loader import resolve_owner_phone
    admin_phone = resolve_owner_phone()
    if not admin_phone or admin_phone == clean_phone:
        return False

    email_display = email.strip() if email else "(sem email vinculado)"
    msg = (
        f"\u26a0\ufe0f *OAuth vinculado SEM aprova\u00e7\u00e3o pr\u00e9via*\n\n"
        f"Um contato acabou de vincular a conta Google abaixo, **mas ainda n\u00e3o foi aprovado por voc\u00ea** "
        f"como secret\u00e1ria pessoal. O token OAuth foi salvo, mas o usu\u00e1rio N\u00c3O tem acesso \u00e0 Jennifer at\u00e9 sua aprova\u00e7\u00e3o.\n\n"
        f"\U0001f464 *Telefone:* +{clean_phone}\n"
        f"\U0001f4e7 *Email Google:* {email_display}\n"
        f"\u2699\ufe0f *Inst\u00e2ncia:* {instance}\n\n"
        f"Se voc\u00ea n\u00e3o reconhece este contato, ignore. Para liberar o acesso, use o Painel Admin "
        f"(/admin/users/{clean_phone}) e defina `is_approved: True`.\n\n"
        f"_Este \u00e9 um alerta do Guardrail \u00a70.7 \u2014 antes do fix, o OAuth auto-aprovava o usu\u00e1rio. "
        f"Agora exige sua decis\u00e3o expl\u00edcita._"
    )

    try:
        from core.evolution_client import send_text
        success = await send_text(
            phone=admin_phone,
            text=msg,
            instance=instance,
        )
        if success:
            logger.info(
                "oauth_linked_alert_sent phone=%s admin_phone=%s email=%s",
                clean_phone, admin_phone, email,
                extra={"event_name": "oauth_linked_alert_sent"},
            )
            return True
    except Exception as exc:
        logger.warning("notify_admin_oauth_linked failed: %s", exc)
    return False

