"""Proactive command handler.

Parses user commands for proactive mode changes:
- "Jennifer, silêncio" -> proactive_mode = "off"
- "Jennifer, modo zen" -> proactive_mode = "zen"
- "Jennifer, modo turbo" -> proactive_mode = "turbo"
- "Jennifer, só emergências" -> proactive_mode = "emergencies"
- "Jennifer, retomar" -> proactive_mode = "normal"
- "Jennifer, grupo off" -> group proactive_mode = "off"
- "Jennifer, grupo on" -> group proactive_mode = "normal"
"""
import os
import logging
import re
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COMMAND_PATTERNS = [
    (r"jennifer,?\s*sil[êe]ncio", "off"),
    (r"jennifer,?\s*modo\s+zen", "zen"),
    (r"jennifer,?\s*modo\s+turbo", "turbo"),
    (r"jennifer,?\s*s[óo]\s+emerg[êe]ncias", "emergencies"),
    (r"jennifer,?\s*retomar", "normal"),
    (r"jennifer,?\s*grupo\s+off", "group_off"),
    (r"jennifer,?\s*grupo\s+on", "group_on"),
]

RESPONSE_MESSAGES = {
    "off": "Entendido! Vou parar de mandar mensagens proativas. Manda 'Jennifer, retomar' quando quiser reativar.",
    "zen": "Modo zen ativado! Vou reduzir a frequencia de mensagens proativas em 50%.",
    "turbo": "Modo turbo ativado! Posso mandar ate 2 mensagens proativas por dia.",
    "emergencies": "Modo emergencias! So vou mandar mensagens em situacoes criticas.",
    "normal": "Modo normal reativado. Proatividade padrao.",
    "group_off": "Proatividade em grupo desativada. Continuo proativo no privado.",
    "group_on": "Proatividade em grupo reativada.",
}


def _get_firestore():
    try:
        from google.cloud import firestore
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def detect_command(text: str) -> Optional[str]:
    """Detect proactive command in user text.

    Returns:
        Command key (e.g., "off", "zen") or None
    """
    text_lower = text.lower().strip()
    for pattern, cmd in COMMAND_PATTERNS:
        if re.search(pattern, text_lower):
            return cmd
    return None


async def apply_command(phone: str, command: str) -> Dict[str, Any]:
    """Apply a proactive command to a contact.

    Args:
        phone: User phone
        command: One of the command keys (off, zen, turbo, emergencies, normal, group_off, group_on)

    Returns:
        {"phone": str, "command": str, "new_mode": str, "message": str}
    """
    db = _get_firestore()
    if db is None:
        return {"error": "firestore_unavailable"}

    try:
        contact_ref = db.collection("contatos").document(phone)
        now = datetime.now(timezone.utc).isoformat()

        if command in ("off", "zen", "turbo", "emergencies", "normal"):
            contact_ref.set({
                "proactive_mode": command,
                "proactive_mode_changed_at": now,
            }, merge=True)
            new_mode = command
        elif command == "group_off":
            contact_ref.set({"group_proactive_mode": "off"}, merge=True)
            new_mode = "group_off"
        elif command == "group_on":
            contact_ref.set({"group_proactive_mode": "normal"}, merge=True)
            new_mode = "group_on"
        else:
            return {"error": "unknown_command"}

        message = RESPONSE_MESSAGES.get(command, "Comando aplicado.")
        logger.info(f"Proactive command applied: phone={phone} command={command}")

        return {
            "phone": phone,
            "command": command,
            "new_mode": new_mode,
            "message": message,
            "applied_at": now,
        }
    except Exception as e:
        logger.exception(f"apply_command error: {e}")
        return {"error": str(e)}


async def handle_command_if_any(phone: str, text: str) -> Optional[Dict[str, Any]]:
    """Check if text contains a proactive command and apply it.

    Returns:
        None if no command detected
        Dict with command result if command was applied
    """
    cmd = detect_command(text)
    if cmd is None:
        return None
    return await apply_command(phone, cmd)