"""Fonte única de verdade dos escopos e serviços Google (desacoplado).

Antes, o status do Portal era adivinhado por substring (``svc_id in scope_str``),
o que quebrava o "Google Contacts": o escopo é ``contacts.readonly`` e não
contém a palavra "people", então ficava "Pendente" para sempre. Agora a relação
serviço -> escopo é explícita e co-localizada com a lista de consentimento.
"""
from typing import Dict, List

# Serviços exibidos no Portal (Conexões). ``scope`` é o fragmento que identifica
# o escopo concedido no token OAuth (substring do URL do escopo).
GOOGLE_SERVICES: List[Dict[str, str]] = [
    {"id": "calendar", "label": "Google Calendar", "icon": "calendar_month", "scope": "calendar"},
    {"id": "gmail", "label": "Gmail", "icon": "mail", "scope": "gmail"},
    {"id": "drive", "label": "Google Drive", "icon": "folder", "scope": "drive"},
    {"id": "tasks", "label": "Google Tasks", "icon": "checklist", "scope": "tasks"},
    {"id": "people", "label": "Google Contacts", "icon": "people", "scope": "contacts.readonly"},
    {"id": "photos", "label": "Google Photos", "icon": "photo_library", "scope": "photoslibrary.readonly"},
]

# Escopos solicitados no consentimento OAuth (lista completa, inclui sub-escopos
# de escrita que nao tem card proprio no Portal).
ALL_OAUTH_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
]


def service_is_connected(service_id: str, scopes: List[str]) -> bool:
    """True se o serviço está autorizado nos scopes concedidos."""
    scope_str = " ".join(str(s) for s in scopes)
    for svc in GOOGLE_SERVICES:
        if svc["id"] == service_id:
            return svc["scope"] in scope_str
    return False
