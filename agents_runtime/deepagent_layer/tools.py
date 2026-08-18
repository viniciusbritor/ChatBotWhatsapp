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
    if manager_id == "manager-googledocs":
        return _build_googledocs_tools()
    if manager_id == "manager-googlesheets":
        return _build_googlesheets_tools()
    if manager_id == "manager-onedrive":
        return _build_onedrive_tools()
    if manager_id == "manager-googlemeet":
        return _build_googlemeet_tools()
    if manager_id == "manager-msteams":
        return _build_msteams_tools()
    if manager_id == "manager-youtube":
        return _build_youtube_tools()
    if manager_id == "manager-github":
        return _build_github_tools()
    if manager_id == "manager-notion":
        return _build_notion_tools()
    if manager_id == "manager-people":
        return _build_people_tools()
    if manager_id == "manager-tasks":
        return _build_tasks_tools()
    if manager_id == "manager-maps":
        return _build_maps_tools()
    if manager_id == "manager-jennifier":
        # Agente conversacional geral: nao tem tools. Retorna lista vazia
        # explicitamente para evitar o warning 'unknown manager_id'.
        # FIX (15/08/2026): bug pre-existente causava loop de fallback porque
        # _build_agent rejeitava manager-jennifier por falta de entry aqui.
        return []
    logger.warning("unknown manager_id=%s", manager_id)
    return []


