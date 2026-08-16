"""Ack module — typing indicator + "Só um instante..." instant message.

Provides immediate feedback to the user before executing ANY Google or
Composio tool/API search, preventing the feeling that the bot has frozen.

Used by: calendar_pipeline, email_pipeline, doc_pipeline, orchestrator tool loop,
and deepagent_layer tool wrappers.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ACK_MAP: Dict[str, str] = {
    # Calendar
    "calendar": "Só um instante. Vou ver sua agenda... 📅",
    "list_calendar_events": "Só um instante. Vou ver sua agenda... 📅",
    "create_calendar_event": "Só um instante. Vou agendar seu compromisso... 📅",
    "move_event": "Só um instante. Vou reagendar seu compromisso... 📅",
    "update_event": "Só um instante. Vou atualizar seu compromisso... 📅",
    "delete_event": "Só um instante. Vou remover o compromisso da agenda... 📅",
    "calendar_freebusy": "Só um instante. Vou checar sua disponibilidade... 📅",
    # Gmail / Email
    "email": "Só um instante. Vou buscar seus e-mails... 📧",
    "gmail": "Só um instante. Vou buscar seus e-mails... 📧",
    "list_messages": "Só um instante. Vou buscar seus e-mails... 📧",
    "get_message": "Só um instante. Vou ler o e-mail... 📧",
    "send_email": "Só um instante. Vou preparar o envio do e-mail... 📧",
    "send_message": "Só um instante. Vou preparar o envio do e-mail... 📧",
    "create_draft": "Só um instante. Vou criar o rascunho do e-mail... 📧",
    # Drive / Docs / Sheets
    "drive": "Só um instante. Vou procurar no Google Drive... 📁",
    "googledrive": "Só um instante. Vou procurar no Google Drive... 📁",
    "search_drive_files": "Só um instante. Vou procurar os arquivos no Google Drive... 📁",
    "list_folder": "Só um instante. Vou listar as pastas no Google Drive... 📁",
    "read_file_content": "Só um instante. Vou abrir e ler o arquivo... 📄",
    "upload_file": "Só um instante. Vou salvar o arquivo no Google Drive... 📁",
    "docs": "Só um instante. Vou abrir o documento no Google Docs... 📄",
    "googledocs": "Só um instante. Vou abrir o documento no Google Docs... 📄",
    "sheets": "Só um instante. Vou consultar a planilha no Google Sheets... 📊",
    "googlesheets": "Só um instante. Vou consultar a planilha no Google Sheets... 📊",
    # Contacts / Tasks / Maps
    "contacts": "Só um instante. Vou buscar nos seus contatos... 👤",
    "people": "Só um instante. Vou buscar nos seus contatos... 👤",
    "tasks": "Só um instante. Vou ver suas tarefas... ✅",
    "vision": "Só um instante. Vou analisar a imagem... 🔍",
    "places": "Só um instante. Vou buscar no Google Maps... 📍",
    "maps": "Só um instante. Vou consultar o Google Maps... 📍",
    "weather": "Só um instante. Vou consultar o clima... ⛅",
    # Composio Apps
    "youtube": "Só um instante. Vou buscar no YouTube... 🎥",
    "linkedin": "Só um instante. Vou consultar o LinkedIn... 💼",
    "github": "Só um instante. Vou verificar o GitHub... 🐙",
    "notion": "Só um instante. Vou consultar o Notion... 📝",
    "onedrive": "Só um instante. Vou buscar no Microsoft OneDrive... ☁️",
    # RAG / Web
    "rag": "Só um instante. Vou verificar minha base de conhecimento... 📚",
    "knowledge": "Só um instante. Vou verificar minha base de conhecimento... 📚",
    "web": "Só um instante. Vou pesquisar na internet... 🔍",
    "translate": "Só um instante. Vou traduzir... 🌐",
}

_ACKED_PHONES: Dict[str, float] = {}


def get_tool_ack_message(tool_name: str) -> str:
    """Retorna a mensagem amigável de feedback imediato baseada na ferramenta chamada."""
    tool_lower = str(tool_name or "").lower().strip()
    if not tool_lower:
        return "Só um instante, estou buscando as informações... ⏳"

    if tool_lower in _ACK_MAP:
        return _ACK_MAP[tool_lower]

    parts = tool_lower.replace("-", ".").replace("_", ".").split(".")
    for p in parts:
        if p in _ACK_MAP:
            return _ACK_MAP[p]

    for key, msg in _ACK_MAP.items():
        if key in tool_lower:
            return msg

    return "Só um instante, estou buscando as informações... ⏳"


async def send_instant_tool_ack(
    tool_name: str,
    phone: str,
    instance: str = "Jennifer",
    extra: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> bool:
    """Dispara IMEDIATAMENTE a mensagem de busca no WhatsApp antes de executar a tool.

    Possui cooldown de 20s por telefone para garantir que o usuário receba
    EXATAMENTE UMA mensagem de busca por turno, mesmo que o agente realize
    múltiplas chamadas de ferramentas internamente.
    """
    if not phone:
        return False
    clean_phone = re.sub(r"\D", "", str(phone))
    if not clean_phone:
        return False

    now = time.time()
    if not force:
        last_ack = _ACKED_PHONES.get(clean_phone, 0)
        if (now - last_ack) < 20:
            return False
    _ACKED_PHONES[clean_phone] = now

    if len(_ACKED_PHONES) > 500:
        cutoff = now - 60
        for k in list(_ACKED_PHONES.keys()):
            if _ACKED_PHONES[k] < cutoff:
                del _ACKED_PHONES[k]

    text = get_tool_ack_message(tool_name)
    extra = extra or {}
    remote_jid = extra.get("remote_jid", "")

    try:
        from core.evolution_client import send_presence, send_text

        try:
            await send_presence(instance, clean_phone, "composing", remote_jid=remote_jid)
        except Exception:
            pass
        await send_text(
            instance=instance,
            phone=clean_phone,
            text=text,
            delay_ms=0,
            presence="composing",
            remote_jid=remote_jid,
        )
        return True
    except Exception as exc:
        logger.debug("send_instant_tool_ack_failed tool=%s exc=%s", tool_name, exc)
        return False


async def send_ack(
    instance: str,
    phone: str,
    ack_type: str,
    extra: Dict[str, Any],
) -> None:
    """Envia typing indicator + mensagem de espera no WhatsApp."""
    force = bool(extra and extra.get("force"))
    await send_instant_tool_ack(
        tool_name=ack_type,
        phone=phone,
        instance=instance,
        extra=extra,
        force=force,
    )
