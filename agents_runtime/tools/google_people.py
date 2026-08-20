"""Google People API tools - 2 functions.

Auth: per-user OAuth via core.oauth_per_user.get_user_credentials.
"""
import functools
import logging
from typing import Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/contacts.readonly"]
_people_services: Dict[str, Any] = {}


def clear_user_cache(phone: str) -> bool:
    """GUARDRAIL §0.7 (19/08/2026): remove o servico People em cache."""
    if not phone:
        return False
    cache_key = str(phone)
    removed = _people_services.pop(cache_key, None)
    return removed is not None


def _get_credentials(phone: str) -> Credentials:
    if not phone:
        logger.error("people_oauth_missing phone=empty")
        raise RuntimeError("phone_required_for_people_oauth")
    from core.oauth_per_user import get_user_credentials

    creds = get_user_credentials(phone)
    if creds is None:
        logger.error("people_oauth_missing phone=%s", phone)
        raise RuntimeError("user_google_oauth_required")
    return creds


def _get_service(phone: str):
    cache_key = phone
    if cache_key not in _people_services:
        creds = _get_credentials(phone)
        _people_services[cache_key] = build("people", "v1", credentials=creds, cache_discovery=False)
    return _people_services[cache_key]


def _owner_guard(capability: str):
    """Allow only the owner phone to invoke People capabilities."""
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


@_owner_guard("people.read")
async def search_contacts(phone: str, query: str, page_size: int = 10) -> Dict[str, Any]:
    """Busca contatos do usuário pelo nome/email/telefone."""
    try:
        service = _get_service(phone)
        result = service.people().searchContacts(
            query=query,
            pageSize=page_size,
            readMask="names,emailAddresses,phoneNumbers,organizations",
        ).execute()
        results = result.get("results", [])
        return {"contacts": [
            _format_person(r.get("person", {}))
            for r in results
        ], "count": len(results)}
    except HttpError as e:
        logger.error(f"People search error: {e}")
        return {"error": str(e)}


@_owner_guard("people.read")
async def get_profile(phone: str) -> Dict[str, Any]:
    """Retorna o perfil do próprio usuário autenticado."""
    try:
        service = _get_service(phone)
        person = service.people().get(
            resourceName="people/me",
            personFields="names,emailAddresses,phoneNumbers,organizations,photos",
        ).execute()
        return {"person": _format_person(person)}
    except HttpError as e:
        logger.error(f"People profile error: {e}")
        return {"error": str(e)}


def _format_person(person: Dict[str, Any]) -> Dict[str, Any]:
    names = person.get("names") or []
    emails = person.get("emailAddresses") or []
    phones = person.get("phoneNumbers") or []
    orgs = person.get("organizations") or []
    return {
        "nome": (names[0].get("displayName") if names else ""),
        "emails": [e.get("value") for e in emails],
        "telefones": [p.get("value") for p in phones],
        "empresa": (orgs[0].get("name") if orgs else ""),
        "cargo": (orgs[0].get("title") if orgs else ""),
    }
