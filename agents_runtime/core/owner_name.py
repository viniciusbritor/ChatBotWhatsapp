"""Resolve display name de um phone via cascata hibrida (D3).

Precedencia:
1. usuarios/{phone}.name (sincronizado via Firebase JWT)
2. usuarios/{phone}.push_name (WhatsApp pushName)
3. Evolution contacts API (runtime lookup, cache 24h via DiskCache)
4. Fallback: phone mascarado

Quando a chamada Evolution falha, o logger registra warning e segue para
o fallback mascardo. Tudo defensivo — NAO pode quebrar o caller.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

PROJECT = "coherence-ominichannel-fs"
_db: Optional[firestore.Client] = None

# Cache em memoria (TTL 24h) — phone_digits -> (name, timestamp)
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SEC = 24 * 3600


def _get_db() -> firestore.Client:
    """Lazy init para evitar Firestore client em import-time."""
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT)
    return _db


def _mask_phone(phone: str) -> str:
    """'+55 11 9****-0020' formato humanizado."""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) < 4:
        return f"+{phone}"
    if len(digits) >= 12:
        # internacional: +CC AA 9****-XXXX
        cc = digits[:2]
        area = digits[2:4]
        last4 = digits[-4:]
        return f"+{cc} {area} 9****-{last4}"
    # BR: +55 11 9****-XXXX
    if len(digits) >= 11:
        return f"+{digits[:2]} {digits[2:4]} 9****-{digits[-4:]}"
    return f"+{phone}"


def _firestore_lookup(phone: str) -> str:
    """Tenta Firestore usuarios/{phone}. Retorna name ou push_name."""
    try:
        doc = _get_db().collection("usuarios").document(phone).get()
        if doc.exists:
            data = doc.to_dict() or {}
            name = (data.get("name") or "").strip()
            if name:
                return name
            push_name = (data.get("push_name") or "").strip()
            if push_name:
                return push_name
    except Exception as e:
        logger.warning("firestore_name_lookup_failed phone=%s err=%s", phone, type(e).__name__)
    return ""


def _evolution_lookup(phone: str) -> str:
    """Tenta Evolution contacts API. Usa cache 24h.

    Import defensivo: se core.evolution_client nao expor find_contact(),
    registra debug e retorna "" (fallback mascardo sera usado).
    """
    cached = _cache.get(phone)
    if cached and (time.time() - cached[1]) < _CACHE_TTL_SEC:
        return cached[0]

    try:
        from core import evolution_client
        if not hasattr(evolution_client, "find_contact"):
            logger.debug("evolution_find_contact_not_available")
            return ""
        # Pode ser sync ou async
        result = evolution_client.find_contact(phone)
        if hasattr(result, "__await__"):
            # Async detectado — nao esperamos em contexto sync
            logger.debug("evolution_find_contact_async_skipped phone=%s", phone)
            return ""
        contact = result or {}
        name = (contact.get("name") or contact.get("pushname") or "").strip()
        if name:
            _cache[phone] = (name, time.time())
            return name
    except Exception as e:
        logger.warning(
            "evolution_contact_lookup_failed phone=%s err=%s", phone, type(e).__name__,
        )
    return ""


def resolve_owner_name(phone: str) -> str:
    """Cascata hibrida: Firestore -> Evolution -> mascardo.

    Args:
        phone: phone digits (com ou sem +55, com ou sem formatacao).

    Returns:
        Display name canonico. Nunca retorna string vazia.
    """
    if not phone:
        return ""

    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits:
        return ""

    # 1. Firestore
    name = _firestore_lookup(digits)
    if name:
        return name

    # 2. Evolution contacts API
    name = _evolution_lookup(digits)
    if name:
        return name

    # 3. Fallback mascardo
    return _mask_phone(digits)


def clear_cache_for_phone(phone: str) -> None:
    """Invalida cache (usado apos sync_user_profile)."""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits:
        _cache.pop(digits, None)
