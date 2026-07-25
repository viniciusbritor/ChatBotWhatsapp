"""Google Calendar tools - 5 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.
The phone parameter is mandatory (Fase D); the global GOOGLE_OAUTH_TOKEN
fallback was removed.

Owner-only: Calendar access is restricted to the phone bound to the Evolution
instance.
"""
import functools
import logging
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
DEFAULT_CALENDAR_ID = "primary"

_calendar_services: Dict[str, Any] = {}


def _get_credentials(phone: str) -> Credentials:
    """Load Google OAuth credentials for the given user (per-user, Fase D).

    Uses core.oauth_per_user.get_user_credentials which centralises refresh
    logic and persists the rotated token back to Firestore.
    """
    if not phone:
        raise RuntimeError("phone_required_for_calendar_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        raise RuntimeError("user_google_oauth_required")
    return creds


def _get_service(phone: str):
    """Get or build Calendar API service (cached per user)."""
    cache_key = phone
    if cache_key not in _calendar_services:
        creds = _get_credentials(phone)
        _calendar_services[cache_key] = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _calendar_services[cache_key]


def _format_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Format event for response."""
    return {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
        "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
        "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "attendees": [a.get("email") for a in event.get("attendees", [])],
        "status": event.get("status", ""),
    }


def _owner_guard(capability: str):
    from core.owner import deny_if_not_owner, resolve_owner

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Tool signatures always start with ``phone``; fall back to positional
            # args when callers (e.g. the orchestrator) invoke with kwargs only.
            phone = kwargs.get("phone")
            if not phone and args:
                phone = args[0]
            phone = str(phone or "")
            instance = str(kwargs.get("instance", "") or kwargs.get("_instance", ""))
            resolution = resolve_owner(instance, fallback_phone=phone)
            denial = deny_if_not_owner(resolution, phone, capability)
            if denial is not None:
                return denial
            return await func(*args, **kwargs)
        return wrapper
    return decorator


@_owner_guard("calendar.list")
async def list_events(
    phone: str,
    time_min: str,
    time_max: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    max_results: int = 50,
    instance: str = "",
) -> Dict[str, Any]:
    """List calendar events between time_min and time_max.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        time_min: ISO 8601 datetime (e.g., "2026-07-13T00:00:00-03:00")
        time_max: ISO 8601 datetime
        calendar_id: Calendar to query (default: primary)
        max_results: Max events to return (default: 50)

    Returns:
        {"events": [...], "count": int}
    """
    try:
        service = _get_service(phone)
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = [_format_event(e) for e in result.get("items", [])]
        return {"events": events, "count": len(events)}
    except HttpError as e:
        logger.error(f"Calendar list_events error: {e}")
        return {"events": [], "count": 0, "error": str(e)}


@_owner_guard("calendar.create")
async def create_event(
    phone: str,
    start: str,
    end: str,
    summary: str,
    description: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    location: Optional[str] = None,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    instance: str = "",
) -> Dict[str, Any]:
    """Create a new calendar event."""
    try:
        service = _get_service(phone)
        event_body = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]

        created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return {"event": _format_event(created)}
    except HttpError as e:
        logger.error(f"Calendar create_event error: {e}")
        return {"event": None, "error": str(e)}


@_owner_guard("calendar.update")
async def update_event(
    phone: str,
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    instance: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Update an existing calendar event."""
    try:
        service = _get_service(phone)
        existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        for key, value in kwargs.items():
            if key in ("start", "end") and value:
                existing[key] = {"dateTime": value}
            elif key == "attendees" and value:
                existing[key] = [{"email": e} for e in value]
            elif value is not None:
                existing[key] = value
        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=existing).execute()
        return {"event": _format_event(updated)}
    except HttpError as e:
        logger.error(f"Calendar update_event error: {e}")
        return {"event": None, "error": str(e)}


@_owner_guard("calendar.delete")
async def delete_event(
    phone: str,
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    instance: str = "",
) -> Dict[str, Any]:
    """Delete a calendar event."""
    try:
        service = _get_service(phone)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id}
    except HttpError as e:
        logger.error(f"Calendar delete_event error: {e}")
        return {"deleted": False, "error": str(e)}


@_owner_guard("calendar.freebusy")
async def freebusy(
    phone: str,
    time_min: str,
    time_max: str,
    calendars: Optional[List[str]] = None,
    instance: str = "",
) -> Dict[str, Any]:
    """Check free/busy status for calendars."""
    try:
        service = _get_service(phone)
        if not calendars:
            calendars = [DEFAULT_CALENDAR_ID]
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": c} for c in calendars],
        }
        result = service.freebusy().query(body=body).execute()
        busy_slots = []
        for cal_id, cal_data in result.get("calendars", {}).items():
            for busy in cal_data.get("busy", []):
                busy_slots.append({
                    "calendar": cal_id,
                    "start": busy.get("start"),
                    "end": busy.get("end"),
                })
        return {"busy": busy_slots, "calendars": calendars}
    except HttpError as e:
        logger.error(f"Calendar freebusy error: {e}")
        return {"busy": [], "error": str(e)}
