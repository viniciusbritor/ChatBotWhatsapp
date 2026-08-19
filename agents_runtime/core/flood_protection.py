"""Anti-Flood, Anti-DDoS, Circuit Breaker & FinOps Shield.

Protege o sistema contra ataques de flood de mensagens, bots repetitivos
e consumo abusivo de tokens em grupos e DMs do WhatsApp.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core.pricing import estimate_cost_usd
from core.timezone import now_brt

logger = logging.getLogger(__name__)

# Configurações de Janela Deslizante (Rate Limiting)
FLOOD_WINDOW_SEC = int(os.getenv("FLOOD_WINDOW_SEC", "60"))
FLOOD_BURST_THRESHOLD = int(os.getenv("FLOOD_BURST_THRESHOLD", "5"))
FLOOD_EXTENDED_WINDOW_SEC = int(os.getenv("FLOOD_EXTENDED_WINDOW_SEC", "180"))
FLOOD_EXTENDED_BURST_THRESHOLD = int(os.getenv("FLOOD_EXTENDED_BURST_THRESHOLD", "10"))

# Taxa de conversão USD -> BRL para relatórios de FinOps
USD_TO_BRL_RATE = float(os.getenv("USD_TO_BRL_RATE", "5.70"))

# Caches locais em memória
_USER_MESSAGE_TIMESTAMPS: Dict[str, List[float]] = {}
_QUARANTINE_CACHE: Dict[str, Tuple[bool, float]] = {}  # phone -> (is_quarantined, cached_at)
_CACHE_LOCK = threading.RLock()
_QUARANTINE_CACHE_TTL = 30.0  # 30 segundos


def _canonical_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) == 11 and digits.startswith("55"):
        return digits
    if len(digits) in (10, 11) and not digits.startswith("55"):
        return f"55{digits}"
    return digits


def _get_firestore_client():
    from google.cloud import firestore
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "coherence-ominichannel-fs"
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        return firestore.Client(project=project or "demo-project")
    return firestore.Client(project=project)


# Whitelist de numeros que NUNCA entram em quarentena (Bots de instancia e Administradores)
_STATIC_WHITELIST_PHONES = {
    "5511917389901",  # Chip da Jennifer (Bot)
    "11917389901",
    "5511966830020",  # Vinicius (Owner Master)
    "11966830020",
}


def _is_whitelisted(phone: str) -> bool:
    """Verifica se o numero pertence ao bot ou a um administrador master."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return False
    if canonical in _STATIC_WHITELIST_PHONES:
        return True
    digits_only = "".join(c for c in canonical if c.isdigit())
    if digits_only in _STATIC_WHITELIST_PHONES or ("55" + digits_only) in _STATIC_WHITELIST_PHONES:
        return True
    return False


def is_user_quarantined(phone: str) -> bool:
    """Verifica se o usuário está em quarentena (bloqueado por flood/segurança)."""
    canonical = _canonical_phone(phone)
    if not canonical or _is_whitelisted(canonical):
        return False

    now = time.time()
    with _CACHE_LOCK:
        cached = _QUARANTINE_CACHE.get(canonical)
        if cached and (now - cached[1]) < _QUARANTINE_CACHE_TTL:
            return cached[0]

    db = _get_firestore_client()
    if db is None:
        return False

    try:
        doc = db.collection("usuarios").document(canonical).get(timeout=3)
        if not doc.exists:
            with _CACHE_LOCK:
                _QUARANTINE_CACHE[canonical] = (False, now)
            return False

        data = doc.to_dict() or {}
        is_quarantined = bool(data.get("is_quarantined", False))
        with _CACHE_LOCK:
            _QUARANTINE_CACHE[canonical] = (is_quarantined, now)
        return is_quarantined
    except Exception as exc:
        logger.warning("is_user_quarantined check failed for %s: %s", canonical, exc)
        return False


def quarantine_user(
    phone: str,
    reason: str = "flood_attack_detected",
    group_id: str = "",
    burst_count: int = 0,
    instance: str = "Jennifer",
) -> None:
    """Coloca o usuário em quarentena no Firestore e no cache local."""
    canonical = _canonical_phone(phone)
    if not canonical or _is_whitelisted(canonical):
        logger.info("quarantine_user skipped for whitelisted phone=%s", canonical)
        return

    now_iso = now_brt().isoformat()
    with _CACHE_LOCK:
        _QUARANTINE_CACHE[canonical] = (True, time.time())

    db = _get_firestore_client()
    if db is None:
        return

    try:
        updates = {
            "is_quarantined": True,
            "quarantine_reason": reason,
            "quarantine_group": group_id,
            "quarantined_at": now_iso,
            "quarantine_burst_count": burst_count,
            "updated_at": now_iso,
        }
        db.collection("usuarios").document(canonical).set(updates, merge=True)
        logger.info(
            "User quarantined phone=%s reason=%s burst_count=%d group=%s",
            canonical,
            reason,
            burst_count,
            group_id,
        )
    except Exception as exc:
        logger.error("quarantine_user failed for %s: %s", canonical, exc)


