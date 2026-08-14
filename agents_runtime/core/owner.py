"""Owner + instance identity resolution.

The owner is the human or workspace that connected WhatsApp + Google. Every
inbound message flows from an Evolution instance; the instance has a single
owner phone attached to it. Tools that require Google data must therefore be
executed only when the inbound phone equals the owner phone of the instance.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from agent_loader import _get_firestore_client

logger = logging.getLogger(__name__)

WHATSAPP_ACCOUNTS_COLLECTION = os.getenv("WHATSAPP_ACCOUNTS_COLLECTION", "whatsapp_accounts")


def normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _candidates(raw: str) -> Iterable[str]:
    digits = normalize_phone(raw)
    if not digits:
        return []
    candidates = {digits}
    if digits.startswith("55") and len(digits) > 11:
        candidates.add(digits[2:])
    elif len(digits) >= 10:
        candidates.add("55" + digits)
    return [c for c in candidates if c]


@dataclass
class OwnerResolution:
    owner_phone: str
    owner_uid: str
    account_id: str
    instance: str

    @property
    def owner_candidates(self) -> Iterable[str]:
        return _candidates(self.owner_phone)


def resolve_owner(instance: str, fallback_phone: str = "") -> Optional[OwnerResolution]:
    """Look up the owner bound to an Evolution instance.

    Strategy:
    1. If ``instance`` is provided, query ``whatsapp_accounts`` for the owner.
    2. If ``instance`` is empty, query ``whatsapp_accounts`` for a row whose
       ``owner_phone`` matches the normalised ``fallback_phone``.
    3. If nothing is found, fall back to the inbound phone so single-tenant
       deployments still work, but tools requiring Google scopes will treat
       the caller as the owner only when the inbound phone matches the
       resolved ``owner_phone``.
    """
    db = _get_firestore_client()
    instance_norm = (instance or "").strip()
    fallback_norm = normalize_phone(fallback_phone)
    if db is not None and instance_norm:
        try:
            docs = db.collection(WHATSAPP_ACCOUNTS_COLLECTION).where(
                "instance", "==", instance_norm
            ).limit(1).stream()
            for doc in docs:
                data = doc.to_dict() or {}
                owner_phone = normalize_phone(data.get("owner_phone", ""))
                if not owner_phone:
                    continue
                return OwnerResolution(
                    owner_phone=owner_phone,
                    owner_uid=str(data.get("owner_uid", owner_phone)),
                    account_id=str(data.get("account_id", doc.id)),
                    instance=instance_norm,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("resolve_owner firestore (instance) failed: %s", exc)
    if db is not None and fallback_norm:
        try:
            docs = db.collection(WHATSAPP_ACCOUNTS_COLLECTION).where(
                "owner_phone", "==", fallback_norm
            ).limit(1).stream()
            for doc in docs:
                data = doc.to_dict() or {}
                return OwnerResolution(
                    owner_phone=fallback_norm,
                    owner_uid=str(data.get("owner_uid", fallback_norm)),
                    account_id=str(data.get("account_id", doc.id)),
                    instance=str(data.get("instance", instance_norm)),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("resolve_owner firestore (owner_phone) failed: %s", exc)
    if not fallback_norm:
        return None
    return OwnerResolution(
        owner_phone=fallback_norm,
        owner_uid=fallback_norm,
        account_id=f"fallback:{fallback_norm}",
        instance=instance_norm or "unknown",
    )


def is_owner_request(resolution: Optional[OwnerResolution], inbound_phone: str) -> bool:
    if not resolution:
        return False
    if not inbound_phone:
        return False
    target = normalize_phone(inbound_phone)
    if not target:
        return False
    return any(target == candidate for candidate in resolution.owner_candidates)


def deny_if_not_owner(resolution: Optional[OwnerResolution], inbound_phone: str, capability: str) -> Optional[Dict[str, str]]:
    if is_owner_request(resolution, inbound_phone):
        return None
    # Multi-tenant: Se o usuário tem token Google OAuth próprio válido no Firestore, permita!
    try:
        from core.oauth_per_user import get_user_oauth
        token_data = get_user_oauth(inbound_phone)
        if token_data and token_data.get("scopes"):
            return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("multi_tenant_oauth_check_failed phone=%s exc=%s", inbound_phone, exc)

    logger.info(
        "owner_guard_denied capability=%s instance=%s phone=%s",
        capability,
        resolution.instance if resolution else "-",
        normalize_phone(inbound_phone),
    )
    if resolution is None:
        message = (
            f"Para acessar {capability}, preciso saber qual instancia WhatsApp voce esta usando. "
            "Tente novamente em alguns segundos; se persistir, chame no privado."
        )
    else:
        oauth_link = (
            "Para liberar, acesse este link e autorize sua conta Google (Gmail, Drive e Calendar): "
            f"https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/oauth/google?phone={inbound_phone}"
        )
        message = (
            f"A busca {capability} precisa que a sua conta Google esteja vinculada. "
            f"{oauth_link}"
        )
    return {
        "error": "owner_only_capability",
        "capability": capability,
        "message": message,
        "instance": resolution.instance if resolution else "",
        "phone": normalize_phone(inbound_phone),
    }
