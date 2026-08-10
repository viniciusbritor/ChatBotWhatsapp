"""Testes dos roles do Portal (Fase 4) — owner = admin automatico.

Cobre o fix 10/08/2026: o owner da instancia (whatsapp_accounts.owner_phone)
resolve como admin mesmo sem campo ``role`` no Firestore. Isso impede que o
dono do bot seja bloqueado pelo middleware de agent_user.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch



def _fake_accounts(owner_phone: str):
    db = MagicMock()
    doc = MagicMock()
    doc.to_dict.return_value = {"owner_phone": owner_phone, "instance": "Jennifer"}
    db.collection.return_value.stream.return_value = [doc]
    return db


class TestGetUserRoleOwnerFix:
    def test_owner_resolves_admin_without_role_field(self):
        """Owner (5511966830020) SEM campo role no Firestore deve ser admin."""
        from agent_loader import get_user_role

        with patch("agent_loader._get_firestore_client", return_value=_fake_accounts("5511966830020")):
            assert get_user_role("5511966830020") == "admin"

    def test_owner_with_plus_and_dashes_still_admin(self):
        """Formato +55 11 96683-0020 tambem resolve admin."""
        from agent_loader import get_user_role

        with patch("agent_loader._get_firestore_client", return_value=_fake_accounts("+5511966830020")):
            assert get_user_role("5511966830020") == "admin"

    def test_non_owner_without_role_is_agent_user(self):
        """Telefone que nao e owner e sem role -> agent_user."""
        from agent_loader import get_user_role

        db = MagicMock()
        db.collection.return_value.stream.return_value = []

        def _get_user(phone):
            return None

        with patch("agent_loader._get_firestore_client", return_value=db):
            with patch("agent_loader.get_user", side_effect=_get_user):
                assert get_user_role("5511888888888") == "agent_user"

    def test_non_owner_with_admin_role_field_is_admin(self):
        """Telefone com role=admin no Firestore (sem ser owner) continua admin."""
        from agent_loader import get_user_role

        db = MagicMock()
        db.collection.return_value.stream.return_value = []

        with patch("agent_loader._get_firestore_client", return_value=db):
            with patch("agent_loader.get_user", return_value={"role": "admin"}):
                assert get_user_role("5511888888888") == "admin"

    def test_non_owner_with_agent_user_role_field(self):
        """Telefone com role=agent_user no Firestore -> agent_user."""
        from agent_loader import get_user_role

        db = MagicMock()
        db.collection.return_value.stream.return_value = []

        with patch("agent_loader._get_firestore_client", return_value=db):
            with patch("agent_loader.get_user", return_value={"role": "agent_user"}):
                assert get_user_role("5511888888888") == "agent_user"


class TestResolveCaller:
    def test_sa_token_is_admin(self):
        """SA token (Bearer) resolve admin sem Firestore."""
        from core.auth import resolve_caller

        expected = "sa-token-test"
        with patch("core.auth.get_sa_token", return_value=expected):
            request = MagicMock()
            request.headers = {"Authorization": "Bearer " + expected}
            request.query_params = {}
            request.cookies = {}
            role, phone = resolve_caller(request)
        assert role == "admin"
        assert phone == ""

    def test_firebase_jwt_without_phone_is_admin(self):
        """JWT valido sem phone_number -> admin (Portal Coherence)."""
        from core.auth import resolve_caller

        with patch("core.auth.get_sa_token", return_value="different-token"):
            with patch(
                "core.auth._firebase_claims",
                return_value={"sub": "abc", "email": "user@example.com"},
            ):
                request = MagicMock()
                request.headers = {"Authorization": "Bearer firebase-jwt"}
                request.query_params = {}
                request.cookies = {}
                role, phone = resolve_caller(request)
        assert role == "admin"
        assert phone == ""


class TestAgentUserWhitelist:
    def test_agent_user_blocked_on_global_admin_paths(self):
        """agent_user nao acessa /admin/agents (fora da whitelist)."""
        from core.auth import _agent_user_allowed

        assert _agent_user_allowed("/admin/agents") is False
        assert _agent_user_allowed("/admin/accounts") is False
        assert _agent_user_allowed("/admin/skills") is False
        assert _agent_user_allowed("/admin/tools") is False
        assert _agent_user_allowed("/admin/owners") is False
        assert _agent_user_allowed("/admin/knowledge") is False

    def test_agent_user_allowed_on_self_scoped_paths(self):
        """agent_user acessa dashboard, status, users/{self} e composio."""
        from core.auth import _agent_user_allowed

        assert _agent_user_allowed("/admin/dashboard") is True
        assert _agent_user_allowed("/admin/status") is True
        assert _agent_user_allowed("/admin/users/5511888888888") is True
        assert _agent_user_allowed("/admin/users/5511888888888/folder-permissions") is True
        assert _agent_user_allowed("/api/v1/composio/status") is True
        assert _agent_user_allowed("/api/v1/composio/authorize") is True

    def test_agent_user_blocked_on_users_list(self):
        """agent_user NAO lista todos os usuarios (/admin/users exato)."""
        from core.auth import _agent_user_allowed

        assert _agent_user_allowed("/admin/users") is False


class TestRenderDashboardRoles:
    def test_admin_sees_all_tabs(self):
        from core.module_ui import render_dashboard

        html = render_dashboard("abc", "now", role="admin")
        assert html.count("data-tab=") == 8
        assert 'data-tab="agents"' in html

    def test_agent_user_sees_three_tabs(self):
        from core.module_ui import render_dashboard

        html = render_dashboard("abc", "now", role="agent_user", caller_phone="5511888888888")
        assert html.count("data-tab=") == 3
        assert 'data-tab="permissoes"' in html
        assert 'data-tab="agents"' not in html
        assert "5511888888888" in html
