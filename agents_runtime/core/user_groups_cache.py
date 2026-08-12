"""Cache in-memory com TTL para o contexto de grupos em comum (G3).

Substitui a collection-group query legada (group_members/member_phones) por
um lookup denormalizado: ``usuarios/{phone}.group_memberships``. O cache
elimina reads repetidos em mensagens consecutivas do mesmo user (o caso
dominante em DMs). Staleness de grupo ate o TTL e aceitavel: e contexto de
prompt, nao controle de acesso.
"""
import os
import time
from typing import Dict, Optional, Tuple

USER_GROUPS_CACHE_TTL_SEC = int(os.getenv("USER_GROUPS_CACHE_TTL_SEC", "300"))

_CACHE: Dict[str, Tuple[float, str]] = {}

# Injectavel em testes para controlar o relogio sem monkeypatch de time.
_clock = time.monotonic


def get(phone: str) -> Optional[str]:
    """Retorna o contexto cacheado ou None se ausente/expirado."""
    entry = _CACHE.get(phone)
    if entry is None:
        return None
    ts, ctx = entry
    if _clock() - ts >= USER_GROUPS_CACHE_TTL_SEC:
        _CACHE.pop(phone, None)
        return None
    return ctx


def set(phone: str, ctx: str) -> None:
    """Grava (ou sobrescreve) o contexto, inclusive "" (user sem grupos)."""
    _CACHE[phone] = (_clock(), ctx)


def invalidate(phone: str) -> None:
    """Remove a entrada (chamado pelo sync_group_members)."""
    _CACHE.pop(phone, None)


def clear() -> None:
    _CACHE.clear()


def stats() -> Dict[str, int]:
    return {"entries": len(_CACHE)}
