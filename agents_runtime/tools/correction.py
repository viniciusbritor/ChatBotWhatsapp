"""Correction tool - detects user corrections and applies patches after confirmation."""
import os
import logging
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CORRECTION_PHRASES = [
    "na verdade", "na verdade meu", "na verdade, meu",
    "errado", "errada", "não é assim", "nao e assim",
    "meu nome e", "meu nome é", "me chamo",
    "sempre", "nunca", "prefiro",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def detect_correction(text: str) -> Dict[str, Any]:
    """Detect if a message contains a correction.

    Args:
        text: User message

    Returns:
        {"is_correction": bool, "confidence": float, "target": str, "extracted": str}
    """
    text_lower = text.lower()
    matches = [p for p in CORRECTION_PHRASES if p in text_lower]
    confidence = min(1.0, len(matches) * 0.4)

    target = "unknown"
    if "nome" in text_lower:
        target = "preferred_name"
    elif any(kw in text_lower for kw in ["comportamento", "tom", "maneira", "jeito"]):
        target = "agent_behavior"
    elif any(kw in text_lower for kw in ["errado", "errada", "incorreto"]):
        target = "agent_fact"

    extracted = text if matches else ""

    return {
        "is_correction": len(matches) > 0,
        "confidence": confidence,
        "target": target,
        "phrases_matched": matches,
        "extracted": extracted,
    }


async def log_correction(
    phone: str,
    user_quote: str,
    target: str,
    before: str,
    after: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Log a correction to Firestore (in contatos/{phone}/corrections/{id}).

    Args:
        phone: User phone
        user_quote: Original user message
        target: What was corrected (preferred_name, agent_behavior, etc.)
        before: Before state
        after: After state
        confirmed: True if user confirmed the change

    Returns:
        {"correction_id": str, "phone": str, "applied": bool}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        import uuid
        correction_id = str(uuid.uuid4())
        ref = (
            db.collection("contatos")
            .document(phone)
            .collection("corrections")
            .document(correction_id)
        )
        ref.set({
            "ts": _now_iso(),
            "user_quote": user_quote,
            "target": target,
            "before": before[:1000],
            "after": after[:1000],
            "applied": confirmed,
            "confirmed_at": _now_iso() if confirmed else None,
        })
        return {
            "correction_id": correction_id,
            "phone": phone,
            "applied": confirmed,
        }
    except Exception as e:
        logger.error(f"log_correction error: {e}")
        return {"error": str(e)}


async def apply_patch(
    agent_id: str,
    target: str,
    patch_text: str,
) -> Dict[str, Any]:
    """Apply a patch to an agent's system_prompt in Firestore.

    Args:
        agent_id: Agent ID to update
        target: Target field (default: system_prompt)
        patch_text: New text for the field

    Returns:
        {"agent_id": str, "updated": bool, "version": int}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        ref = db.collection("agents").document(agent_id)
        doc = ref.get()
        if not doc.exists:
            return {"error": "agent_not_found"}
        data = doc.to_dict()
        current_version = data.get("system_prompt_version", 1)

        if target == "system_prompt":
            new_text = patch_text
        elif target.startswith("replace:"):
            old = target.replace("replace:", "", 1)
            new_text = data.get("system_prompt", "").replace(old, patch_text)
        else:
            new_text = patch_text

        ref.update({
            "system_prompt": new_text,
            "system_prompt_version": current_version + 1,
            "last_learned_at": _now_iso(),
            "updated_at": _now_iso(),
        })

        return {
            "agent_id": agent_id,
            "updated": True,
            "version": current_version + 1,
        }
    except Exception as e:
        logger.error(f"apply_patch error: {e}")
        return {"error": str(e)}


def generate_confirmation_message(target: str, extracted: str) -> str:
    """Generate confirmation message for user.

    Args:
        target: Type of correction
        extracted: Original quote

    Returns:
        Message asking user to confirm
    """
    if target == "preferred_name":
        return (
            f"Anoto isso? Voce disse '{extracted[:80]}'. "
            "A partir de agora eu uso o novo nome que voce preferir. "
            "Responda 'sim' para confirmar ou 'nao' para descartar."
        )
    elif target == "agent_behavior":
        return (
            f"Voce quer que eu mude meu comportamento? "
            f"Disse: '{extracted[:80]}'. "
            "Responda 'sim' para eu atualizar ou 'nao' para manter como esta."
        )
    else:
        return (
            f"Entendi sua observacao: '{extracted[:80]}'. "
            "Posso anotar? Responda 'sim' ou 'nao'."
        )