def _build_googledocs_tools() -> List[Any]:
    """LangChain tools para Google Docs via Composio (manager-googledocs).

    Tools wrapped:
    - googledocs_create_document: GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN
    - googledocs_read_document: GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT
    - googledocs_search_documents: GOOGLEDOCS_SEARCH_DOCUMENTS
    - googledocs_export_pdf: GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF
    """
    from tools import googledocs_composio

    @tool
    async def googledocs_create_document(
        title: str,
        markdown_text: str = "",
        phone: str = "",
    ) -> Dict[str, Any]:
        """Cria um documento Google Docs a partir de markdown.

        Args:
            title: Titulo do documento (max 200 chars).
            markdown_text: Conteudo em markdown (max 50000 chars).
            phone: Telefone do usuario.
        """
        return await googledocs_composio.create_document(
            title=title, markdown_text=markdown_text, phone=phone,
        )

    @tool
    async def googledocs_read_document(doc_id: str, phone: str) -> Dict[str, Any]:
        """Le o conteudo plain text de um documento Google Docs.

        Args:
            doc_id: ID do documento Google Docs.
            phone: Telefone do usuario.
        """
        return await googledocs_composio.read_document(doc_id=doc_id, phone=phone)

    @tool
    async def googledocs_search_documents(
        query: str = "",
        max_results: int = 10,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Busca documentos Google Docs por texto.

        Args:
            query: Texto de busca (max 500 chars).
            max_results: Numero maximo de resultados (default 10).
            phone: Telefone do usuario.
        """
        return await googledocs_composio.search_documents(
            query=query, max_results=max_results, phone=phone,
        )

    @tool
    async def googledocs_export_pdf(doc_id: str, phone: str) -> Dict[str, Any]:
        """Exporta um documento Google Docs como PDF.

        Args:
            doc_id: ID do documento Google Docs.
            phone: Telefone do usuario.
        """
        return await googledocs_composio.export_pdf(doc_id=doc_id, phone=phone)

    return [
        googledocs_create_document,
        googledocs_read_document,
        googledocs_search_documents,
        googledocs_export_pdf,
    ]


def _build_googlesheets_tools() -> List[Any]:
    """LangChain tools para Google Sheets via Composio (manager-googlesheets).

    Tools wrapped:
    - googlesheets_read_cells: GOOGLESHEETS_READ_GOOGLE_SHEET
    - googlesheets_write_cells: GOOGLESHEETS_WRITE_TO_GOOGLE_SHEET
    - googlesheets_create_spreadsheet: GOOGLESHEETS_CREATE_GOOGLE_SHEET
    """
    from tools import googlesheets_composio

    @tool
    async def googlesheets_read_cells(
        spreadsheet_id: str,
        range_: str = "A1:Z100",
        phone: str = "",
    ) -> Dict[str, Any]:
        """Le celulas de uma planilha Google Sheets.

        Args:
            spreadsheet_id: ID da planilha (encontrado na URL).
            range_: Range A1 notation (default 'A1:Z100').
            phone: Telefone do usuario.
        """
        return await googlesheets_composio.read_cells(
            spreadsheet_id=spreadsheet_id, range_=range_, phone=phone,
        )

    @tool
    async def googlesheets_write_cells(
        spreadsheet_id: str,
        range_: str,
        values: List[List[str]],
        phone: str = "",
    ) -> Dict[str, Any]:
        """Escreve valores em celulas de uma planilha Google Sheets.

        Args:
            spreadsheet_id: ID da planilha.
            range_: Range A1 notation (ex: 'A1:C10').
            values: Matriz de valores (linhas x colunas).
            phone: Telefone do usuario.
        """
        return await googlesheets_composio.write_cells(
            spreadsheet_id=spreadsheet_id, range_=range_, values=values, phone=phone,
        )

    @tool
    async def googlesheets_create_spreadsheet(
        title: str,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Cria uma nova planilha Google Sheets.

        Args:
            title: Titulo da planilha.
            phone: Telefone do usuario.
        """
        return await googlesheets_composio.create_spreadsheet(
            title=title, phone=phone,
        )

    return [
        googlesheets_read_cells,
        googlesheets_write_cells,
        googlesheets_create_spreadsheet,
    ]


def _build_onedrive_tools() -> List[Any]:
    """LangChain tools para OneDrive via Composio (manager-onedrive).

    Tools wrapped:
    - onedrive_list_items: ONE_DRIVE_LIST_ITEMS
    - onedrive_list_folder_children: ONE_DRIVE_LIST_FOLDER_CHILDREN
    - onedrive_list_drives: ONE_DRIVE_LIST_DRIVES
    """
    from tools import onedrive_composio

    @tool
    async def onedrive_list_items(top: int = 50, phone: str = "") -> Dict[str, Any]:
        """Lista itens do OneDrive (arquivos e pastas).

        Args:
            top: Numero maximo de itens (default 50).
            phone: Telefone do usuario.
        """
        return await onedrive_composio.list_items(top=top, phone=phone)

    @tool
    async def onedrive_list_folder_children(
        folder_path: str = "/",
        top: int = 200,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Lista arquivos dentro de uma pasta especifica.

        Args:
            folder_path: Caminho da pasta (default raiz '/').
            top: Numero maximo de itens (default 200).
            phone: Telefone do usuario.
        """
        return await onedrive_composio.list_folder_children(
            folder_path=folder_path, top=top, phone=phone,
        )

    @tool
    async def onedrive_list_drives(phone: str = "") -> Dict[str, Any]:
        """Lista os drives disponiveis para o usuario.

        Args:
            phone: Telefone do usuario.
        """
        return await onedrive_composio.list_drives(phone=phone)

    return [
        onedrive_list_items,
        onedrive_list_folder_children,
        onedrive_list_drives,
    ]


def _build_googlemeet_tools() -> List[Any]:
    """LangChain tools para Google Meet via Composio (manager-googlemeet).

    Google Meet eh acessado via Google Calendar API (cada evento do Calendar
    tem um link Meet automatico). Tools wrapped:
    - googlemeet_create_meeting: GOOGLECALENDAR_CREATE_EVENT
    - googlemeet_list_meetings: GOOGLECALENDAR_LIST_EVENTS
    - googlemeet_get_meeting_link: GOOGLECALENDAR_GET_EVENT
    """
    from tools import googlemeet_composio

    @tool
    async def googlemeet_create_meeting(
        summary: str,
        start_time: str,
        end_time: str,
        attendees: str = "",
        phone: str = "",
    ) -> Dict[str, Any]:
        """Cria uma reuniao no Google Meet (via Calendar).

        Args:
            summary: Titulo da reuniao.
            start_time: ISO 8601 (ex: '2026-08-20T15:00:00-03:00').
            end_time: ISO 8601.
            attendees: Emails separados por virgula (opcional).
            phone: Telefone do usuario.
        """
        return await googlemeet_composio.create_meeting(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            phone=phone,
        )

    @tool
    async def googlemeet_list_meetings(
        time_min: str,
        time_max: str,
        max_results: int = 50,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Lista reunioes (eventos Calendar) com link Meet.

        Args:
            time_min: ISO 8601 datetime inicio.
            time_max: ISO 8601 datetime fim.
            max_results: Numero maximo de resultados (default 50).
            phone: Telefone do usuario.
        """
        return await googlemeet_composio.list_meetings(
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            phone=phone,
        )

    @tool
    async def googlemeet_get_meeting_link(event_id: str, phone: str = "") -> Dict[str, Any]:
        """Retorna link de Meet de um evento especifico.

        Args:
            event_id: ID do evento no Google Calendar.
            phone: Telefone do usuario.
        """
        return await googlemeet_composio.get_meeting_link(
            event_id=event_id, phone=phone,
        )

    return [
        googlemeet_create_meeting,
        googlemeet_list_meetings,
        googlemeet_get_meeting_link,
    ]


def _build_msteams_tools() -> List[Any]:
    """LangChain tools para Microsoft Teams via Composio (manager-msteams).

    Tools wrapped:
    - msteams_send_message: MS_TEAMS_SEND_MESSAGE
    - msteams_list_channels: MS_TEAMS_LIST_CHANNELS
    - msteams_list_messages: MS_TEAMS_LIST_MESSAGES
    """
    from tools import microsoft_teams_composio

    @tool
    async def msteams_send_message(
        channel_id: str,
        message: str,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Envia uma mensagem para um canal do Microsoft Teams.

        Args:
            channel_id: ID do canal de destino.
            message: Conteudo da mensagem.
            phone: Telefone do usuario.
        """
        return await microsoft_teams_composio.send_message(
            channel_id=channel_id, message=message, phone=phone,
        )

    @tool
    async def msteams_list_channels(phone: str = "") -> Dict[str, Any]:
        """Lista canais do Microsoft Teams do usuario.

        Args:
            phone: Telefone do usuario.
        """
        return await microsoft_teams_composio.list_channels(phone=phone)

    @tool
    async def msteams_list_messages(
        channel_id: str,
        top: int = 20,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Lista mensagens de um canal do Microsoft Teams.

        Args:
            channel_id: ID do canal.
            top: Numero maximo de mensagens (default 20).
            phone: Telefone do usuario.
        """
        return await microsoft_teams_composio.list_messages(
            channel_id=channel_id, top=top, phone=phone,
        )

    return [
        msteams_send_message,
        msteams_list_channels,
        msteams_list_messages,
    ]


def _build_youtube_tools() -> List[Any]:
    """LangChain tools para YouTube via Composio (manager-youtube)."""
    from tools import youtube_composio

    @tool
    async def youtube_search_videos(query: str, max_results: int = 5, phone: str = "") -> Dict[str, Any]:
        """Busca videos no YouTube.

        Args:
            query: Termo de busca.
            max_results: Numero maximo de resultados (default 5).
            phone: Telefone do usuario.
        """
        return await youtube_composio.search_videos(query=query, max_results=max_results, phone=phone)

    @tool
    async def youtube_get_video_details(video_ids: list, phone: str = "") -> Dict[str, Any]:
        """Retorna detalhes de videos do YouTube por IDs.

        Args:
            video_ids: Lista de IDs de videos.
            phone: Telefone do usuario.
        """
        return await youtube_composio.get_video_details(video_ids=video_ids, phone=phone)

    return [
        youtube_search_videos,
        youtube_get_video_details,
    ]


def _build_github_tools() -> List[Any]:
    """LangChain tools para GitHub via Composio (manager-github)."""
    from tools import github_composio

    @tool
    async def github_list_repos(
        type_: str = "all",
        sort: str = "full_name",
        direction: str = "",
        page: int = 1,
        per_page: int = 30,
        phone: str = "",
    ) -> Dict[str, Any]:
        """Lista repositorios do usuario no GitHub.

        Args:
            type_: 'all' | 'owner' | 'public' | 'private' | 'member'.
            sort: 'created' | 'updated' | 'pushed' | 'full_name'.
            direction: 'asc' | 'desc'.
            page: pagina (default 1).
            per_page: itens por pagina (default 30).
            phone: Telefone do usuario.
        """
        return await github_composio.list_repos(
            type_=type_, sort=sort, direction=direction,
            page=page, per_page=per_page, phone=phone,
        )

    @tool
    async def github_my_profile(phone: str = "") -> Dict[str, Any]:
        """Obtem o perfil autenticado do usuario no GitHub.

        Args:
            phone: Telefone do usuario.
        """
        return await github_composio.my_profile(phone=phone)

    return [
        github_list_repos,
        github_my_profile,
    ]


def _build_notion_tools() -> List[Any]:
    """LangChain tools para Notion via Composio (manager-notion)."""
    from tools import notion_composio

    @tool
    async def notion_search_pages(query: str = "", page_size: int = 25, phone: str = "") -> Dict[str, Any]:
        """Busca paginas no Notion por termo.

        Args:
            query: Termo de busca.
            page_size: Numero maximo de resultados (default 25).
            phone: Telefone do usuario.
        """
        return await notion_composio.search_pages(query=query, page_size=page_size, phone=phone)

    @tool
    async def notion_list_all(query: str = "", page_size: int = 100, phone: str = "") -> Dict[str, Any]:
        """Lista todas as paginas do Notion do usuario.

        Args:
            query: Filtro opcional.
            page_size: Numero maximo de resultados (default 100).
            phone: Telefone do usuario.
        """
        return await notion_composio.list_all(query=query, page_size=page_size, phone=phone)

    @tool
    async def notion_retrieve_page(page_id: str, phone: str = "") -> Dict[str, Any]:
        """Obtem o conteudo de uma pagina do Notion.

        Args:
            page_id: ID da pagina.
            phone: Telefone do usuario.
        """
        return await notion_composio.retrieve_page(page_id=page_id, phone=phone)

    return [
        notion_search_pages,
        notion_list_all,
        notion_retrieve_page,
    ]


def _build_people_tools() -> List[Any]:
    """LangChain tools para Google Contacts (manager-people, OAuth per-user)."""
    from tools import google_people

    @tool
    async def people_search_contacts(query: str, page_size: int = 10, phone: str = "") -> Dict[str, Any]:
        """Busca contatos do usuario no Google Contacts.

        Args:
            query: Termo de busca (nome, email, telefone).
            page_size: Numero maximo de resultados (default 10).
            phone: Telefone do usuario.
        """
        return await google_people.search_contacts(query=query, page_size=page_size, phone=phone)

    @tool
    async def people_get_profile(phone: str = "") -> Dict[str, Any]:
        """Obtem o perfil do usuario no Google Contacts.

        Args:
            phone: Telefone do usuario.
        """
        return await google_people.get_profile(phone=phone)

    return [
        people_search_contacts,
        people_get_profile,
    ]


def _build_tasks_tools() -> List[Any]:
    """LangChain tools para Google Tasks (manager-tasks, OAuth per-user)."""
    from tools import google_tasks

    @tool
    async def tasks_list_tasks(phone: str = "", tasklist_id: str = "@default", max_results: int = 20) -> Dict[str, Any]:
        """Lista tarefas do usuario no Google Tasks.

        Args:
            phone: Telefone do usuario.
            tasklist_id: ID da lista de tarefas (default @default).
            max_results: Numero maximo de resultados (default 20).
        """
        return await google_tasks.list_tasks(
            phone=phone, tasklist_id=tasklist_id, max_results=max_results,
        )

    @tool
    async def tasks_create_task(
        title: str,
        notes: str = "",
        due: str = "",
        tasklist_id: str = "@default",
        phone: str = "",
    ) -> Dict[str, Any]:
        """Cria uma tarefa no Google Tasks.

        Args:
            title: Titulo da tarefa.
            notes: Notas opcionais.
            due: Data de vencimento (RFC3339, opcional).
            tasklist_id: ID da lista de tarefas (default @default).
            phone: Telefone do usuario.
        """
        return await google_tasks.create_task(
            title=title, notes=notes, due=due, tasklist_id=tasklist_id, phone=phone,
        )

    @tool
    async def tasks_update_task(
        task_id: str,
        completed: bool = False,
        title: str = None,
        tasklist_id: str = "@default",
        phone: str = "",
    ) -> Dict[str, Any]:
        """Atualiza uma tarefa no Google Tasks (concluir/renomear).

        Args:
            task_id: ID da tarefa.
            completed: True para marcar como concluida.
            title: Novo titulo (opcional).
            tasklist_id: ID da lista de tarefas (default @default).
            phone: Telefone do usuario.
        """
        return await google_tasks.update_task(
            task_id=task_id, completed=completed, title=title,
            tasklist_id=tasklist_id, phone=phone,
        )

    return [
        tasks_list_tasks,
        tasks_create_task,
        tasks_update_task,
    ]


def _build_maps_tools() -> List[Any]:
    """LangChain tools para Google Maps (manager-maps, API key)."""
    from tools import locomotion

    @tool
    async def maps_calc_route(origem: str, destino: str) -> Dict[str, Any]:
        """Calcula rota entre dois enderecos no Google Maps.

        Args:
            origem: Endereco ou coordenada de origem.
            destino: Endereco ou coordenada de destino.
        """
        return await locomotion.calc_route(origem=origem, destino=destino)

    @tool
    async def maps_geocode(endereco: str) -> Dict[str, Any]:
        """Geocodifica um endereco (endereco -> coordenadas).

        Args:
            endereco: Endereco a geocodificar.
        """
        return await locomotion.geocode(endereco=endereco)

    @tool
    async def maps_search_places(local: str, tipo: str = "restaurant") -> list:
        """Busca lugares proximos no Google Maps.

        Args:
            local: Localizacao de referencia.
            tipo: Tipo de lugar (ex: restaurant, cafe, hotel).
        """
        return await locomotion.search_places(local=local, tipo=tipo)

    @tool
    async def maps_find_place(query: str, localizacao: str = "") -> list:
        """Encontra um lugar no Google Maps.

        Args:
            query: Termo de busca do lugar.
            localizacao: Localizacao de referencia (opcional).
        """
        return await locomotion.find_place(query=query, localizacao=localizacao)

    return [
        maps_calc_route,
        maps_geocode,
        maps_search_places,
        maps_find_place,
    ]


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
