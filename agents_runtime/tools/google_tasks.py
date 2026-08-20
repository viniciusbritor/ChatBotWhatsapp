"""Google Tasks tools - 3 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.
The phone parameter is mandatory (Fase D).
"""
import functools
import logging
from typing import Optional, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/tasks"]
_tasks_services: Dict[str, Any] = {}


def clear_user_cache(phone: str) -> bool:
    """GUARDRAIL §0.7 (19/08/2026): remove o servico Tasks em cache."""
    if not phone:
        return False
    cache_key = str(phone)
    removed = _tasks_services.pop(cache_key, None)
    return removed is not None


def _get_credentials(phone: str) -> Credentials:
    if not phone:
        logger.error("tasks_oauth_missing phone=empty")
        raise RuntimeError("phone_required_for_tasks_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        logger.error("tasks_oauth_missing phone=%s", phone)
        raise RuntimeError("user_google_oauth_required")
    return creds


def _get_service(phone: str):
    cache_key = phone
    if cache_key not in _tasks_services:
        creds = _get_credentials(phone)
        _tasks_services[cache_key] = build("tasks", "v1", credentials=creds, cache_discovery=False)
    return _tasks_services[cache_key]


def _owner_guard(capability: str):
    """Allow only the owner phone to invoke Tasks capabilities."""
    from core.owner import deny_if_not_owner, resolve_owner
    from core.owner_guard import check_folder_permission, post_filter_tool_result

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
            fp_denial = check_folder_permission(phone, capability, kwargs)
            if fp_denial is not None:
                return fp_denial
            result = await func(*args, **kwargs)
            return await post_filter_tool_result(phone, capability, result, kwargs)
        return wrapper
    return decorator


@_owner_guard("tasks.read")
async def list_tasks(phone: str, tasklist_id: str = "@default", max_results: int = 20) -> Dict[str, Any]:
    """Lista tarefas da lista padrão do usuário."""
    try:
        service = _get_service(phone)
        result = service.tasks().list(tasklist=tasklist_id, maxResults=max_results).execute()
        items = result.get("items", [])
        return {"tasks": [
            {
                "id": t.get("id"),
                "title": t.get("title", ""),
                "notes": t.get("notes", ""),
                "due": t.get("due", ""),
                "status": t.get("status", "needsAction"),
                "completed": t.get("completed", ""),
            }
            for t in items
        ], "count": len(items)}
    except HttpError as e:
        logger.error(f"Tasks list error: {e}")
        return {"error": str(e)}


@_owner_guard("tasks.write")
async def create_task(phone: str, title: str, notes: str = "", due: str = "", tasklist_id: str = "@default") -> Dict[str, Any]:
    """Cria uma nova tarefa na lista padrão."""
    try:
        service = _get_service(phone)
        body: Dict[str, Any] = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due
        created = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
        return {"task": {
            "id": created.get("id"),
            "title": created.get("title", ""),
            "notes": created.get("notes", ""),
            "due": created.get("due", ""),
            "status": created.get("status", "needsAction"),
        }}
    except HttpError as e:
        logger.error(f"Tasks create error: {e}")
        return {"error": str(e)}


@_owner_guard("tasks.write")
async def update_task(phone: str, task_id: str, completed: bool = False, title: Optional[str] = None, tasklist_id: str = "@default") -> Dict[str, Any]:
    """Atualiza uma tarefa (marca concluída ou renomeia)."""
    try:
        service = _get_service(phone)
        existing = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        if title is not None:
            existing["title"] = title
        existing["status"] = "completed" if completed else "needsAction"
        if completed:
            import datetime
            existing["completed"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated = service.tasks().update(tasklist=tasklist_id, task=task_id, body=existing).execute()
        return {"task": {
            "id": updated.get("id"),
            "title": updated.get("title", ""),
            "status": updated.get("status", ""),
            "completed": updated.get("completed", ""),
        }}
    except HttpError as e:
        logger.error(f"Tasks update error: {e}")
        return {"error": str(e)}
