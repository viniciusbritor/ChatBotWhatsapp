from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from core.oauth_per_user import create_oauth_state, parse_oauth_state
from main import oauth_callback, oauth_google


def _request(query):
    request = MagicMock()
    request.query_params = query
    request.url_for.return_value = "https://agents-runtime.example.run.app/oauth/callback"
    request.headers = {
        "x-forwarded-proto": "https",
        "x-forwarded-host": "agents-runtime.example.run.app",
    }
    request.url.scheme = "https"
    request.url.hostname = "agents-runtime.example.run.app"
    request.client.host = "127.0.0.1"
    return request


@pytest.mark.asyncio
async def test_oauth_start_creates_signed_state(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    with patch("main.OAUTH_CLIENT_ID", "client-id"):
        with patch("main.OAUTH_CLIENT_SECRET", "client-secret"):
            response = await oauth_google(_request({"phone": "+55 11 96683-0020"}))

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert parse_oauth_state(query["state"][0]) == "5511966830020"
    assert query["redirect_uri"][0] == "https://agents-runtime.example.run.app/oauth/callback"


@pytest.mark.asyncio
async def test_oauth_start_requires_phone():
    with pytest.raises(HTTPException) as exc:
        await oauth_google(_request({}))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_oauth_callback_rejects_unsigned_state():
    response = await oauth_callback(_request({"code": "code", "state": "unsigned"}))
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_saves_token_without_client_secret(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    state = create_oauth_state("5511966830020")
    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
    }

    with patch("main.OAUTH_CLIENT_ID", "client-id"):
        with patch("main.OAUTH_CLIENT_SECRET", "client-secret"):
            with patch("requests.post", return_value=token_response):
                with patch("agent_loader.save_user", return_value=True) as save_user:
                    with patch("agent_loader.get_user", return_value={}) as get_user:
                        response = await oauth_callback(
                            _request({"code": "authorization-code", "state": state})
                        )

    assert response.status_code == 200
    saved = save_user.call_args.args[1]
    token_data = saved["google_oauth_token"]
    assert token_data["token"] == "access-token"
    assert token_data["refresh_token"] == "refresh-token"
    assert "client_id" not in token_data
    assert "client_secret" not in token_data
    assert token_data["linked_at"].endswith("-03:00")


@pytest.mark.asyncio
async def test_oauth_callback_does_not_auto_approve(monkeypatch):
    """GUARDRAIL §0.7 (16/08/2026): /oauth/callback NAO seta mais
    role='analyst' nem is_approved=True. Antes do fix, qualquer pessoa que
    completasse OAuth era aprovada automaticamente (Vetor #1 do incidente).
    """
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    state = create_oauth_state("5511973391993")  # phone da Vivian (caso real)
    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "id_token": "x.y.z",
    }

    with patch("main.OAUTH_CLIENT_ID", "client-id"):
        with patch("main.OAUTH_CLIENT_SECRET", "client-secret"):
            with patch("requests.post", return_value=token_response):
                with patch("agent_loader.save_user", return_value=True) as save_user:
                    # Simula usuario NAO pre-aprovado (caso da Vivian antes do fix)
                    with patch("agent_loader.get_user", return_value={}) as get_user:
                        response = await oauth_callback(
                            _request({"code": "authorization-code", "state": state})
                        )

    assert response.status_code == 200
    saved = save_user.call_args.args[1]
    # OAuth NAO pode setar is_approved
    assert "is_approved" not in saved or saved.get("is_approved") is not True
    # OAuth NAO pode setar role=analyst
    assert saved.get("role") != "analyst"
    # OAuth apenas vincula token
    assert saved.get("google_oauth_token", {}).get("token") == "access-token"


@pytest.mark.asyncio
async def test_oauth_callback_does_not_auto_approve_even_if_token_present(monkeypatch):
    """GUARDRAIL §0.7: mesmo se get_user retornar um doc pre-existente SEM
    is_approved, o callback NAO pode aprovar. Antes do fix 1.1, o user_update
    sempre setava is_approved=True, sobrescrevendo o estado anterior.
    """
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    state = create_oauth_state("5511900000000")
    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 3600,
    }

    pre_existing_doc = {"phone": "5511900000000", "role": "guest", "is_approved": False}

    with patch("main.OAUTH_CLIENT_ID", "client-id"):
        with patch("main.OAUTH_CLIENT_SECRET", "client-secret"):
            with patch("requests.post", return_value=token_response):
                with patch("agent_loader.save_user", return_value=True) as save_user:
                    with patch("agent_loader.get_user", return_value=pre_existing_doc):
                        response = await oauth_callback(
                            _request({"code": "authorization-code", "state": state})
                        )

    assert response.status_code == 200
    saved = save_user.call_args.args[1]
    assert "is_approved" not in saved or saved.get("is_approved") is False
