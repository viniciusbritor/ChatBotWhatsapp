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
    "drive": "Só um instante. Vou procurar no Drive... 📁",
    "email": "Só um instante. Vou buscar seus emails... 📧",
    "gmail": "Só um instante. Vou buscar seus emails... 📧",
    "rag": "Só um instante. Vou verificar minha base de conhecimento... 📚",
    "sheets": "Só um instante. Vou preparar a planilha... 📊",
    "googlesheets": "Só um instante. Vou preparar a planilha... 📊",
    "translate": "Só um instante. Vou traduzir... 🌐",
    "tasks": "Só um instante. Vou ver suas tarefas... ✅",
    "people": "Só um instante. Vou buscar nos contatos... 👤",
    "contacts": "Só um instante. Vou buscar nos contatos... 👤",
    "photos": "Só um instante. Vou buscar as fotos... 🖼️",
    "vision": "Só um instante. Vou analisar a imagem... 🔍",
    "places": "Só um instante. Vou buscar no Google Maps... 📍",
    "youtube": "Só um instante. Vou buscar no YouTube... 🎥",
    "docs": "Só um instante. Vou procurar o documento... 📄",
    "googledocs": "Só um instante. Vou procurar o documento... 📄",
    "maps": "Só um instante. Vou calcular a rota... 🗺️",
    "weather": "Só um instante. Vou consultar o clima... ⛅",
    "linkedin": "Só um instante. Vou consultar o LinkedIn... 💼",
    "github": "Só um instante. Vou verificar o GitHub... 🐙",
    "notion": "Só um instante. Vou consultar o Notion... 📝",
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
