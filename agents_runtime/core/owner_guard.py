"""Owner-only guard for Google tools.

Wraps each user-scoped tool so that Gmail/Drive/Calendar calls are executed
only when:
1. The inbound phone matches the owner phone bound to the Evolution instance
   (resolução de instância via core.owner.resolve_owner), E
2. A folder_permission whitelist autoriza o pattern solicitado (TASK B RAG
   runtime enforcement), por tool (drive/gmail/calendar).

O padrão sem whitelist (fall-back) é **lock-down** = tool retorna vazio
sem chamar a API do Google. Isso é por design de Fase B: sem permissão
concedida, não há dados retornados.

Default off: o guard de folder_permissions respeita env var
``RAG_FOLDER_PERMISSIONS_ENFORCE`` (default "true" em runtime). Em
dev/test pode-se desligar com ``RAG_FOLDER_PERMISSIONS_ENFORCE=false``.

Owner bypass (Fase 01/08/2026): o owner da instance (já validado por
``deny_if_not_owner``) tem acesso total aos próprios dados sem precisar
de grants em folder_permissions. TASK B continua valendo para
non-owners (preparação para multi-user futuro). Resolve o bug onde TASK B
bloqueava o owner porque whitelist estava vazia — agora tools não podem
falhar para o owner.
"""
from __future__ import annotations

import functools
import logging
import os
import re
from typing import Any, Awaitable, Callable, Dict, Optional

from core.owner import OwnerResolution, deny_if_not_owner, resolve_owner

logger = logging.getLogger(__name__)

# Capacidade -> tool name em get_user_allowed_tools
CAPABILITY_TO_TOOL = {
    "drive.list": "drive",
    "drive.upload": "drive",
    "drive.create_folder": "drive",
    "drive.find_omnichannel_atas": "drive",
    "drive.read_file": "drive",
    "drive.deep_search": "drive",
    "drive.search": "drive",
    "drive.read": "drive",
    "gmail.thread": "gmail",
    "gmail.send": "gmail",
    "gmail.search": "gmail",
    "calendar.list": "calendar",
    "calendar.create": "calendar",
    "calendar.update": "calendar",
}

ENFORCE_ENABLED = os.getenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "true").lower() == "true"


def is_enforce_enabled() -> bool:
    """Indica se o enforcement de folder_permissions está ativo (re-leitura
    da env var a cada chamada para permitir toggle em runtime/test)."""
    return os.getenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "true").lower() == "true"


def _extract_patterns_for_capability(
    capability: str, kwargs: Dict[str, Any]
) -> list:
    """Para uma capability, retorna os patterns solicitados.

    Drive patterns: folder_id, query, parent_id.
    Gmail patterns: from/endereços contidos no query (best-effort).
    Calendar patterns: calendar_id, summary/substring em summary.
    """
    tool = CAPABILITY_TO_TOOL.get(capability, "")
    if not tool:
        return []
    patterns = []
    for key in ("folder_id", "query", "parent_id", "calendar_id", "summary"):
        value = kwargs.get(key)
        if value:
            patterns.append(str(value))
    return patterns


