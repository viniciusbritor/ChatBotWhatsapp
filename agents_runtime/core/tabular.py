"""Tabular payload builders for auto-image reports.

Usado por:
- ``orchestrator._detect_tabular_payload`` (extraindo listas de tool_results)
- ``pipelines._prefetch.prefetch_for_agent`` (a partir de dados estruturados
  retornados por ``_prefetch_calendar/_prefetch_email/_prefetch_drive*``)

Mantemos a tabela ``_MIME_LABELS`` no orchestrator para compat com tool
results que usam os rotulos longos (Word/Planilha/Apresentacao) e a
label curta do drive prefetch (Docs/Sheets/Slides).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Limite de linhas por tipo (mesmo do _detect_tabular_payload original).
MAX_ROWS_LISTS = 20
MAX_ROWS_CHUNKS = 5


_MIME_LABELS_DRIVE = {
    "application/vnd.google-apps.folder": "Pasta",
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Planilha",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "Apresentação",
    "image/png": "PNG",
    "image/jpeg": "Imagem",
}


def _label_mime(mime: str) -> str:
    if not mime:
        return "Arquivo"
    if mime in _MIME_LABELS_DRIVE:
        return _MIME_LABELS_DRIVE[mime]
    ext = mime.split(".")[-1].upper()
    return ext if ext else "Arquivo"


def events_to_rows(events: List[Dict[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for ev in events[:MAX_ROWS_LISTS]:
        start = ev.get("start") or {}
        end = ev.get("end") or {}
        rows.append([
            str(ev.get("summary") or "(sem titulo)")[:48],
            str(start.get("dateTime") or start.get("date") or "")[:16],
            str(end.get("dateTime") or end.get("date") or "")[:16],
        ])
    return rows


def messages_to_rows(messages: List[Dict[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for m in messages[:MAX_ROWS_LISTS]:
        rows.append([
            str(m.get("subject") or m.get("snippet") or "(sem assunto)")[:64],
            str(m.get("from") or m.get("sender") or "")[:48],
            str(m.get("date") or m.get("internal_date") or "")[:10],
        ])
    return rows


def files_to_rows(files: List[Dict[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for f in files[:MAX_ROWS_LISTS]:
        mime = f.get("mime_type") or f.get("mimeType") or ""
        rows.append([
            str(f.get("name", ""))[:64],
            _label_mime(mime),
            str(f.get("modified") or f.get("modifiedTime") or "")[:10],
        ])
    return rows


def build_calendar_payload(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not events:
        return None
    return {
        "title": "Eventos da agenda",
        "headers": ["Evento", "Início", "Fim"],
        "rows": events_to_rows(events),
        "emoji_header": "📅",
    }


def build_email_payload(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not messages:
        return None
    return {
        "title": "Emails encontrados",
        "headers": ["Assunto", "De", "Data"],
        "rows": messages_to_rows(messages),
        "emoji_header": "📧",
    }


def build_drive_payload(files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not files:
        return None
    return {
        "title": "Arquivos da pasta",
        "headers": ["Nome", "Tipo", "Modificado"],
        "rows": files_to_rows(files),
        "emoji_header": "📁",
    }


def build_from_agent_type(agent_type: str, raw_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Constroi payload tabular a partir do tipo de agente e lista estruturada."""
    if agent_type == "calendar":
        return build_calendar_payload(raw_items)
    if agent_type == "email":
        return build_email_payload(raw_items)
    if agent_type == "drive":
        return build_drive_payload(raw_items)
    return None
