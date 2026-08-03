"""Ack module — typing indicator + "Só um instante..." message.

Used by: calendar_pipeline, email_pipeline, doc_pipeline (drive path only).

Fallback: silent pass on any error. Pipeline continues normally.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_ACK_MAP = {
    "calendar": "Só um instante. Vou ver sua agenda... 📅",
    "drive": "Só um instante. Vou procurar aqui... 📁",
    "email": "Só um instante. Vou buscar seus emails... 📧",
    "rag": "Só um instante. Vou verificar minha base de conhecimento... 📚",
}


async def send_ack(
    instance: str,
    phone: str,
    ack_type: str,
    extra: Dict[str, Any],
) -> None:
    """Envia typing indicator + mensagem de espera no WhatsApp.

    Aguarda o envio HTTP para garantir que o ack chegue antes da resposta.
    Presence é fire-and-forget (não bloqueante).
    """
    try:
        text = _ACK_MAP.get(ack_type, "Só um instante... ⏳")
        from core.delay_calculator import calculate_delay_ms
        from core.evolution_client import send_presence, send_text

        delay_ms = max(1500, calculate_delay_ms(text))
        remote_jid = extra.get("remote_jid", "")

        asyncio.create_task(
            send_presence(instance, phone, "composing", remote_jid=remote_jid)
        )
        await send_text(
            instance=instance,
            phone=phone,
            text=text,
            delay_ms=delay_ms,
            presence="composing",
            remote_jid=remote_jid,
        )
    except Exception:
        pass
