"""Owner-only guard for Google tools.

Wraps each user-scoped tool so that Gmail/Drive/Calendar calls are executed
only when the inbound phone matches the owner phone bound to the Evolution
instance. The wrap is applied at runtime to keep tool schemas static while
preserving per-call authorization.
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Awaitable, Callable, Dict

from core.owner import OwnerResolution, deny_if_not_owner, resolve_owner

logger = logging.getLogger(__name__)


async def _invoke_with_guard(
    func: Callable[..., Awaitable[Dict[str, Any]]],
    capability: str,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    phone = str(kwargs.get("phone", ""))
    instance = str(kwargs.get("instance", "") or kwargs.get("_instance", ""))
    resolution: OwnerResolution | None = None
    if instance:
        resolution = resolve_owner(instance, fallback_phone=phone)
    denial = deny_if_not_owner(resolution, phone, capability)
    if denial is not None:
        return denial
    return await func(**kwargs)


def guard_owner_only(capability: str) -> Callable[[Callable[..., Awaitable[Dict[str, Any]]]], Callable[..., Awaitable[Dict[str, Any]]]]:
    def decorator(func: Callable[..., Awaitable[Dict[str, Any]]]) -> Callable[..., Awaitable[Dict[str, Any]]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            return await _invoke_with_guard(func, capability, dict(kwargs))
        return wrapper
    return decorator
