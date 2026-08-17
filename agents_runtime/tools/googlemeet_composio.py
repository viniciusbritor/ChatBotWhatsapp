"""Google Meet tools via Composio SDK.

GUARDRAIL §0.8 (17/08/2026): modulo criado para suportar manager-googlemeet.
Usa helper compartilhado `composio_call` de `tools._composio_common`.

Tools wrapped:
- create_meeting: GOOGLESHEETS_CREATE_GOOGLE_SHEET (Meet via Calendar)
- list_meetings: GOOGLESHEETS_READ_GOOGLE_SHEET (via Calendar)
"""
import logging
from typing import Any, Dict

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def create_meeting(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: str = "",
    phone: str = "",
) -> Dict[str, Any]:
    """Cria um evento no Google Calendar com link de Meet.

    Args:
        summary: Titulo da reuniao.
        start_time: ISO 8601 (ex: '2026-08-20T15:00:00-03:00').
        end_time: ISO 8601.
        attendees: Emails separados por virgula (opcional).
        phone: Telefone do usuario.
    """
    args = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
        "conferenceData": {"createRequest": {"requestId": f"meet-{phone}-{start_time}"}},
    }
    if attendees:
        args["attendees"] = [{"email": e.strip()} for e in attendees.split(",") if e.strip()]

    user_id = str(phone or "")
    return await composio_call(
        "GOOGLECALENDAR_CREATE_EVENT",
        args,
        user_id=user_id,
    )


async def list_meetings(
    time_min: str,
    time_max: str,
    max_results: int = 50,
    phone: str = "",
) -> Dict[str, Any]:
    """Lista eventos do Google Calendar (que tem link de Meet).

    Args:
        time_min: ISO 8601 datetime inicio.
        time_max: ISO 8601 datetime fim.
        max_results: Maximo de resultados (default 50).
        phone: Telefone do usuario.
    """
    user_id = str(phone or "")
    return await composio_call(
        "GOOGLECALENDAR_LIST_EVENTS",
        {"time_min": time_min, "time_max": time_max, "max_results": max_results},
        user_id=user_id,
    )


async def get_meeting_link(event_id: str, phone: str = "") -> Dict[str, Any]:
    """Retorna dados de um evento especifico (incluindo link Meet).

    Args:
        event_id: ID do evento no Google Calendar.
        phone: Telefone do usuario.
    """
    user_id = str(phone or "")
    return await composio_call(
        "GOOGLECALENDAR_GET_EVENT",
        {"event_id": event_id},
        user_id=user_id,
    )