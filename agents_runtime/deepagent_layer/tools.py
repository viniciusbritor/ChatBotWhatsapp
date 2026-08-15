"""LangChain 1.x tool wrappers for Google Calendar, Gmail, Drive, and Web search.

Each function is wrapped with the LangChain ``@tool`` decorator (via
``langchain_adapter``) so that DeepAgents (built on LangGraph 1.x) can
call them as native tools. The underlying business logic stays in
``tools/google_*.py`` and the owner guard is preserved.

Fase M (25/07/2026): langchain 0.3 -> 1.4 + deepagents 0.6.12.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_adapter import tool

logger = logging.getLogger(__name__)


def _build_langchain_tools_for(manager_id: str) -> List[Any]:
    """Build the LangChain tool list for a given manager.

    Returns the list of wrapped tools. Each tool is a
    ``langchain_core.tools.BaseTool`` instance that can be passed directly
    to ``create_deep_agent``.

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
    if manager_id == "manager-group-rag":
        return _build_group_rag_tools()
    if manager_id == "manager-web":
        return _build_web_tools()
    logger.warning("unknown manager_id=%s", manager_id)
    return []


def _fire_ack(tool_name: str, phone: str) -> None:
    """Dispara mensagem instantânea de busca no WhatsApp antes de executar a API."""
    try:
        import asyncio
        from pipelines._ack import send_instant_tool_ack
        from core.runtime_context import get_instance
        instance = get_instance() or "Jennifer"
        asyncio.create_task(send_instant_tool_ack(tool_name=tool_name, phone=phone, instance=instance))
    except Exception:
        pass


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
        _fire_ack("calendar", phone)
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
        _fire_ack("create_calendar_event", phone)
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
        _fire_ack("calendar_freebusy", phone)
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
        _fire_ack("email", phone)
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
        _fire_ack("get_message", phone)
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
        _fire_ack("send_email", phone)
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
        _fire_ack("drive", phone)
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
        _fire_ack("drive", phone)
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
        _fire_ack("drive", phone)
        return await google_drive.create_folder(
            phone=phone,
            name=name,
        )

    @tool
    async def read_drive_file_content(
        phone: str,
        file_id: str,
    ) -> Dict[str, Any]:
        """Download and extract the text content of a Google Drive file.

        Use this AFTER search_drive_files/list_drive_folder returns a file_id
        and the user wants to read the file contents (e.g. "leia a ata",
        "o que tem no PDF", "resuma o documento").

        Supports:
        - PDF (application/pdf)
        - Word .docx (Office Open XML)
        - Excel .xlsx (formatted as WhatsApp-friendly ASCII table)
        - Plain text / CSV
        - Google Docs (exported to text/plain)
        - Google Sheets (exported to text/csv)
        - Google Slides (exported to text/plain)

        Args:
            phone: User phone for per-user OAuth.
            file_id: Google Drive file ID (from search_drive_files result).

        Returns:
            Dict with file_id, file_name, mime_type, content (extracted text),
            truncated (bool), parser (which parser was used).
        """
        _fire_ack("read_file_content", phone)
        return await google_drive.read_file_content(
            phone=phone,
            file_id=file_id,
        )

    @tool
    async def deep_search_drive_files(
        phone: str,
        query: str,
        parent_folder_id: str = "root",
        max_depth: int = 3,
        max_results: int = 50,
        include_shared_drives: bool = True,
    ) -> Dict[str, Any]:
        """Recursive deep search across ALL Google Drive folders and shared drives.

        Use this as the FIRST tool when the user asks to find something
        without specifying the exact folder. It scans recursively through
        folders and subfolders, matching both file AND folder names.

        Use search_drive_files when the user already specifies a known folder.
        Use list_drive_folder when they want to see what's in a specific folder.

        Examples:
        - "ache a ata da reuniao" -> deep_search_drive_files(query="ata")
        - "procure o relatorio de custos" -> deep_search_drive_files(query="relatorio custos")
        - "busque a apresentacao no omnichannel" -> deep_search_drive_files(query="apresentacao")

        Args:
            phone: User phone for per-user OAuth.
            query: Search term (matched against file and folder names).
            parent_folder_id: Starting folder ID, or "root" for everything.
            max_depth: How deep to recurse (1=root only, 2=root+subfolders, 3=deep).
            max_results: Max total files to return.
            include_shared_drives: Search shared drives too.

        Returns:
            Dict with files, count, scanned_folders, max_depth_reached.
        """
        _fire_ack("drive", phone)
        return await google_drive.deep_search_drive(
            phone=phone,
            query=query,
            parent_folder_id=parent_folder_id,
            max_depth=max_depth,
            max_results=max_results,
            include_shared_drives=include_shared_drives,
        )

    return [search_drive_files, list_drive_folder, create_drive_folder, read_drive_file_content, deep_search_drive_files]


def _build_group_rag_tools() -> List[Any]:
    from tools import group

    @tool
    async def index_group_document(
        phone: str,
        group_jid: str,
        text: str,
        visibility: str,
        source_name: str = "",
        force_overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Index a document into group-level or public RAG.

        Use AFTER reading a file (drive.read_file_content) and asking the user
        whether it should be group-only or public.

        Chunks at 1200 chars x 15% overlap. Embeds via OpenAI text-embedding-3-small.
        Auto-classifies theme: ata_reuniao, dados_financeiros, apresentacao,
        contrato, documentacao. If returns {"needs_overwrite": true}, ask
        user confirmation and call again with force_overwrite=True.

        Args:
            phone: User phone.
            group_jid: WhatsApp group JID.
            text: Document text content.
            visibility: "group" or "public".
            source_name: Original file name.
            force_overwrite: Set True if user confirmed overwriting existing doc.
        """
        _fire_ack("rag", phone)
        return await group.index_group_document(
            phone=phone, group_jid=group_jid, text=text,
            visibility=visibility, source_name=source_name,
            force_overwrite=force_overwrite,
        )

    @tool
    async def search_group_knowledge(
        phone: str,
        group_jid: str,
        query: str,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Search group and public RAG knowledge base.

        Use when someone asks "what was decided about X?" or
        "do we have any document about Y?". Returns top-N semantically
        similar chunks filtered by group membership (or visibility=public).

        Args:
            phone: User phone (used to verify group membership).
            group_jid: WhatsApp group JID.
            query: Search text.
            limit: Max results (default 5).
        """
        _fire_ack("rag", phone)
        return await group.search_group_knowledge(
            group_jid=group_jid, query=query, limit=limit, phone=phone,
        )

    return [index_group_document, search_group_knowledge]


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
        _fire_ack("web", "")
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
