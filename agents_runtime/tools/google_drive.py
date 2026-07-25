"""Google Drive tools - 4 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.
The phone parameter is mandatory (Fase D); the global GOOGLE_OAUTH_TOKEN
fallback was removed.

Owner-only: Drive access is restricted to the phone bound to the Evolution
instance. Any other phone is denied with an ``owner_only_capability`` error.
"""
import functools
import logging
from typing import Optional, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]
_OMNICHANNEL_FOLDER_NAME = "Omnichannel"
_ATAS_SUBFOLDER = "Atas"

_drive_services: Dict[str, Any] = {}


def _get_credentials(phone: str) -> Credentials:
    """Load Google OAuth credentials for the given user (per-user, Fase D)."""
    if not phone:
        raise RuntimeError("phone_required_for_drive_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        raise RuntimeError("user_google_oauth_required")
    return creds


def _get_service(phone: str):
    """Get or build Drive API service (cached per user)."""
    cache_key = phone
    if cache_key not in _drive_services:
        creds = _get_credentials(phone)
        _drive_services[cache_key] = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_services[cache_key]


def _format_file(file: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": file.get("id"),
        "name": file.get("name"),
        "mime_type": file.get("mimeType"),
        "modified": file.get("modifiedTime"),
        "size": file.get("size"),
        "web_view_link": file.get("webViewLink"),
    }


def _owner_guard(capability: str):
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


@_owner_guard("drive.search")
async def search_files(
    phone: str,
    query: str,
    folder_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    max_results: int = 20,
    instance: str = "",
) -> Dict[str, Any]:
    """Search for files in Drive.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        query: Search query (Google Drive query syntax)
        folder_id: Restrict search to folder
        mime_type: Filter by MIME type
        max_results: Max results

    Returns:
        {"files": [...], "count": int}
    """
    try:
        service = _get_service(phone)
        q_parts = [f"name contains '{query}'" if query else ""]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if mime_type:
            q_parts.append(f"mimeType='{mime_type}'")
        q = " and ".join(p for p in q_parts if p)

        result = service.files().list(
            q=q if q else None,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
        ).execute()
        files = [_format_file(f) for f in result.get("files", [])]
        return {"files": files, "count": len(files)}
    except HttpError as e:
        logger.error(f"Drive search_files error: {e}")
        return {"files": [], "count": 0, "error": str(e)}


@_owner_guard("drive.upload")
async def upload_file(
    phone: str,
    folder_id: str,
    filename: str,
    content: str,
    mime_type: str = "text/plain",
    instance: str = "",
) -> Dict[str, Any]:
    """Upload a file to Drive folder.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        folder_id: Destination folder ID
        filename: Name of the file
        content: File content (string)
        mime_type: MIME type (default text/plain)

    Returns:
        {"file": {...}} or {"error": str}
    """
    try:
        service = _get_service(phone)
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype=mime_type,
            resumable=True,
        )
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, modifiedTime, size, webViewLink",
        ).execute()
        return {"file": _format_file(uploaded)}
    except HttpError as e:
        logger.error(f"Drive upload_file error: {e}")
        return {"error": str(e)}


@_owner_guard("drive.list")
async def list_folder(
    phone: str,
    folder_id: str = "root",
    max_results: int = 50,
    instance: str = "",
) -> Dict[str, Any]:
    """List contents of a folder.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        folder_id: Folder ID (default: root)
        max_results: Max results

    Returns:
        {"files": [...], "count": int}
    """
    try:
        service = _get_service(phone)
        if folder_id == "root":
            query = "'root' in parents"
        else:
            query = f"'{folder_id}' in parents"

        result = service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
        ).execute()
        files = [_format_file(f) for f in result.get("files", [])]
        return {"files": files, "count": len(files)}
    except HttpError as e:
        logger.error(f"Drive list_folder error: {e}")
        return {"files": [], "count": 0, "error": str(e)}


@_owner_guard("drive.create_folder")
async def create_folder(
    phone: str,
    name: str,
    parent_id: Optional[str] = None,
    instance: str = "",
) -> Dict[str, Any]:
    """Create a folder.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        name: Folder name
        parent_id: Parent folder ID (None for root)

    Returns:
        {"folder": {...}} or {"error": str}
    """
    try:
        service = _get_service(phone)
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = service.files().create(body=metadata, fields="id, name, mimeType").execute()
        return {"folder": _format_file(folder)}
    except HttpError as e:
        logger.error(f"Drive create_folder error: {e}")
        return {"error": str(e)}


@_owner_guard("drive.find_omnichannel_atas")
async def find_omnichannel_atas_folder(phone: str, instance: str = "") -> Dict[str, Any]:
    """Find the Omnichannel/Atas/ folder, creating if missing.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).

    Returns:
        {"folder_id": "..."} or {"error": str}
    """
    try:
        service = _get_service(phone)
        results = service.files().list(
            q=f"name='{_OMNICHANNEL_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id, name)",
        ).execute()
        files = results.get("files", [])
        if not files:
            return {"error": f"{_OMNICHANNEL_FOLDER_NAME} folder not found"}
        omnichannel_id = files[0]["id"]

        atas_results = service.files().list(
            q=f"name='{_ATAS_SUBFOLDER}' and mimeType='application/vnd.google-apps.folder' and '{omnichannel_id}' in parents",
            fields="files(id, name)",
        ).execute()
        atas_files = atas_results.get("files", [])
        if atas_files:
            return {"folder_id": atas_files[0]["id"]}

        created = await create_folder(phone, _ATAS_SUBFOLDER, parent_id=omnichannel_id)
        if "folder" in created:
            return {"folder_id": created["folder"]["id"]}
        return {"error": "failed to create Atas folder"}
    except HttpError as e:
        logger.error(f"Drive find_omnichannel_atas_folder error: {e}")
        return {"error": str(e)}
