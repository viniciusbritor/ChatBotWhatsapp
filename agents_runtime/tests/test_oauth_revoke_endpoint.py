"""Testes para os endpoints /api/v1/google/oauth/{revoke,status}.

GUARDRAIL §0.7 (19/08/2026): resolve bug onde desconectar no Portal
nao revogava tokens OAuth. Estes testes validam RBAC + fluxo completo.
"""
import asyncio
from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.responses import JSONResponse


def _make_request(body=None, query_params=None, role="agent_user", phone="5511966830020"):
    """Constroi um mock de Request com body e caller_role."""
    req = MagicMock(spec=Request)
    async def _json():
        return body or {}
    req.json = _json
    req.query_params = query_params or {}
    return req


async def _run(coro):
    return await coro


# --- /api/v1/google/oauth/revoke ---


def test_revoke_requires_phone():
    from main import google_oauth_revoke

    req = _make_request(body={}, role="admin", phone="5511966830020")
    with patch("main._caller_role", return_value=("admin", "")):
        response = asyncio.run(google_oauth_revoke(req))
    assert response.status_code == 400


def test_revoke_blocks_non_admin_revoking_other_phone():
    """agent_user so pode revogar o PROPRIO telefone."""
    from main import google_oauth_revoke

    req = _make_request(body={"phone": "5511000000000"}, role="agent_user", phone="5511966830020")
    with patch("main._caller_role", return_value=("agent_user", "5511966830020")):
        response = asyncio.run(google_oauth_revoke(req))
    assert response.status_code == 403


def test_revoke_allows_admin_revoking_any_phone():
    from main import google_oauth_revoke

    req = _make_request(body={"phone": "5511000000000"}, role="admin", phone="5511966830020")
    with patch("main._caller_role", return_value=("admin", "5511966830020")):
        with patch("core.oauth_per_user.revoke_user_oauth", return_value={
            "phone": "5511000000000",
            "access_revoked": True,
            "refresh_revoked": True,
            "firestore_deleted": True,
            "caches_cleared": {"calendar": True, "drive": True, "gmail": True},
            "revoked_at": "2026-08-19T22:00:00-03:00",
        }):
            with patch("agent_loader._get_firestore_client", return_value=None):
                response = asyncio.run(google_oauth_revoke(req))
    assert response.status_code == 200
    body = response.body.decode()
    assert "5511000000000" in body
    assert "access_revoked" in body


def test_revoke_agent_user_can_revoke_own_phone():
    from main import google_oauth_revoke

    req = _make_request(body={}, role="agent_user", phone="5511966830020")
    with patch("main._caller_role", return_value=("agent_user", "5511966830020")):
        with patch("core.oauth_per_user.revoke_user_oauth", return_value={
            "phone": "5511966830020",
            "access_revoked": True,
            "refresh_revoked": True,
            "firestore_deleted": True,
            "caches_cleared": {"calendar": True},
            "revoked_at": "2026-08-19T22:00:00-03:00",
        }):
            with patch("agent_loader._get_firestore_client", return_value=None):
                response = asyncio.run(google_oauth_revoke(req))
    assert response.status_code == 200


# --- /api/v1/google/oauth/status ---


def test_status_returns_connected_when_token_present():
    from main import google_oauth_status

    req = _make_request(query_params={"phone": "5511966830020"})
    with patch("main._caller_role", return_value=("agent_user", "5511966830020")):
        with patch("core.oauth_per_user.is_user_connected", return_value=True):
            with patch("core.oauth_per_user.get_user_oauth", return_value={
                "token": "x",
                "refresh_token": "y",
                "scopes": ["calendar", "gmail"],
                "updated_at": "2026-08-19T22:00:00-03:00",
            }):
                response = asyncio.run(google_oauth_status(req))
    assert response.status_code == 200
    body = response.body.decode()
    assert '"connected": true' in body
    assert "calendar" in body


def test_status_returns_disconnected_when_no_token():
    from main import google_oauth_status

    req = _make_request(query_params={"phone": "5511966830020"})
    with patch("main._caller_role", return_value=("agent_user", "5511966830020")):
        with patch("core.oauth_per_user.is_user_connected", return_value=False):
            with patch("agent_loader._get_firestore_client", return_value=None):
                response = asyncio.run(google_oauth_status(req))
    assert response.status_code == 200
    body = response.body.decode()
    assert '"connected": false' in body


def test_status_blocks_non_admin_querying_other_phone():
    from main import google_oauth_status

    req = _make_request(query_params={"phone": "5511000000000"})
    with patch("main._caller_role", return_value=("agent_user", "5511966830020")):
        response = asyncio.run(google_oauth_status(req))
    assert response.status_code == 403


def test_status_admin_can_query_any_phone():
    from main import google_oauth_status

    req = _make_request(query_params={"phone": "5511000000000"})
    with patch("main._caller_role", return_value=("admin", "5511966830020")):
        with patch("core.oauth_per_user.is_user_connected", return_value=False):
            with patch("agent_loader._get_firestore_client", return_value=None):
                response = asyncio.run(google_oauth_status(req))
    assert response.status_code == 200