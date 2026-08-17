"""LangChain `@tool` wrappers for DeepAgent Manager specialists.

Exposes tools for:
- manager-calendar: list_calendar_events, create_calendar_event, calendar_freebusy
- manager-email: search_gmail, get_gmail_thread, send_gmail
- manager-drive: search_drive_files, list_drive_folder, create_drive_folder,
  read_drive_file_content, deep_search_drive_files
- manager-group-rag: index_group_document, search_group_knowledge
- manager-web: web_search_tool

Auth is handled at runtime via per-user OAuth tokens (Fase D).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _build_langchain_tools_for(manager_id: str) -> List[Any]:
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
    if manager_id == "manager-linkedin":
        return _build_linkedin_tools()
    if manager_id == "manager-jennifier":
        # Agente conversacional geral: nao tem tools. Retorna lista vazia
        # explicitamente para evitar o warning 'unknown manager_id'.
        # FIX (15/08/2026): bug pre-existente causava loop de fallback porque
        # _build_agent rejeitava manager-jennifier por falta de entry aqui.
        return []
    logger.warning("unknown manager_id=%s", manager_id)
    return []


def _build_linkedin_tools() -> List[Any]:
    """LangChain tools para LinkedIn via Composio (manager-linkedin).

    Tools wrapped:
    - linkedin_my_profile: LINKEDIN_GET_MY_INFO
    - linkedin_create_post: LINKEDIN_CREATE_LINKED_IN_POST
    - linkedin_read_post: LINKEDIN_GET_POST_CONTENT
    - linkedin_create_article: LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE
    """
    from tools import linkedin_composio

    @tool
    async def linkedin_my_profile(phone: str) -> Dict[str, Any]:
        """Busca o perfil LinkedIn do usuario autenticado.

        Args:
            phone: Telefone do usuario (per-user Composio user_id).

        Returns:
            Dict com firstName, lastName, headline, id, vanityName, profilePicture.
        """
        return await linkedin_composio.my_profile(phone=phone)

    @tool
    async def linkedin_create_post(
        text: str,
        visibility: str,
        phone: str,
    ) -> Dict[str, Any]:
        """Cria um post no LinkedIn do usuario.

        Args:
            text: Conteudo do post (max 3000 caracteres).
            visibility: PUBLIC | CONNECTIONS | LOGGED_IN_MEMBERS.
            phone: Telefone do usuario para identificar o autor.
        """
        return await linkedin_composio.create_post(
            text=text, visibility=visibility, phone=phone,
        )

    @tool
    async def linkedin_read_post(post_id: str, phone: str) -> Dict[str, Any]:
        """Le o conteudo de um post do LinkedIn por ID.

        Args:
            post_id: ID do post no LinkedIn (urn:li:activity:xxx ou similar).
            phone: Telefone do usuario.
        """
        return await linkedin_composio.read_post(post_id=post_id, phone=phone)

    @tool
    async def linkedin_create_article(
        text: str,
        title: str,
        phone: str,
        url: str = "",
    ) -> Dict[str, Any]:
        """Cria um artigo ou compartilha uma URL no LinkedIn.

        Args:
            text: Conteudo do artigo (max 3000 chars).
            title: Titulo do artigo (max 200 chars).
            phone: Telefone do usuario.
            url: URL externa para compartilhar (opcional).
        """
        return await linkedin_composio.create_article(
            text=text, title=title, url=url, phone=phone,
        )

    return [linkedin_my_profile, linkedin_create_post, linkedin_read_post, linkedin_create_article]


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

    async def _apply_default_filter(
        result: Dict[str, Any],
        phone: str,
        query: str,
    ) -> Dict[str, Any]:
        """FIX Bug #1B (15/08/2026): quando o usuario ja marcou um arquivo
        como padrao via memory.save_fact(key=curriculo_padrao), prioriza
        esse arquivo no topo do resultado. Nao esconde os outros - apenas
        reordena para que o LLM nao precise adivinhar entre copias.
        """
        if not isinstance(result, dict) or not result.get("files"):
            return result
        query_norm = str(query or "").strip().lower()
        fact_keys = ("curriculo_padrao",)
        if not any(kw in query_norm for kw in ("curriculo", "currículo", "resum", "cv ")):
            return result
        try:
            from tools.memory import get_fact_by_key

            default_filename = None
            for key in fact_keys:
                default_filename = await get_fact_by_key(key, phone)
                if default_filename:
                    break
            if not default_filename:
                return result
            files = list(result.get("files") or [])
            default_norm = default_filename.strip().lower()
            prioritized = []
            others = []
            for f in files:
                fname = str(f.get("name") or "").strip().lower()
                if fname == default_norm:
                    prioritized.append(f)
                else:
                    others.append(f)
            if prioritized:
                result["files"] = prioritized + others
                result["default_file_id"] = prioritized[0].get("id", "")
                result["default_file_name"] = prioritized[0].get("name", "")
            return result
        except Exception as exc:  # noqa: BLE001
            logger.debug("apply_default_filter_skipped exc=%s", exc)
            return result

    @tool
    async def search_drive_files(
        phone: str,
        query: str,
        max_results: int = 20,
        apply_default_filter: bool = True,
    ) -> Dict[str, Any]:
        """Search Google Drive files by name or content.

        Args:
            phone: User phone for per-user OAuth.
            query: Free-text search query.
            max_results: Maximum number of files to return. Default 20.
            apply_default_filter: Quando True (default) e o usuario tem
                um arquivo padrao marcado (memory.save_fact com
                key=curriculo_padrao), prioriza esse arquivo no topo
                do resultado sem esconder os outros.
        """
        result = await google_drive.search_files(
            phone=phone,
            query=query,
            max_results=max_results,
        )
        if apply_default_filter:
            result = await _apply_default_filter(result, phone, query)
        return result

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
