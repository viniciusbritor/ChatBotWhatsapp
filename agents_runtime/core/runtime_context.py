"""Contexto de runtime compartilhado entre orchestrador e tools.

Usa contextvars para transportar valores como ``instance`` que o DeepAgent/LangChain
nao injeta automaticamente nos kwargs das tool calls.
"""
from __future__ import annotations

import contextvars

_current_instance: contextvars.ContextVar[str] = contextvars.ContextVar(
    "runtime_instance", default=""
)
_current_phone: contextvars.ContextVar[str] = contextvars.ContextVar(
    "runtime_phone", default=""
)


def set_instance(instance: str) -> None:
    _current_instance.set(instance)


def get_instance() -> str:
    return _current_instance.get()


def set_phone(phone: str) -> None:
    _current_phone.set(phone)


def get_phone() -> str:
    return _current_phone.get()
