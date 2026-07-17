"""Google Gmail tools - 3 functions."""
import os
import json
import base64
import logging
from datetime import datetime, timedelta
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


def _get_credentials(phone: Optional[str] = None) -> Credentials:
    """Load Google OAuth credentials — per-user if phone provided, else global token."""
    if phone:
        try:
            from agent_loader import get_user
            user = get_user(phone)
            if user and user.get("google_oauth_token"):
                token_data = user["google_oauth_token"]
                if isinstance(token_data.get("token"), str):
                    creds = Credentials(
                        token=token_data["token"],
                        refresh_token=token_data.get("refresh_token"),
                        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                        client_id=token_data.get("client_id", ""),
                        client_secret=token_data.get("client_secret", ""),
                        scopes=SCOPES,
                        expiry=datetime.fromtimestamp(float(token_data.get("expiry", 0))) if token_data.get("expiry") else None,
                    )
                    if creds.expired:
                        from google.auth.transport.requests import Request
                        creds.refresh(Request())
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
    """Get or build Gmail API service (cached per user)."""
    cache_key = phone or "_global_"
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


async def search_messages(
    query: str,
    max_results: int = 10,
    label_ids: Optional[List[str]] = None,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Search Gmail messages.

    Args:
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


async def get_thread(thread_id: str, phone: Optional[str] = None) -> Dict[str, Any]:
    """Get all messages in a thread.

    Args:
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


async def send_message(
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    html: bool = False,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email.

    Args:
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