def unquarantine_user(phone: str) -> bool:
    """Remove o usuário da quarentena e limpa seu histórico recente de mensagens."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return False

    with _CACHE_LOCK:
        _QUARANTINE_CACHE[canonical] = (False, time.time())
        _USER_MESSAGE_TIMESTAMPS.pop(canonical, None)

    db = _get_firestore_client()
    if db is None:
        return True

    try:
        updates = {
            "is_quarantined": False,
            "quarantine_reason": "",
            "quarantine_group": "",
            "unquarantined_at": now_brt().isoformat(),
            "updated_at": now_brt().isoformat(),
        }
        db.collection("usuarios").document(canonical).set(updates, merge=True)
        logger.info("User unquarantined successfully phone=%s", canonical)
        return True
    except Exception as exc:
        logger.error("unquarantine_user failed for %s: %s", canonical, exc)
        return False


def check_and_record_message(
    phone: str,
    group_id: str = "",
    instance: str = "Jennifer",
    text: str = "",
) -> Tuple[bool, Dict[str, Any]]:
    """Verifica se a mensagem atual ultrapassa os limites de flood da janela deslizante.

    Retorna:
        (is_blocked: bool, flood_details: dict)
    """
    canonical = _canonical_phone(phone)
    if not canonical or _is_whitelisted(canonical):
        return False, {}

    # 1. Se já está em quarentena, bloqueia direto
    if is_user_quarantined(canonical):
        return True, {"already_quarantined": True, "phone": canonical}

    now = time.time()
    with _CACHE_LOCK:
        timestamps = _USER_MESSAGE_TIMESTAMPS.get(canonical, [])
        # Poda timestamps com mais de 180s
        cutoff = now - FLOOD_EXTENDED_WINDOW_SEC
        valid_timestamps = [t for t in timestamps if t >= cutoff]
        valid_timestamps.append(now)
        _USER_MESSAGE_TIMESTAMPS[canonical] = valid_timestamps

        # Checa janela curta (ex: 5 msgs em 60s)
        short_cutoff = now - FLOOD_WINDOW_SEC
        short_burst = len([t for t in valid_timestamps if t >= short_cutoff])

        # Checa janela estendida (ex: 10 msgs em 180s)
        extended_burst = len(valid_timestamps)

    is_flood = (short_burst >= FLOOD_BURST_THRESHOLD) or (extended_burst >= FLOOD_EXTENDED_BURST_THRESHOLD)

    if is_flood:
        burst_count = max(short_burst, extended_burst)
        quarantine_user(
            canonical,
            reason="flood_attack_detected",
            group_id=group_id,
            burst_count=burst_count,
            instance=instance,
        )
        metrics = get_user_finops_metrics(canonical)
        flood_details = {
            "quarantined": True,
            "phone": canonical,
            "burst_count": burst_count,
            "group_id": group_id,
            "instance": instance,
            "total_messages": metrics.get("total_messages", burst_count),
            "estimated_cost_usd": metrics.get("estimated_cost_usd", 0.0),
            "estimated_cost_brl": metrics.get("estimated_cost_brl", 0.0),
            "text_preview": text[:100],
        }
        return True, flood_details

    return False, {}


def record_usage_metrics(
    phone: str,
    group_id: str = "",
    instance: str = "Jennifer",
    costs: Optional[Dict[str, int]] = None,
) -> None:
    """Registra estatísticas de uso de mensagens e tokens para controle de custos."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return

    costs = costs or {}
    cost_usd = estimate_cost_usd(costs)
    cost_brl = round(cost_usd * USD_TO_BRL_RATE, 4)

    db = _get_firestore_client()
    if db is None:
        return

    try:
        from google.cloud import firestore
        doc_ref = db.collection("usuarios").document(canonical)
        updates: Dict[str, Any] = {
            "total_messages": firestore.Increment(1),
            "total_tokens_input": firestore.Increment(costs.get("deepseek_input_tokens", 0)),
            "total_tokens_output": firestore.Increment(costs.get("deepseek_output_tokens", 0)),
            "total_tokens_embeddings": firestore.Increment(costs.get("openai_embedding_input_tokens", 0)),
            "estimated_cost_usd": firestore.Increment(cost_usd),
            "estimated_cost_brl": firestore.Increment(cost_brl),
            "last_active_at": now_brt().isoformat(),
            "updated_at": now_brt().isoformat(),
        }
        if group_id and not group_id.endswith("@s.whatsapp.net"):
            updates["last_group_id"] = group_id

        doc_ref.set(updates, merge=True)
    except Exception as exc:
        logger.warning("record_usage_metrics failed for %s: %s", canonical, exc)


