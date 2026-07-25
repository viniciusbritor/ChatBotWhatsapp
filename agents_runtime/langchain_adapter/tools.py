"""Stable wrapper around ``langchain_core.tools.tool``.

Fase M (25/07/2026): migrating from langchain-core 0.3.x to 1.4.x.
The ``@tool`` decorator API is stable across these versions but we
isolate the import here so future upgrades are localized.

Usage:
    from langchain_adapter import tool

    @tool
    async def my_tool(arg: str) -> str:
        \"\"\"Tool description for the LLM.\"\"\"
        return f\"result for {arg}\"
"""
from __future__ import annotations

try:
    from langchain_core.tools import tool as _lc_tool_v1
except ImportError as exc:  # pragma: no cover - defensive
    raise ImportError(
        "langchain-core>=1.4.8 is required. Run: pip install -r requirements.txt"
    ) from exc


def tool(*args, **kwargs):
    """Stable wrapper around langchain_core 1.x ``@tool`` decorator.

    Accepts the same arguments as ``langchain_core.tools.tool``.
    """
    return _lc_tool_v1(*args, **kwargs)
