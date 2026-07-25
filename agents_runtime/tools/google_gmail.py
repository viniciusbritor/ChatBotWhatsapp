"""Google Gmail tools - 3 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.
The phone parameter is mandatory (Fase D); the global GOOGLE_OAUTH_TOKEN
fallback was removed.

Owner-only: Gmail access is restricted to the phone bound to the Evolution
instance. Any other phone is denied with an ``owner_only_capability`` error.
"""
import base64
import functools
import logging
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
_gmail_services: Dict[str, Any] = {}


def _get_credentials(phone: str) -> Credentials:
    """Load Google OAuth credentials for the given user (per-user, Fase D)."""
    if not phone:
        raise RuntimeError("phone_required_for_gmail_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        raise RuntimeError("user_google_oauth_required")
    return creds


def _get_service(phone: str):
    """Get or build Gmail API service (cached per user)."""
    cache_key = phone
    if cache_key not in _gmail_services:
        creds = _get_credentials(phone)
        _gmail_services[cache_key] = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _gmail_services[cache_key]


def _decode_body(data: str) -> str:
    """Decode base64url-encoded email body."""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: Dict[str, Any]) -> str:
    """Extract plain text body from email payload."""
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain" and payload.get("body", {}).get("data"):
        return _decode_body(payload["body"]["data"])
    for part in payload.get("parts", []):
        body = _extract_body(part)
        if body:
            return body
    return ""


def _format_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
        "body": _extract_body(msg.get("payload", {})),
    }


def _owner_guard(capability: str):
    """Allow only the owner phone to invoke Gmail capabilities."""
    from core.owner import deny_if_not_owner, resolve_owner

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
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


@_owner_guard("gmail.search")
async def search_messages(
    phone: str,
    query: str,
    max_results: int = 10,
    label_ids: Optional[List[str]] = None,
    instance: str = "",
) -> Dict[str, Any]:
    """Search Gmail messages.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        query: Gmail search query (e.g., "from:user@example.com", "subject:meeting")
        max_results: Max results
        label_ids: Filter by labels (e.g., ["INBOX"])

    Returns:
        {"messages": [...], "count": int}
    """
    try:
        service = _get_service(phone)
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
            labelIds=label_ids,
        ).execute()

        messages_data = result.get("messages", [])
        detailed = []
        for m in messages_data[:max_results]:
            full = service.users().messages().get(
                userId="me",
                id=m["id"],
                format="full",
            ).execute()
            detailed.append(_format_message(full))

        return {"messages": detailed, "count": len(detailed)}
    except HttpError as e:
        logger.error(f"Gmail search_messages error: {e}")
        return {"messages": [], "count": 0, "error": str(e)}


@_owner_guard("gmail.thread")
async def get_thread(
    phone: str,
    thread_id: str,
    instance: str = "",
) -> Dict[str, Any]:
    """Get all messages in a thread.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        thread_id: Gmail thread ID

    Returns:
        {"messages": [...], "count": int}
    """
    try:
        service = _get_service(phone)
        thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        messages = [_format_message(m) for m in thread.get("messages", [])]
        return {"messages": messages, "count": len(messages)}
    except HttpError as e:
        logger.error(f"Gmail get_thread error: {e}")
        return {"messages": [], "count": 0, "error": str(e)}


@_owner_guard("gmail.send")
async def send_message(
    phone: str,
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    html: bool = False,
    instance: str = "",
) -> Dict[str, Any]:
    """Send an email.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        to: Recipient email
        subject: Email subject
        body: Email body
        thread_id: Optional thread ID for replies
        html: If True, body is HTML; else plain text

    Returns:
        {"message": {...}} or {"error": str}
    """
    try:
        service = _get_service(phone)
        content_type = "text/html" if html else "text/plain"
        message = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: {content_type}; charset=UTF-8\r\n\r\n{body}"
        raw = base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8").rstrip("=")
        body_payload = {"raw": raw}
        if thread_id:
            body_payload["threadId"] = thread_id

        sent = service.users().messages().send(userId="me", body=body_payload).execute()
        return {
            "message": {
                "id": sent.get("id"),
                "thread_id": sent.get("threadId"),
                "to": to,
                "subject": subject,
            }
        }
    except HttpError as e:
        logger.error(f"Gmail send_message error: {e}")
        return {"error": str(e)}
