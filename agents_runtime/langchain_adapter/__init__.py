"""Stable LangChain adapter.

Isolates the LangChain version from the rest of the codebase. If the
framework changes its public API in future releases, we update ONLY
this module. Everything else uses ``from langchain_adapter import tool``
and similar stable imports.
"""
from langchain_adapter.models import build_default_chat_model
from langchain_adapter.tools import tool

__all__ = ["build_default_chat_model", "tool"]
