"""Google Calendar tools - 5 functions.

Auth: reuses existing token at ~/.gemini/config/skills/google_calendar_manager/resources/token_drive.json
"""
import json
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


def _get_credentials(phone: Optional[str] = None) -> Credentials:
    """Load Google OAuth credentials - per-user if phone provided, else global token.

    Uses core.oauth_per_user.get_user_credentials which centralises refresh logic.
    """
    if phone:
        try:
            from core.oauth_per_user import get_user_credentials

            creds = get_user_credentials(phone)
            if creds is not None:
                return creds
        except Exception as e:
            logger.warning(f"Per-user credentials failed for {phone}: {e}")

    from core.secrets import get_secret
    token_json = get_secret("GOOGLE_OAUTH_TOKEN")
    if not token_json:
        raise RuntimeError("GOOGLE_OAUTH_TOKEN not configured")
    token_data = json.loads(token_json) if isinstance(token_json, str) else token_json
    return Credentials.from_authorized_user_info(token_data, SCOPES)


def _get_service(phone: Optional[str] = None):
    """Get or build Calendar API service (cached per user)."""
    cache_key = phone or "_global_"
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


async def list_events(
    time_min: str,
    time_max: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    max_results: int = 50,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """List calendar events between time_min and time_max.

    Args:
        time_min: ISO 8601 datetime (e.g., "2026-07-13T00:00:00-03:00")
        time_max: ISO 8601 datetime
        calendar_id: Calendar to query (default: primary)
        max_results: Max events to return (default: 50)
        phone: User phone for per-user OAuth token

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


async def create_event(
    start: str,
    end: str,
    summary: str,
    description: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    location: Optional[str] = None,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new calendar event.

    Args:
        start: ISO 8601 datetime
        end: ISO 8601 datetime
        summary: Event title
        description: Event description
        attendees: List of email addresses
        location: Event location
        calendar_id: Calendar to add event to
        phone: User phone for per-user OAuth token

    Returns:
        {"event": {...}} on success or {"error": str}
    """
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
        return {"error": str(e)}


async def update_event(
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    phone: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Update an existing event.

    Args:
        event_id: Event ID to update
        calendar_id: Calendar containing the event
        phone: User phone for per-user OAuth token
        **kwargs: Fields to update (start, end, summary, description, location, attendees)

    Returns:
        {"event": {...}} or {"error": str}
    """
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
        return {"error": str(e)}


async def delete_event(
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete a calendar event.

    Args:
        event_id: Event ID to delete
        calendar_id: Calendar containing the event
        phone: User phone for per-user OAuth token

    Returns:
        {"deleted": True} or {"error": str}
    """
    try:
        service = _get_service(phone)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id}
    except HttpError as e:
        logger.error(f"Calendar delete_event error: {e}")
        return {"error": str(e)}


async def freebusy(
    time_min: str,
    time_max: str,
    calendars: Optional[List[str]] = None,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Check free/busy status for calendars.

    Args:
        time_min: ISO 8601 datetime
        time_max: ISO 8601 datetime
        calendars: List of calendar IDs (default: ["primary"])
        phone: User phone for per-user OAuth token

    Returns:
        {"busy": [{"start": ..., "end": ...}, ...], "calendars": [...]}
    """
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