def _check_folder_permission(
    phone: str, capability: str, kwargs: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Retorna dict denial se a operação não for autorizada pela whitelist.

    Lock-down semantics:
    - whitelist vazia para o tool -> permite SOMENTE se ENFORCE_LOCKDOWN
      for False. Default em runtime: deny tudo.
    - whitelist populada, kwargs nao referencia nenhum pattern -> permite
      (a tool cuida de filtrar a partir do lado servidor; aqui só bloqueamos
      tentativas de bypass explícito).
    - whitelist populada, kwargs referencia pattern fora da whitelist -> deny.

    Owner bypass (01/08/2026): o caller ``_invoke_with_guard`` já validou
    que o phone é o owner da instance via ``deny_if_not_owner``. Quando o
    bypass está ativo, retornamos ``None`` (allow) sem consultar Firestore,
    eliminando o vetor de falha onde folder_permissions vazio bloqueia o
    owner. TASK B continua valendo para non-owners (preparação multi-user).
    """
    if not is_enforce_enabled():
        return None
    if not phone:
        return {
            "error": "missing_phone",
            "message": "tool chamada sem phone, nao foi possivel checar permissoes",
        }

    # Owner bypass: phone que resolve para owner da instance recebe allow
    # sem consultar folder_permissions. Dupla validação: deny_if_not_owner
    # no caller (_invoke_with_guard) já confirmou owner.
    instance = str(kwargs.get("instance", "") or kwargs.get("_instance", ""))
    if not instance:
        from core.runtime_context import get_instance
        instance = get_instance()
    if instance:
        try:
            resolution = resolve_owner(instance, fallback_phone=phone)
            if resolution is not None:
                digits = re.sub(r"\D", "", phone or "")
                if digits and any(digits == c for c in resolution.owner_candidates):
                    logger.info(
                        "owner_bypass_folder_permission phone=%s capability=%s instance=%s",
                        phone, capability, instance,
                    )
                    return None  # allow
        except Exception as exc:
            # Fail-open: se nao conseguir resolver owner, segue com check
            # normal (defesa em profundidade).
            logger.debug(
                "owner_bypass_check_failed phone=%s exc=%s", phone, exc,
            )
    # Multi-tenant: Se o usuário tem token Google OAuth próprio válido no Firestore, permita!
    try:
        from core.oauth_per_user import get_user_oauth
        token_data = get_user_oauth(phone)
        if token_data and token_data.get("scopes"):
            return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("owner_guard_multi_tenant_oauth_check_failed phone=%s exc=%s", phone, exc)

    try:
        from core.folder_permissions import get_user_allowed_tools

        allowed_map = get_user_allowed_tools(phone)
    except Exception as exc:
        logger.warning(
            "enforce_folder_permissions: get_user_allowed_tools falhou phone=%s exc=%s",
            phone, exc,
        )
        return None  # fail-open na indisponibilidade

    tool = CAPABILITY_TO_TOOL.get(capability, "")
    if not tool:
        return None  # tool nao mapeada: nao enforce
    allowed = allowed_map.get(tool, [])
    if not allowed:
        # Lock-down sem whitelist -> deny. Whitelist explicitamente sem pattern
        # para o tool -> vazio.
        return {
            "error": "folder_permission_required",
            "tool": tool,
            "capability": capability,
            "message": (
                f"usuario sem permissao de {tool}; conceda via "
                f"/admin/users/{phone}/folder-permissions antes de usar a tool."
            ),
        }
    # Whitelist existe. Se nenhum pattern foi passado na chamada (ex: search_files
    # sem folder_id), devolvemos permissao ampliada (qualquer arquivo da
    # whitelist). Se um pattern foi passado, exigimos match.
    patterns = _extract_patterns_for_capability(capability, kwargs)
    if not patterns:
        return None
    for p in patterns:
        if p in allowed:
            return None  # match -> permite
        # match parcial: se pattern e substring de algum allowed -> permite
        for allowed_pattern in allowed:
            if allowed_pattern and (
                p in allowed_pattern or allowed_pattern in p
            ):
                return None
    return {
        "error": "folder_permission_denied",
        "tool": tool,
        "capability": capability,
        "requested_pattern": patterns,
        "allowed_patterns": allowed,
        "message": f"pattern nao esta na whitelist do usuario para {tool}",
    }


async def _invoke_with_guard(
    func: Callable[..., Awaitable[Dict[str, Any]]],
    capability: str,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    phone = str(kwargs.get("phone", ""))
    instance = str(kwargs.get("instance", "") or kwargs.get("_instance", ""))
    if not instance:
        from core.runtime_context import get_instance
        instance = get_instance()
    resolution: OwnerResolution | None = None
    if instance:
        resolution = resolve_owner(instance, fallback_phone=phone)
    denial = deny_if_not_owner(resolution, phone, capability)
    if denial is not None:
        return denial

    fp_denial = _check_folder_permission(phone, capability, kwargs)
    if fp_denial is not None:
        return fp_denial

    result = await func(**kwargs)

    # Post-filter para tools de listagem: filtra resultados em memória
    # (a API do Google nao tem parametro de folder; temos que cortar do
    # que voltou). Isso cobre o caso em que a whitelist cobre *alguns* mas
    # nao todos os arquivos do usuario.
    try:
        tool = CAPABILITY_TO_TOOL.get(capability, "")
        if tool in {"drive", "gmail"} and isinstance(result, dict):
            # Multi-tenant / Owner bypass: não filtra resultados de quem tem OAuth próprio ou é proprietário
            from core.oauth_per_user import get_user_oauth as _guo
            _tok = _guo(phone)
            if _tok and _tok.get("scopes"):
                return result
            from core.runtime_context import get_instance as _rti
            from core.owner import resolve_owner as _ro
            _inst = _rti()
            if _inst:
                _res = _ro(_inst, fallback_phone=phone)
                if _res and _res.owner_phone == phone:
                    return result
            allowed = __import__("core.folder_permissions", fromlist=["get_user_allowed_tools"]).get_user_allowed_tools(phone).get(tool, [])
            if not allowed:
                # Lock-down -> ja barrado na pre; defensivo.
                return {**result, "files": [], "count": 0}
            if "files" in result and isinstance(result["files"], list):
                filtered = [
                    f for f in result["files"]
                    if not isinstance(f, dict)
                    or any(p in " ".join(str(f.get(k, "")) for k in ("name", "id", "parent_id", "parents")) for p in allowed)
                    or not _extract_patterns_for_capability(capability, kwargs)
                ]
                result = {**result, "files": filtered, "count": len(filtered)}
            elif "messages" in result and isinstance(result["messages"], list):
                filtered = [
                    m for m in result["messages"]
                    if not isinstance(m, dict)
                    or any(p in " ".join(str(m.get(k, "")) for k in ("from", "subject", "to")) for p in allowed)
                    or not _extract_patterns_for_capability(capability, kwargs)
                ]
                result = {**result, "messages": filtered, "count": len(filtered)}
    except Exception as exc:
        logger.debug("post_filter no-op: %s", exc)
    return result


def guard_owner_only(capability: str) -> Callable[[Callable[..., Awaitable[Dict[str, Any]]]], Callable[..., Awaitable[Dict[str, Any]]]]:
    def decorator(func: Callable[..., Awaitable[Dict[str, Any]]]) -> Callable[..., Awaitable[Dict[str, Any]]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            return await _invoke_with_guard(func, capability, dict(kwargs))
        return wrapper
    return decorator


def check_folder_permission(phone: str, capability: str, kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Helper exportado para os decoradores locais das tools
    (tools/google_drive.py::_owner_guard, etc) que nao usam guard_owner_only."""
    return _check_folder_permission(phone, capability, kwargs)


async def post_filter_tool_result(
    phone: str,
    capability: str,
    result: Dict[str, Any],
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Post-filtra o resultado de tools de listagem (drive/gmail) por whitelist."""
    if not isinstance(result, dict):
        return result
    if not is_enforce_enabled():
        return result
    try:
        tool = CAPABILITY_TO_TOOL.get(capability, "")
        if tool not in {"drive", "gmail"}:
            return result
        from core.folder_permissions import get_user_allowed_tools

        # 1. Multi-tenant / Per-user OAuth bypass: não filtra dados de quem tem OAuth próprio
        from core.oauth_per_user import get_user_oauth as _guo
        _tok = _guo(phone)
        if _tok and _tok.get("scopes"):
            return result

        # 2. Owner bypass: não filtra resultados do proprietário
        from agent_loader import resolve_owner_phone
        if phone and phone == resolve_owner_phone():
            return result

        from core.runtime_context import get_instance as _rti2
        from core.owner import resolve_owner as _ro2
        _inst2 = _rti2() or str(kwargs.get("instance") or kwargs.get("_instance") or "")
        if _inst2:
            _res2 = _ro2(_inst2, fallback_phone=phone)
            if _res2 and _res2.owner_phone == phone:
                return result

        allowed = get_user_allowed_tools(phone).get(tool, [])
        if not allowed:
            return {**result, "files": [], "count": 0} if "files" in result else (
                {**result, "messages": [], "count": 0} if "messages" in result else result
            )

        def _drive_match(f: Any) -> bool:
            if not isinstance(f, dict):
                return True
            haystack = " ".join(str(f.get(k, "")) for k in ("name", "id", "parent_id", "parents"))
            return any(p in haystack for p in allowed)

        def _mail_match(m: Any) -> bool:
            if not isinstance(m, dict):
                return True
            haystack = " ".join(str(m.get(k, "")) for k in ("from", "subject", "to"))
            return any(p in haystack for p in allowed)

        if "files" in result and isinstance(result["files"], list):
            filtered = [f for f in result["files"] if _drive_match(f)]
            return {**result, "files": filtered, "count": len(filtered)}
        if "messages" in result and isinstance(result["messages"], list):
            filtered = [m for m in result["messages"] if _mail_match(m)]
            return {**result, "messages": filtered, "count": len(filtered)}
    except Exception as exc:
        logger.debug("post_filter_tool_result no-op: %s", exc)
    return result

