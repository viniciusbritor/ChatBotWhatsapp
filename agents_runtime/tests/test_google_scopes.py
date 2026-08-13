"""Testes de core.google_scopes (fonte unica de escopos/servicos Google)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.google_scopes import (
    ALL_OAUTH_SCOPES,
    GOOGLE_SERVICES,
    service_is_connected,
)


def test_oauth_scopes_completo():
    assert len(ALL_OAUTH_SCOPES) == 8
    assert "https://www.googleapis.com/auth/contacts.readonly" in ALL_OAUTH_SCOPES
    assert "https://www.googleapis.com/auth/tasks" in ALL_OAUTH_SCOPES
    assert "https://www.googleapis.com/auth/photoslibrary.readonly" in ALL_OAUTH_SCOPES


def test_people_connected_com_contacts_readonly():
    scopes = [
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/tasks",
    ]
    assert service_is_connected("people", scopes) is True
    assert service_is_connected("tasks", scopes) is True
    assert service_is_connected("photos", scopes) is False


def test_photos_connected_com_photoslibrary():
    scopes = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
    assert service_is_connected("photos", scopes) is True


def test_todo_fragmento_de_servico_aparece_na_lista_de_scopes():
    scope_str = " ".join(ALL_OAUTH_SCOPES)
    for svc in GOOGLE_SERVICES:
        assert svc["scope"] in scope_str, (
            f"servico {svc['id']} com fragmento orfao: {svc['scope']}"
        )
