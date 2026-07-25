"""LangChain tool wrappers for Google Calendar, Gmail, Drive, and Web search.

Each function is wrapped with the LangChain ``@tool`` decorator so that
DeepAgents (built on LangGraph) can call them as native tools. The
underlying business logic stays in ``tools/google_*.py`` and the owner
guard is preserved.

The DeepAgents harness handles:
- Tool calling loop (no more manual loop in ``core.llm_provider``)
- Context offloading for large tool results
- Sub-agent spawning for parallel tool calls
- Tool call timeout and retry

These wrappers are THIN: they only convert async/sync callables to the
LangChain tool format. Owner guard, OAuth and error handling remain in
the underlying tools.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from langchain_core.tools import tool
except ImportError as exc:
    raise ImportError(
        "langchain-core is required. Install with: pip install langchain-core>=0.3.0"
    ) from exc

logger = logging.getLogger(__name__)


def _build_langchain_tools_for(manager_id: str) -> List[Any]:
    """Build the LangChain tool list for a given manager.

    Returns the list of wrapped tools. Each tool is a ``langchain_core.tools.BaseTool``
    instance that can be passed directly to ``create_deep_agent``.

    Args:
        manager_id: One of ``manager-calendar``, ``manager-email``,
            ``manager-drive``, ``manager-web``. Other values return [].
    """
    if manager_id == "manager-calendar":
        return _build_calendar_tools()
    if manager_id == "manager-email":
        return _build_email_tools()
    if manager_id == "manager-drive":
        return _build_drive_tools()
    if manager_id == "manager-web":
        return _build_web_tools()
    logger.warning("unknown manager_id=%s", manager_id)
    return []


def _build_calendar_tools() -> List[Any]:
    from tools import google_calendar

    @tool
    async def list_calendar_events(
        phone: str,
        time_min: str,
        time_max: str,
        max_results: int = 50,
    ) -> Dict[str, Any]:
        """List Google Calendar events between time_min and time_max.

        Args:
            phone: User phone (e.g. +5511999999999) for per-user OAuth.
            time_min: Start of the time window in ISO 8601 (e.g. 2026-07-23T00:00:00-03:00).
            time_max: End of the time window in ISO 8601.
            max_results: Maximum number of events to return. Default 50.
        """
        return await google_calendar.list_events(
            phone=phone,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )

    @tool
    async def create_calendar_event(
        phone: str,
        start: str,
        end: str,
        summary: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Google Calendar event.

        Args:
            phone: User phone for per-user OAuth.
            start: Event start in ISO 8601.
            end: Event end in ISO 8601.
            summary: Event title.
            description: Optional event description.
            location: Optional event location.
        """
        return await google_calendar.create_event(
            phone=phone,
            start=start,
            end=end,
            summary=summary,
            description=description,
            location=location,
        )

    @tool
    async def calendar_freebusy(
        phone: str,
        time_min: str,
        time_max: str,
    ) -> Dict[str, Any]:
        """Check free/busy status of the primary calendar.

        Args:
            phone: User phone for per-user OAuth.
            time_min: Start of the time window in ISO 8601.
            time_max: End of the time window in ISO 8601.
        """
        return await google_calendar.freebusy(
            phone=phone,
            time_min=time_min,
            time_max=time_max,
        )

    return [list_calendar_events, create_calendar_event, calendar_freebusy]


def _build_email_tools() -> List[Any]:
    from tools import google_gmail

    @tool
    async def search_gmail(
        phone: str,
        query: str,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """Search Gmail messages matching the query.

        Args:
            phone: User phone for per-user OAuth.
            query: Gmail search query (e.g. "in:inbox newer_than:30d", "from:user@example.com").
            max_results: Maximum number of messages to return. Default 10.
        """
        return await google_gmail.search_messages(
            phone=phone,
            query=query,
            max_results=max_results,
        )

    @tool
    async def get_gmail_thread(
        phone: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """Get all messages in a Gmail thread.

        Args:
            phone: User phone for per-user OAuth.
            thread_id: Gmail thread ID.
        """
        return await google_gmail.get_thread(
            phone=phone,
            thread_id=thread_id,
        )

    @tool
    async def send_gmail(
        phone: str,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email via Gmail.

        Args:
            phone: User phone for per-user OAuth.
            to: Recipient email address.
            subject: Email subject.
            body: Email body (plain text).
            thread_id: Optional Gmail thread ID to reply into.
        """
        return await google_gmail.send_message(
            phone=phone,
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )

    return [search_gmail, get_gmail_thread, send_gmail]


def _build_drive_tools() -> List[Any]:
    from tools import google_drive

    @tool
    async def search_drive_files(
        phone: str,
        query: str,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Search Google Drive files by name or content.

        Args:
            phone: User phone for per-user OAuth.
            query: Free-text search query.
            max_results: Maximum number of files to return. Default 20.
        """
        return await google_drive.search_files(
            phone=phone,
            query=query,
            max_results=max_results,
        )

    @tool
    async def list_drive_folder(
        phone: str,
        folder_id: str,
    ) -> Dict[str, Any]:
        """List contents of a Google Drive folder.

        Args:
            phone: User phone for per-user OAuth.
            folder_id: Google Drive folder ID.
        """
        return await google_drive.list_folder(
            phone=phone,
            folder_id=folder_id,
        )

    @tool
    async def create_drive_folder(
        phone: str,
        name: str,
    ) -> Dict[str, Any]:
        """Create a new Google Drive folder.

        Args:
            phone: User phone for per-user OAuth.
            name: Folder name.
        """
        return await google_drive.create_folder(
            phone=phone,
            name=name,
        )

    return [search_drive_files, list_drive_folder, create_drive_folder]


def _build_web_tools() -> List[Any]:
    from tools import web_search

    @tool
    async def web_search_tool(
        query: str,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Search the web via Serper.dev.

        Args:
            query: Search query.
            max_results: Maximum number of results. Default 5.
        """
        return await web_search.search(query=query, max_results=max_results)

    return [web_search_tool]


def get_tools_for_manager(manager_id: str) -> List[Any]:
    """Public entry point: return the LangChain tools for a given manager.

    Returns an empty list if the manager is unknown or the import fails.
    """
    try:
        return _build_langchain_tools_for(manager_id)
    except Exception as exc:
        logger.exception("failed to build tools for %s: %s", manager_id, exc)
        return []
