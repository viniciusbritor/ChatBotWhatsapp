"""Nickname tools - lookup + consent management."""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from core.timezone import now_brt

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nicknames.json")
_builtin_dict: Optional[Dict[str, List[str]]] = None

FORBIDDEN_NICKNAMES = {
    "burro", "burra", "idiota", "feio", "feia", "gordo", "gorda",
    "magrelo", "magrela", "bicha", "viado", "puta", "piranha",
    "vagabundo", "vagabunda", "otario", "otaria", "trouxa", "mane",
    "bosta", "merda", "caralho", "fdp", "porra", "buceta",
    "desgracado", "desgracada", "retardado", "retardada", "lerdo", "lerda",
    "tapado", "anta", "jegue", "corno", "chifrudo", "nojento", "nojenta",
    "lixo", "escroto", "escrota", "arrombado", "arrombada", "fudido",
    "fudida", "cuzão", "cuzona",
}


def _load_builtin() -> Dict[str, List[str]]:
    """Load built-in nickname dictionary."""
    global _builtin_dict
    if _builtin_dict is None:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _builtin_dict = {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception as e:
            logger.warning(f"Failed to load nicknames.json: {e}")
            _builtin_dict = {}
    return _builtin_dict


def _normalize_name(name: str) -> str:
    """Normalize name for matching (strip, title case, handle accents)."""
    return name.strip().title()


async def lookup(name: str) -> Dict[str, Any]:
    """Look up possible nicknames for a name.

    Checks built-in dict first, then custom learned nicknames in Firestore.

    Args:
        name: Full name (e.g., "Vinicius")

    Returns:
        {"nicknames": [...], "source": "builtin"|"custom"|"none"}
    """
    normalized = _normalize_name(name)
    builtin = _load_builtin()

    if normalized in builtin:
        return {
            "nicknames": builtin[normalized],
            "source": "builtin",
            "name": normalized,
        }

    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if project and not os.getenv("FIRESTORE_EMULATOR_HOST"):
            db = firestore.Client(project=project)
            doc = db.collection("apelidos_custom").document(_hash_phone(name)).get()
            if doc.exists:
                data = doc.to_dict()
                return {
                    "nicknames": data.get("nicknames", []),
                    "source": "custom",
                    "name": normalized,
                }
    except Exception as e:
        logger.warning(f"Firestore lookup error: {e}")

    return {"nicknames": [], "source": "none", "name": normalized}


def _hash_phone(s: str) -> str:
    """Hash a string to use as Firestore doc ID."""
    import hashlib
    return hashlib.sha256(s.lower().encode("utf-8")).hexdigest()[:32]


async def set_consent(
    phone: str,
    name: str,
    nickname: str,
    accepted: bool = True,
) -> Dict[str, Any]:
    """Record user's nickname preference.

    Args:
        phone: User's phone number (E.164)
        name: Full name offered
        nickname: Nickname accepted/rejected
        accepted: True if user accepted the nickname

    Returns:
        {"phone": str, "name": str, "nickname": str, "accepted": bool}
    """
    nickname_lower = nickname.lower().strip() if nickname else ""
    if nickname_lower in FORBIDDEN_NICKNAMES:
        logger.warning(f"FORBIDDEN nickname rejected: '{nickname}' for {phone}")
        return {"error": "forbidden_nickname", "nickname": nickname, "accepted": False}

    record = {
        "phone": phone,
        "name": _normalize_name(name),
        "nickname": nickname,
        "accepted": accepted,
        "ts": now_brt().isoformat(),
    }

    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if project and not os.getenv("FIRESTORE_EMULATOR_HOST"):
            db = firestore.Client(project=project)
            db.collection("apelidos_custom").document(_hash_phone(phone)).set({
                "phone": phone,
                "detected_name": _normalize_name(name),
                "offered_nickname": nickname,
                "accepted": accepted,
                "ts": record["ts"],
            })
            logger.info(f"Stored nickname consent for {phone}")
    except Exception as e:
        logger.warning(f"Failed to store nickname consent: {e}")

    return record


async def get_preferred_name(phone: str) -> Optional[str]:
    """Get user's preferred name (nickname if accepted, else display_name).

    Args:
        phone: User's phone number

    Returns:
        Preferred name or None if not set
    """
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        db = firestore.Client(project=project)
        doc = db.collection("apelidos_custom").document(_hash_phone(phone)).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("accepted"):
                return data.get("nickname")
        return None
    except Exception as e:
        logger.warning(f"get_preferred_name error: {e}")
        return None
