"""Microsoft Teams tools via Composio SDK.

GUARDRAIL §0.8 (17/08/2026): modulo criado para suportar manager-msteams.
Usa helper compartilhado `composio_call` de `tools._composio_common`.

Tools wrapped:
- send_message: MS_TEAMS_SEND_MESSAGE
- list_channels: MS_TEAMS_LIST_CHANNELS
- list_messages: MS_TEAMS_LIST_MESSAGES
"""
import logging
from typing import Any, Dict

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def send_message(
    channel_id: str,
    message: str,
    phone: str = "",
) -> Dict[str, Any]:
    """Envia uma mensagem para um canal do Teams.

    Args:
        channel_id: ID do canal de destino.
        message: Conteudo da mensagem.
        phone: Telefone do usuario.
    """
    user_id = str(phone or "")
    return await composio_call(
        "MS_TEAMS_SEND_MESSAGE",
        {
            "channel_id": channel_id,
            "message": message,
        },
        user_id=user_id,
    )


async def list_channels(phone: str = "") -> Dict[str, Any]:
    """Lista canais do Teams do usuario.

    Args:
        phone: Telefone do usuario.
    """
    user_id = str(phone or "")
    return await composio_call(
        "MS_TEAMS_LIST_CHANNELS",
        {},
        user_id=user_id,
    )


async def list_messages(
    channel_id: str,
    top: int = 20,
    phone: str = "",
) -> Dict[str, Any]:
    """Lista mensagens de um canal do Teams.

    Args:
        channel_id: ID do canal.
        top: Numero maximo de mensagens (default 20).
        phone: Telefone do usuario.
    """
    user_id = str(phone or "")
    return await composio_call(
        "MS_TEAMS_LIST_MESSAGES",
        {"channel_id": channel_id, "top": max(1, min(999, top))},
        user_id=user_id,
    )


async def create_online_meeting(
    subject: str,
    start_date_time: str,
    end_date_time: str,
    phone: str = "",
    user_id: str = "",
    participants: list = None,
) -> Dict[str, Any]:
    """Cria uma reuniao online standalone no Microsoft Teams.

    Args:
        subject: Titulo da reuniao.
        start_date_time: ISO 8601 (ex: '2026-08-20T15:00:00Z').
        end_date_time: ISO 8601.
        phone: Telefone do usuario (per-user Composio user_id).
        user_id: (alternativo) Graph user ID.
        participants: Lista opcional de participantes (objects com user_id/email).
    """
    user = str(user_id or phone or "")
    args = {
        "subject": subject,
        "startDateTime": start_date_time,
        "endDateTime": end_date_time,
    }
    if participants:
        args["participants"] = participants
    return await composio_call(
        "MICROSOFT_TEAMS_CREATE_ONLINE_MEETING",
        args,
        user_id=user,
    )