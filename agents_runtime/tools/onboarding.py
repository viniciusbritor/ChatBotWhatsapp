"""Onboarding tools — vincula email do Portal ao telefone WhatsApp.

Storage: usuarios/{phone}.email (merge).
Usado pela Jennifer no primeiro contato com um novo usuario:
pergunta o email do Portal Coherence e salva a vinculacao.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    from core.timezone import now_brt

    return now_brt().isoformat()


def _get_firestore():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("onboarding firestore unavailable: %s", exc)
        return None


async def link_email(phone: str = "", email: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Vincula o email do Portal Coherence ao telefone WhatsApp.

    Salva ``usuarios/{phone}.email`` no Firestore (merge, nao apaga
    campos existentes como google_oauth_token).

    Args:
        phone: Telefone do usuario (obrigatorio, vem do WhatsApp).
        email: Email do usuario no Portal Coherence (obrigatorio).

    Returns:
        {"linked": True, "phone": ..., "email": ...} ou erro.
    """
    phone = str(phone or "").strip()
    email = str(email or "").strip().lower()
    if not phone or not email:
        return {"error": "phone_and_email_required", "linked": False}
    if "@" not in email:
        return {"error": "invalid_email", "linked": False}

    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable", "linked": False}
    try:
        db.collection("usuarios").document(phone).set(
            {
                "email": email,
                "email_linked_at": _now_iso(),
                "phone": phone,
                "onboarding_source": "whatsapp",
            },
            merge=True,
        )
        logger.info("onboarding_email_linked phone=%s email=%s", phone, email)
        return {"linked": True, "phone": phone, "email": email}
    except Exception as exc:
        logger.warning("onboarding_link_email_failed phone=%s error=%s", phone, exc)
        return {"error": str(exc)[:200], "linked": False}


__all__ = ["link_email"]