def get_user_finops_metrics(phone: str) -> Dict[str, Any]:
    """Retorna o resumo de métricas de custos e uso do usuário."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return {"total_messages": 0, "estimated_cost_usd": 0.0, "estimated_cost_brl": 0.0}

    db = _get_firestore_client()
    if db is None:
        return {"total_messages": 0, "estimated_cost_usd": 0.0, "estimated_cost_brl": 0.0}

    try:
        doc = db.collection("usuarios").document(canonical).get(timeout=3)
        if not doc.exists:
            return {"total_messages": 0, "estimated_cost_usd": 0.0, "estimated_cost_brl": 0.0}

        data = doc.to_dict() or {}
        cost_usd = float(data.get("estimated_cost_usd", 0.0))
        cost_brl = float(data.get("estimated_cost_brl", round(cost_usd * USD_TO_BRL_RATE, 4)))
        return {
            "phone": canonical,
            "name": data.get("name") or data.get("push_name") or "Contato",
            "total_messages": int(data.get("total_messages", 0)),
            "total_tokens_input": int(data.get("total_tokens_input", 0)),
            "total_tokens_output": int(data.get("total_tokens_output", 0)),
            "estimated_cost_usd": round(cost_usd, 4),
            "estimated_cost_brl": round(cost_brl, 2),
            "is_quarantined": bool(data.get("is_quarantined", False)),
            "quarantine_reason": data.get("quarantine_reason", ""),
            "quarantined_at": data.get("quarantined_at", ""),
            "last_active_at": data.get("last_active_at", ""),
            "last_group_id": data.get("last_group_id", ""),
        }
    except Exception as exc:
        logger.warning("get_user_finops_metrics failed for %s: %s", canonical, exc)
        return {"total_messages": 0, "estimated_cost_usd": 0.0, "estimated_cost_brl": 0.0}


def get_all_finops_overview(instance: str = "") -> Dict[str, Any]:
    """Retorna métricas consolidadas de FinOps de todas as contas."""
    db = _get_firestore_client()
    if db is None:
        return {
            "total_cost_usd": 0.0,
            "total_cost_brl": 0.0,
            "total_messages": 0,
            "active_users_count": 0,
            "quarantined_users_count": 0,
            "users": [],
        }

    total_cost_usd = 0.0
    total_messages = 0
    quarantined_count = 0
    users_list: List[Dict[str, Any]] = []

    try:
        for doc in db.collection("usuarios").stream():
            data = doc.to_dict() or {}
            phone = str(doc.id).strip()
            if not phone or not phone.isdigit() or len(phone) < 8:
                continue

            # Se filtrou por instância, checa
            doc_instance = str(data.get("instance") or "Jennifer")
            if instance and instance.lower() != "all" and doc_instance.lower() != instance.lower():
                continue

            u_cost_usd = float(data.get("estimated_cost_usd", 0.0))
            u_cost_brl = float(data.get("estimated_cost_brl", round(u_cost_usd * USD_TO_BRL_RATE, 4)))
            u_messages = int(data.get("total_messages", 0))
            is_quarantined = bool(data.get("is_quarantined", False))

            total_cost_usd += u_cost_usd
            total_messages += u_messages
            if is_quarantined:
                quarantined_count += 1

            name = data.get("name") or data.get("push_name") or data.get("display_name") or f"+{phone}"
            raw_groups = data.get("group_memberships") or []
            groups: List[str] = []
            for g in raw_groups:
                if isinstance(g, dict):
                    g_label = g.get("subject") or g.get("gid") or ""
                    if g_label and g_label not in groups:
                        groups.append(str(g_label))
                elif isinstance(g, str) and g and g not in groups:
                    groups.append(g)

            last_gid = data.get("last_group_id")
            if last_gid and str(last_gid) not in groups:
                groups.append(str(last_gid))

            users_list.append({
                "phone": phone,
                "name": name,
                "email": data.get("email", ""),
                "role": data.get("role", "guest"),
                "total_messages": u_messages,
                "total_tokens_input": int(data.get("total_tokens_input", 0)),
                "total_tokens_output": int(data.get("total_tokens_output", 0)),
                "estimated_cost_usd": round(u_cost_usd, 4),
                "estimated_cost_brl": round(u_cost_brl, 2),
                "is_quarantined": is_quarantined,
                "quarantine_reason": data.get("quarantine_reason", ""),
                "quarantined_at": data.get("quarantined_at", ""),
                "last_active_at": data.get("last_active_at", data.get("updated_at", "")),
                "groups": groups,
                "instance": doc_instance,
            })


        # Ordena por maior custo primeiro
        users_list.sort(key=lambda x: x["estimated_cost_usd"], reverse=True)

        return {
            "total_cost_usd": round(total_cost_usd, 4),
            "total_cost_brl": round(total_cost_usd * USD_TO_BRL_RATE, 2),
            "total_messages": total_messages,
            "active_users_count": len(users_list) - quarantined_count,
            "quarantined_users_count": quarantined_count,
            "users": users_list,
        }
    except Exception as exc:
        logger.error("get_all_finops_overview failed: %s", exc)
        return {
            "total_cost_usd": 0.0,
            "total_cost_brl": 0.0,
            "total_messages": 0,
            "active_users_count": 0,
            "quarantined_users_count": 0,
            "users": [],
        }
