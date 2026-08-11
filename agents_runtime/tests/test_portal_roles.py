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


class TestResolveCallerHybrid:
    """resolve_caller hibrido: phone_number claim -> email lookup -> uid lookup."""

    def _request(self, claims):
        from core.auth import resolve_caller

        with patch("core.auth.get_sa_token", return_value="sa-token"):
            with patch("core.auth._firebase_claims", return_value=claims):
                request = MagicMock()
                request.headers = {"Authorization": "Bearer jwt"}
                request.query_params = {}
                request.cookies = {}
                return resolve_caller(request)

    def test_phone_claim_wins(self):
        """Claim phone_number tem prioridade sobre lookup."""
        role, phone = self._request({"sub": "uid1", "email": "ana@company.com", "phone_number": "+5511888888888"})
        assert phone == "5511888888888"
        assert role == "agent_user"

    def test_email_lookup_finds_phone(self):
        """Sem phone no claim, busca usuarios/* pelo email."""
        with patch("agent_loader.lookup_phone_by_email", return_value="5511777777777"):
            with patch("agent_loader.get_user_role", return_value="agent_user"):
                role, phone = self._request({"sub": "uid1", "email": "ana@company.com"})
        assert phone == "5511777777777"
        assert role == "agent_user"

    def test_admin_email_without_phone_is_admin(self):
        """Email admin na whitelist, sem phone vinculado -> admin."""
        with patch("agent_loader.lookup_phone_by_email", return_value=""):
            with patch("agent_loader.get_user_role", side_effect=lambda x: "admin" if "@" in x else "agent_user"):
                role, phone = self._request({"sub": "uid1", "email": "viniciusbritor@gmail.com"})
        assert role == "admin"
        assert phone == ""

    def test_unknown_email_is_agent_user(self):
        """Email desconhecido e sem phone vinculado -> agent_user (seguro)."""
        with patch("agent_loader.lookup_phone_by_email", return_value=""):
            with patch("agent_loader.get_user_role", return_value="agent_user"):
                role, phone = self._request({"sub": "uid1", "email": "nobody@example.com"})
        assert role == "agent_user"
        assert phone == ""

    def test_uid_lookup_fallback(self):
        """Sem email, tenta lookup por firebase_uid."""
        claims = {"sub": "firebase-uid-xyz"}
        with patch("agent_loader.lookup_phone_by_email", return_value=""):
            with patch("agent_loader.lookup_phone_by_uid", return_value="5511666666666"):
                with patch("agent_loader.get_user_role", return_value="agent_user"):
                    role, phone = self._request(claims)
        assert phone == "5511666666666"
        assert role == "agent_user"


class TestLookupPhone:
    def test_lookup_phone_by_email_finds_doc(self):
        from agent_loader import lookup_phone_by_email

        db = MagicMock()
        doc1 = MagicMock()
        doc1.id = "5511777777777"
        doc1.to_dict.return_value = {"email": "ana@company.com"}
        doc2 = MagicMock()
        doc2.id = "5511888888888"
        doc2.to_dict.return_value = {"email": "outro@x.com"}
        db.collection.return_value.stream.return_value = [doc1, doc2]

        with patch("agent_loader._get_firestore_client", return_value=db):
            assert lookup_phone_by_email("ANA@company.com") == "5511777777777"

    def test_lookup_phone_by_email_case_insensitive(self):
        from agent_loader import lookup_phone_by_email

        db = MagicMock()
        doc = MagicMock()
        doc.id = "5511777777777"
        doc.to_dict.return_value = {"email": "ana@company.com"}
        db.collection.return_value.stream.return_value = [doc]

        with patch("agent_loader._get_firestore_client", return_value=db):
            assert lookup_phone_by_email("Ana@Company.COM") == "5511777777777"

    def test_lookup_phone_by_email_not_found(self):
        from agent_loader import lookup_phone_by_email

        db = MagicMock()
        db.collection.return_value.stream.return_value = []
        with patch("agent_loader._get_firestore_client", return_value=db):
            assert lookup_phone_by_email("nobody@x.com") == ""

    def test_lookup_phone_by_email_invalid(self):
        from agent_loader import lookup_phone_by_email

        assert lookup_phone_by_email("") == ""
        assert lookup_phone_by_email("not-an-email") == ""

    def test_lookup_phone_by_uid_finds_doc(self):
        from agent_loader import lookup_phone_by_uid

        db = MagicMock()
        doc = MagicMock()
        doc.id = "5511777777777"
        doc.to_dict.return_value = {"firebase_uid": "uid-abc"}
        db.collection.return_value.stream.return_value = [doc]

        with patch("agent_loader._get_firestore_client", return_value=db):
            assert lookup_phone_by_uid("uid-abc") == "5511777777777"


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
        assert html.count('<button data-tab=') == 7
        assert 'data-tab="agents"' in html

    def test_agent_user_sees_three_tabs(self):
        from core.module_ui import render_dashboard

        html = render_dashboard("abc", "now", role="agent_user", caller_phone="5511888888888")
        assert html.count('<button data-tab=') == 3
        assert 'data-tab="permissoes"' in html
        assert 'data-tab="agents"' not in html
        assert "5511888888888" in html


class TestAdminWhitelist:
    """Whitelist config/admins: email e UID do admin."""

    def _patch_admins(self, emails=None, uids=None):
        from unittest.mock import patch

        return patch(
            "agent_loader._get_admins_config",
            return_value={
                "admin_emails": emails or ["viniciusbritor@gmail.com"],
                "admin_uids": uids or [],
            },
        )

    def test_admin_email_in_whitelist(self):
        from agent_loader import get_user_role

        with self._patch_admins():
            with patch("agent_loader._is_instance_owner", return_value=False):
                with patch("agent_loader.get_user", return_value=None):
                    assert get_user_role("viniciusbritor@gmail.com") == "admin"

    def test_non_admin_email_is_agent_user(self):
        from agent_loader import get_user_role

        with self._patch_admins():
            with patch("agent_loader._is_instance_owner", return_value=False):
                with patch("agent_loader.get_user", return_value=None):
                    assert get_user_role("ana@company.com") == "agent_user"

    def test_admin_email_case_insensitive(self):
        from agent_loader import get_user_role

        with self._patch_admins():
            with patch("agent_loader._is_instance_owner", return_value=False):
                with patch("agent_loader.get_user", return_value=None):
                    assert get_user_role("VINICIUSBRITOR@GMAIL.COM") == "admin"

    def test_admin_uid_in_whitelist(self):
        from agent_loader import get_user_role

        with self._patch_admins(uids=["o9ztuVhozgRIp3lGzyWdkw6G9JD3"]):
            with patch("agent_loader._is_instance_owner", return_value=False):
                with patch("agent_loader.get_user", return_value=None):
                    assert get_user_role("o9ztuVhozgRIp3lGzyWdkw6G9JD3") == "admin"

    def test_owner_phone_still_admin_without_whitelist(self):
        """Owner check continua funcionando mesmo com whitelist vazia."""
        from agent_loader import get_user_role

        with patch("agent_loader._is_instance_owner", return_value=True):
            assert get_user_role("5511966830020") == "admin"

    def test_missing_config_falls_back_to_agent_user(self):
        """Se config/admins nao existir, email desconhecido -> agent_user."""
        from agent_loader import get_user_role

        with patch("agent_loader._get_admins_config", return_value={"admin_emails": [], "admin_uids": []}):
            with patch("agent_loader._is_instance_owner", return_value=False):
                with patch("agent_loader.get_user", return_value=None):
                    assert get_user_role("ana@company.com") == "agent_user"
