"""Tests for main.py /chat endpoint - F4d: document returns info, doesn't process."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set SA token BEFORE importing main so the auth middleware accepts it
os.environ["AGENTS_RUNTIME_SA_TOKEN_SECRET"] = "test-sa-token"
os.environ["GCP_PROJECT"] = "test"

from main import app  # noqa: E402


SA_TOKEN = "test-sa-token"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {SA_TOKEN}"}


def _document_payload():
    return {
        "instance": "jennifer",
        "phone": "5511966830020",
        "text": "",
        "sender_name": "Vini",
        "extra": {
            "has_document": True,
            "doc_mimetype": "application/pdf",
            "doc_file_name": "teste.pdf",
            "doc_base64": "JVBERi0xLjQK",
        },
    }


def test_chat_returns_400_when_document_sent(client, auth_headers):
    """F4d: /chat nao processa document — apenas retorna info."""
    response = client.post("/chat", json=_document_payload(), headers=auth_headers)
    assert response.status_code == 400
    body = response.json()
    assert "webhook" in body["reply"].lower()


def test_chat_processes_text_only_without_document(client, auth_headers):
    """F4d: /chat continua funcionando para mensagens de texto."""
    payload = {
        "instance": "jennifer",
        "phone": "5511966830020",
        "text": "oi",
        "sender_name": "Vini",
        "extra": {},
    }
    with patch("main.orchestrate", new_callable=AsyncMock,
               return_value={"reply": "Oi Vini!", "delay_ms": 0,
                             "presence": "composing", "metadata": {"agent_id": "jennifier"}}):
        response = client.post("/chat", json=payload, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Oi Vini!"


def test_chat_returns_422_when_no_phone(client, auth_headers):
    payload = {
        "instance": "jennifer",
        "phone": "",
        "text": "oi",
        "sender_name": "Vini",
        "extra": {},
    }
    response = client.post("/chat", json=payload, headers=auth_headers)
    assert response.status_code == 422


def test_chat_returns_422_when_no_text_audio_document(client, auth_headers):
    payload = {
        "instance": "jennifer",
        "phone": "5511966830020",
        "text": "",
        "sender_name": "Vini",
        "extra": {},
    }
    response = client.post("/chat", json=payload, headers=auth_headers)
    assert response.status_code == 422
