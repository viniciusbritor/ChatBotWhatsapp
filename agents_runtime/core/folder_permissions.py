"""Per-user folder permissions (TASK A 30/07/2026).

Permite ao admin module (web) conceder/revogar acesso do user
a pastas especificas de Calendar/Gmail/GDrive. Sem isso, o bot
usa o token OAuth global do user e tem acesso a TODOS os dados.

Storage: usuarios/{phone}/folder_permissions/{permission_id}

Schema:
{
  permission_id: str (auto-generated ULID-like)
  tool: 'drive' | 'gmail' | 'calendar'
  scope: 'whitelist' | 'blacklist'
  pattern: str (folder_id, email_pattern, event_id_pattern, ou '*')
  created_at: ISO datetime
  created_by: 'admin-sa-token' ou phone
}

Runtime enforcement (IMPLEMENTADO):
- tools/google_drive.py::search_files filtra resultados por
  permissions.whitelist[pattern] e exclui blacklisted[pattern]
- tools/google_gmail.py::search_messages similar
- tools/google_calendar.py::list_events similar
- core/owner_guard.py: check_folder_permission (pre) +
  post_filter_tool_result (pos). Owner da instancia tem bypass.
- Toggle: RAG_FOLDER_PERMISSIONS_ENFORCE (default "true").
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


VALID_TOOLS = frozenset({"drive", "gmail", "calendar"})
VALID_SCOPES = frozenset({"whitelist", "blacklist"})


def _now_iso() -> str:
    """ISO datetime BRT (UTC-3) - matches core.rag pattern."""
    from core.timezone import now_brt

    return now_brt().isoformat()


def _get_firestore_client():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "coherence-ominichannel-fs"
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("folder_permissions firestore unavailable: %s", exc)
        return None


def _gen_permission_id(tool: str, pattern: str) -> str:
    """Generate deterministic-ish permission_id from tool+pattern."""
    seed = f"{tool}::{pattern}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:16]


def grant_folder_permission(
    phone: str,
    tool: str,
    pattern: str,
    scope: str = "whitelist",
    created_by: str = "admin-sa-token",
) -> Optional[Dict[str, Any]]:
    """Concede (ou adiciona a blacklist) permissao para pattern.

    Args:
        phone: telefone do user (com ou sem +55).
        tool: 'drive' | 'gmail' | 'calendar'.
        pattern: folder_id, email_pattern, event_id_pattern, ou '*'.
        scope: 'whitelist' (default) ou 'blacklist'.
        created_by: quem criou (audit).

    Returns:
        Dict com permission_id + data, ou None se Firestore indisponivel.
    """
    if tool not in VALID_TOOLS:
        raise ValueError(f"tool invalido: {tool}")
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope invalido: {scope}")
    if not pattern or not pattern.strip():
        raise ValueError("pattern nao pode ser vazio")

    db = _get_firestore_client()
    if db is None:
        return None

    permission_id = _gen_permission_id(tool, pattern)
    data = {
        "permission_id": permission_id,
        "phone": phone,
        "tool": tool,
        "scope": scope,
        "pattern": pattern,
        "created_at": _now_iso(),
        "created_by": created_by,
    }
    try:
        db.collection("usuarios").document(phone).collection(
            "folder_permissions"
        ).document(permission_id).set(data, merge=True)
        logger.info(
            "folder_permission granted phone=%s tool=%s pattern=%s scope=%s",
            phone, tool, pattern, scope,
        )
        force_reload_cache(phone)
        return data
    except Exception as exc:
        logger.error("grant_folder_permission falhou: %s", exc)
        return None


def list_folder_permissions(phone: str) -> List[Dict[str, Any]]:
    """Lista todas as permissoes do user."""
    db = _get_firestore_client()
    if db is None:
        return []
    try:
        docs = (
            db.collection("usuarios").document(phone)
            .collection("folder_permissions")
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception as exc:
        logger.error("list_folder_permissions falhou: %s", exc)
        return []


def revoke_folder_permission(phone: str, permission_id: str) -> bool:
    """Remove permissao. Retorna True se removeu."""
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        db.collection("usuarios").document(phone).collection(
            "folder_permissions"
        ).document(permission_id).delete()
        logger.info(
            "folder_permission revoked phone=%s id=%s",
            phone, permission_id,
        )
        force_reload_cache(phone)
        return True
    except Exception as exc:
        logger.error("revoke_folder_permission falhou: %s", exc)
        return False


_PERMISSION_CACHE: Dict[str, tuple] = {}
_CACHE_TTL_SEC = 60


def _permissions_cached(phone: str) -> List[Dict[str, Any]]:
    """Cache in-process de permissoes para evitar round-trip
    Firestore a cada tool call (60s TTL)."""
    now = time.time()
    if phone in _PERMISSION_CACHE:
        perms, cached_at = _PERMISSION_CACHE[phone]
        if now - cached_at < _CACHE_TTL_SEC:
            return perms
    perms = list_folder_permissions(phone)
    _PERMISSION_CACHE[phone] = (perms, now)
    return perms


def force_reload_cache(phone: Optional[str] = None) -> None:
    """Invalidacao de cache apos write. Se phone=None, limpa tudo."""
    if phone is None:
        _PERMISSION_CACHE.clear()
    else:
        _PERMISSION_CACHE.pop(phone, None)


def get_user_allowed_tools(phone: str) -> Dict[str, List[str]]:
    """Helper para runtime enforcement (Fase 2).

    Returns:
        {'drive': ['folder1', 'folder2'],
         'gmail': ['*'],
         'calendar': []}
    """
    perms = _permissions_cached(phone)
    allowed: Dict[str, List[str]] = {tool: [] for tool in VALID_TOOLS}
    for p in perms:
        if p.get("scope") == "whitelist" and p.get("tool") in allowed:
            allowed[p["tool"]].append(p["pattern"])
    return allowed


__all__ = [
    "VALID_TOOLS",
    "VALID_SCOPES",
    "grant_folder_permission",
    "list_folder_permissions",
    "revoke_folder_permission",
    "get_user_allowed_tools",
    "force_reload_cache",
]
