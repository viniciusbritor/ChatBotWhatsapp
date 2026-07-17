"""Tool Registry - central map of tool_id -> implementation function.

Each tool has:
- id: unique identifier
- function: callable
- description: for LLM schema
- parameters_schema: OpenAI-compatible JSON schema
"""
import logging
from typing import Dict, Any, Callable, Awaitable

from tools import google_calendar, google_drive, google_gmail, web_search, nickname
from tools import locomotion, youtube

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[Dict[str, Any]]]

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "calendar.list_events": {
        "function": google_calendar.list_events,
        "implementation": "google_calendar",
        "description": "Lista eventos do Google Calendar entre time_min e time_max. IMPORTANTE: sempre passe o telefone (phone) do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "ISO 8601 datetime inicio"},
                "time_max": {"type": "string", "description": "ISO 8601 datetime fim"},
                "calendar_id": {"type": "string", "description": "ID do calendario (default: primary)"},
                "max_results": {"type": "integer", "description": "Maximo de eventos (default: 50)"},
                "phone": {"type": "string", "description": "Telefone do usuario para usar o token OAuth dele"},
            },
            "required": ["time_min", "time_max"],
        },
    },
    "calendar.create_event": {
        "function": google_calendar.create_event,
        "implementation": "google_calendar",
        "description": "Cria um novo evento no Google Calendar. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO 8601 datetime inicio"},
                "end": {"type": "string", "description": "ISO 8601 datetime fim"},
                "summary": {"type": "string", "description": "Titulo do evento"},
                "description": {"type": "string", "description": "Descricao opcional"},
                "attendees": {"type": "array", "items": {"type": "string"}, "description": "Lista de emails"},
                "location": {"type": "string", "description": "Local do evento"},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["start", "end", "summary"],
        },
    },
    "calendar.update_event": {
        "function": google_calendar.update_event,
        "implementation": "google_calendar",
        "description": "Atualiza um evento existente.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["event_id"],
        },
    },
    "calendar.delete_event": {
        "function": google_calendar.delete_event,
        "implementation": "google_calendar",
        "description": "Deleta um evento do calendar.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["event_id"],
        },
    },
    "calendar.freebusy": {
        "function": google_calendar.freebusy,
        "implementation": "google_calendar",
        "description": "Consulta free/busy de calendarios.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "calendars": {"type": "array", "items": {"type": "string"}},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["time_min", "time_max"],
        },
    },
    "drive.search_files": {
        "function": google_drive.search_files,
        "implementation": "google_drive",
        "description": "Busca arquivos no Google Drive por nome. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "folder_id": {"type": "string"},
                "mime_type": {"type": "string"},
                "max_results": {"type": "integer"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["query"],
        },
    },
    "drive.upload_file": {
        "function": google_drive.upload_file,
        "implementation": "google_drive",
        "description": "Faz upload de arquivo para uma pasta do Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string"},
                "filename": {"type": "string"},
                "content": {"type": "string"},
                "mime_type": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["folder_id", "filename", "content"],
        },
    },
    "drive.list_folder": {
        "function": google_drive.list_folder,
        "implementation": "google_drive",
        "description": "Lista conteudo de uma pasta do Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string"},
                "max_results": {"type": "integer"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
        },
    },
    "drive.create_folder": {
        "function": google_drive.create_folder,
        "implementation": "google_drive",
        "description": "Cria uma pasta no Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["name"],
        },
    },
    "gmail.search_messages": {
        "function": google_gmail.search_messages,
        "implementation": "google_gmail",
        "description": "Busca mensagens no Gmail por query. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "label_ids": {"type": "array", "items": {"type": "string"}},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["query"],
        },
    },
    "gmail.get_thread": {
        "function": google_gmail.get_thread,
        "implementation": "google_gmail",
        "description": "Retorna todas as mensagens de uma thread.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["thread_id"],
        },
    },
    "gmail.send_message": {
        "function": google_gmail.send_message,
        "implementation": "google_gmail",
        "description": "Envia um email.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "thread_id": {"type": "string"},
                "html": {"type": "boolean"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "web.search": {
        "function": web_search.serper_search,
        "implementation": "web_search",
        "description": "Busca na web via Serper.dev (com cache 24h).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num": {"type": "integer", "description": "Numero de resultados (default: 10)"},
            },
            "required": ["query"],
        },
    },
    "web.fetch_url": {
        "function": web_search.fetch_url,
        "implementation": "web_search",
        "description": "Faz fetch do conteudo de uma URL.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["url"],
        },
    },
    "nickname.lookup": {
        "function": nickname.lookup,
        "implementation": "nickname",
        "description": "Busca apelidos conhecidos para um nome.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    "nickname.set_consent": {
        "function": nickname.set_consent,
        "implementation": "nickname",
        "description": "Registra consentimento do usuario sobre um apelido.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "name": {"type": "string"},
                "nickname": {"type": "string"},
                "accepted": {"type": "boolean"},
            },
            "required": ["phone", "name", "nickname"],
        },
    },
    "nickname.get_preferred_name": {
        "function": nickname.get_preferred_name,
        "implementation": "nickname",
        "description": "Retorna o nome preferido (apelido aceito) do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    "drive.find_omnichannel_atas_folder": {
        "function": google_drive.find_omnichannel_atas_folder,
        "implementation": "google_drive",
        "description": "Encontra a pasta Omnichannel/Atas/ no Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
        },
    },
    "locomotion.calc_route": {
        "function": locomotion.calc_route,
        "implementation": "locomotion",
        "description": "Calcula rota entre dois enderecos. Retorna distancia, duracao, preco estimado Uber e 99.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Endereco de partida"},
                "destino": {"type": "string", "description": "Endereco de chegada"},
            },
            "required": ["origem", "destino"],
        },
    },
    "locomotion.geocode": {
        "function": locomotion.geocode,
        "implementation": "locomotion",
        "description": "Converte endereco em coordenadas e endereco formatado.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "endereco": {"type": "string", "description": "Endereco para geocodificar"},
            },
            "required": ["endereco"],
        },
    },
    "locomotion.search_places": {
        "function": locomotion.search_places,
        "implementation": "locomotion",
        "description": "Busca lugares proximos (restaurantes, farmacias, etc).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "local": {"type": "string", "description": "Localizacao de referencia"},
                "tipo": {"type": "string", "description": "Tipo: restaurant, pharmacy, gas_station"},
            },
            "required": ["local"],
        },
    },
    "youtube.search_videos": {
        "function": youtube.search_videos,
        "implementation": "youtube",
        "description": "Busca videos no YouTube e retorna titulo, canal e link.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca"},
                "max_results": {"type": "integer", "description": "Maximo de resultados (default 3)"},
            },
            "required": ["query"],
        },
    },
    "rag.search_knowledge": {
        "function": lambda **kwargs: __import__("asyncio").run(__import__("core.rag").search_knowledge(kwargs.get("query", ""), kwargs.get("limit", 5))),
        "implementation": "rag",
        "description": "Busca semantica na base de conhecimento publica (leis, editais, livros).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca semantica"},
                "limit": {"type": "integer", "description": "Maximo de resultados"},
            },
            "required": ["query"],
        },
    },
    "rag.search_legal_knowledge": {
        "function": lambda **kwargs: __import__("asyncio").run(__import__("core.rag").search_legal_knowledge(kwargs.get("phone", ""), kwargs.get("query", ""), kwargs.get("k", 5))),
        "implementation": "rag",
        "description": "Busca semantica em legislacao (leis penais, editais) no banco privado do agente.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "query": {"type": "string", "description": "Termo de busca semantica"},
                "k": {"type": "integer", "description": "Maximo de resultados"},
            },
            "required": ["phone", "query"],
        },
    },
}


def get_tool(tool_id: str):
    """Get tool function by id."""
    entry = TOOL_REGISTRY.get(tool_id)
    if entry:
        return entry["function"]
    return None


def get_tool_schema(tool_id: str):
    """Get tool schema for LLM."""
    entry = TOOL_REGISTRY.get(tool_id)
    if entry:
        return {
            "name": tool_id,
            "description": entry["description"],
            "parameters": entry["parameters_schema"],
        }
    return None


def list_tool_ids() -> list:
    """List all registered tool IDs."""
    return list(TOOL_REGISTRY.keys())


def get_tools_for_agent(tool_ids: list) -> list:
    """Get tool schemas for an agent."""
    return [get_tool_schema(tid) for tid in tool_ids if get_tool_schema(tid)]