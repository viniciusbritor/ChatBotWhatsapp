"""Testes de aprovação em 1 clique do Admin e notificações de acesso."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from core.admin_notify import create_approval_token, parse_approval_token, generate_approval_url, notify_admin_access_request
from agent_loader import is_user_approved, ensure_user_registered, get_user


def test_approval_token_roundtrip():
    phone = "5511988887777"
    token = create_approval_token(phone)
    assert token
    assert "." in token
    parsed = parse_approval_token(token)
    assert parsed == phone


def test_approval_token_invalid_or_tampered():
    token = create_approval_token("5511988887777")
    tampered = token[:-4] + "abcd"
    assert parse_approval_token(tampered) is None
    assert parse_approval_token("invalid.token") is None
    assert parse_approval_token("") is None


def test_generate_approval_url():
    url = generate_approval_url("5511988887777")
    assert "admin/approve-user?phone=5511988887777&token=" in url


@pytest.mark.asyncio
async def test_notify_admin_access_request():
    with patch("agent_loader.resolve_owner_phone", return_value="5511966830020"):
        with patch("core.evolution_client.send_text", AsyncMock(return_value=True)) as mock_send:
            res = await notify_admin_access_request(
                phone="5511977776666",
                sender_name="Carlos Teste",
                message_text="como está minha agenda?",
            )
            assert res is True
            mock_send.assert_called_once()
            args = mock_send.call_args[1]
            assert args["phone"] == "5511966830020"
            assert "Carlos Teste" in args["text"]
            assert "admin/approve-user" in args["text"]


def test_is_user_approved_owner_and_guest():
    with patch("agent_loader.resolve_owner_phone", return_value="5511966830020"):
        # Owner sempre aprovado
        assert is_user_approved("5511966830020") is True

        # Guest não aprovado
        with patch("agent_loader.get_user", return_value={"role": "guest", "is_approved": False}):
            assert is_user_approved("5511911112222") is False

        # Analista aprovado (via flag explicita)
        with patch("agent_loader.get_user", return_value={"role": "analyst", "is_approved": True}):
            assert is_user_approved("5511911112222") is True

        # GUARDRAIL §0.7 (16/08/2026): Aprovacao por approved_by continua valendo
        with patch("agent_loader.get_user", return_value={"role": "agent_user", "approved_by": "admin_whatsapp_link"}):
            assert is_user_approved("5511911112222") is True


def test_is_user_approved_strict_no_auto_approval():
    """GUARDRAIL §0.7: nenhum campo sozinho (role, oauth_token, email+portal) aprova.

    Antes do fix 1.3, existiam 3 caminhos de auto-aprovacao que vazaram acesso:
    Rafael Oliveira e Vivian Young foram auto-aprovados assim em 16/08/2026.
    Apos o fix, SOMENTE owner / is_approved=True / approved_by aprovado.
    """
    with patch("agent_loader.resolve_owner_phone", return_value="5511966830020"):
        with patch("agent_loader._is_instance_owner", return_value=False):
            # (a) Apenas role=analyst SEM approved_by -> NAO aprova (era o caso do Rafael)
            with patch("agent_loader.get_user", return_value={"role": "analyst", "is_approved": True, "email": "rafael@example.com"}):
                # Esse caso REALMENTE aprova pois is_approved=True esta setado.
                # Mas se is_approved NAO estiver setado (caso do bug original), NAO aprova.
                pass

            with patch("agent_loader.get_user", return_value={"role": "analyst"}):
                assert is_user_approved("5521984843235") is False

            # (b) Apenas google_oauth_token (sem is_approved) -> NAO aprova
            with patch("agent_loader.get_user", return_value={"google_oauth_token": {"token": "ya29.x"}}):
                assert is_user_approved("5511973391993") is False

            # (c) Apenas email+coherence_role (sem is_approved) -> NAO aprova
            with patch("agent_loader.get_user", return_value={"email": "vivian@example.com", "role": "agent_user"}):
                with patch("agent_loader.get_coherence_module_role", return_value="agent_user"):
                    assert is_user_approved("5511973391993") is False

            # (d) Apenas role=agent_user (sem is_approved) -> NAO aprova
            with patch("agent_loader.get_user", return_value={"role": "agent_user"}):
                assert is_user_approved("5511911112222") is False


def test_admin_approve_user_endpoint():
    from main import app
    client = TestClient(app)

    token = create_approval_token("5511944443333")
    with patch("agent_loader.get_user", return_value={"name": "Carlos Teste", "phone": "5511944443333"}):
        with patch("agent_loader.save_user", return_value=True) as mock_save:
            with patch("core.evolution_client.send_text", AsyncMock(return_value=True)) as mock_send:
                # 1. GET renderiza tela de confirmação (anti-crawler)
                res_get = client.get(f"/admin/approve-user?phone=5511944443333&token={token}")
                assert res_get.status_code == 200
                assert "Solicitação de Acesso" in res_get.text
                assert "Carlos Teste" in res_get.text
                mock_save.assert_not_called()
                mock_send.assert_not_called()

                # 2. POST executa a aprovação e dispara WhatsApp
                res_post = client.post(
                    "/admin/approve-user",
                    data={"phone": "5511944443333", "token": token},
                )
                assert res_post.status_code == 200
                assert "Analista Aprovado" in res_post.text
                mock_save.assert_called_once()
                mock_send.assert_called_once()
                saved_data = mock_save.call_args[0][1]
                assert saved_data["role"] == "analyst"
                assert saved_data["is_approved"] is True


def test_admin_me_phone_update_endpoint():
    """GUARDRAIL §0.7 (16/08/2026): /admin/me/phone NAO auto-aplica mais
    role=analyst nem is_approved=True no self-vinculo Portal->WhatsApp.
    Apenas persiste email/uid/name/picture; admin precisa aprovar manualmente.
    """
    from main import app
    client = TestClient(app)

    mock_caller = {
        "email": "analista@coherence.com",
        "name": "Analista Teste",
        "uid": "uid123",
        "role": "analyst",
        "is_admin": False,
    }

    with patch("core.auth.get_sa_token", return_value="test-sa"):
        with patch("core.auth.resolve_caller_profile", return_value=mock_caller):
            with patch("agent_loader.save_user", return_value=True) as mock_save:
                res = client.post(
                    "/admin/me/phone",
                    json={"phone": "+55 11 93333-2222"},
                    headers={"Authorization": "Bearer test-sa"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "ok"
                assert data["phone"] == "5511933332222"
                mock_save.assert_called_once()
                saved_data = mock_save.call_args[0][1]
                assert saved_data["email"] == "analista@coherence.com"
                # Aprovacao NAO e mais aplicada aqui
                assert "is_approved" not in saved_data or not saved_data.get("is_approved")
                assert "role" not in saved_data or saved_data.get("role") != "analyst"
