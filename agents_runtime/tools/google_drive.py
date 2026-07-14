"""Google Drive tools - 4 functions."""
import os
import json
import logging
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
_OMNICHANNEL_FOLDER_NAME = "Omnichannel"
_ATAS_SUBFOLDER = "Atas"

_drive_service = None


def _get_credentials() -> Credentials:
    from core.secrets import get_secret
    token_json = get_secret("GOOGLE_OAUTH_TOKEN")
    if not token_json:
        raise RuntimeError("GOOGLE_OAUTH_TOKEN not configured")
    token_data = json.loads(token_json) if isinstance(token_json, str) else token_json
    return Credentials.from_authorized_user_info(token_data, SCOPES)


def _get_service():
    global _drive_service
    if _drive_service is None:
        creds = _get_credentials()
        _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_service


def _format_file(file: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": file.get("id"),
        "name": file.get("name"),
        "mime_type": file.get("mimeType"),
        "modified": file.get("modifiedTime"),
        "size": file.get("size"),
        "web_view_link": file.get("webViewLink"),
    }


async def search_files(
    query: str,
    folder_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Search for files in Drive.

    Args:
        query: Search query (Google Drive query syntax)
        folder_id: Restrict search to folder
        mime_type: Filter by MIME type
        max_results: Max results

    Returns:
        {"files": [...], "count": int}
    """
    try:
        service = _get_service()
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


async def upload_file(
    folder_id: str,
    filename: str,
    content: str,
    mime_type: str = "text/plain",
) -> Dict[str, Any]:
    """Upload a file to Drive folder.

    Args:
        folder_id: Destination folder ID
        filename: Name of the file
        content: File content (string)
        mime_type: MIME type (default text/plain)

    Returns:
        {"file": {...}} or {"error": str}
    """
    try:
        service = _get_service()
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


async def list_folder(
    folder_id: str = "root",
    max_results: int = 50,
) -> Dict[str, Any]:
    """List contents of a folder.

    Args:
        folder_id: Folder ID (default: root)
        max_results: Max results

    Returns:
        {"files": [...], "count": int}
    """
    try:
        service = _get_service()
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


async def create_folder(
    name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a folder.

    Args:
        name: Folder name
        parent_id: Parent folder ID (None for root)

    Returns:
        {"folder": {...}} or {"error": str}
    """
    try:
        service = _get_service()
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


async def find_omnichannel_atas_folder() -> Dict[str, Any]:
    """Find the Omnichannel/Atas/ folder, creating if missing.

    Returns:
        {"folder_id": "..."} or {"error": str}
    """
    try:
        service = _get_service()
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

        created = await create_folder(_ATAS_SUBFOLDER, parent_id=omnichannel_id)
        if "folder" in created:
            return {"folder_id": created["folder"]["id"]}
        return {"error": "failed to create Atas folder"}
    except HttpError as e:
        logger.error(f"Drive find_omnichannel_atas_folder error: {e}")
        return {"error": str(e)}