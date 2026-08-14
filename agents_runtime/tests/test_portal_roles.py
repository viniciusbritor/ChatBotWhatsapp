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
        assert phone in ("5511966830020", "")

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
        """agent_user nao acessa rotas restritas de admin (/admin/agents, accounts, skills, etc)."""
        from core.auth import _agent_user_allowed

        assert _agent_user_allowed("/admin/agents") is False
        assert _agent_user_allowed("/admin/accounts") is False
        assert _agent_user_allowed("/admin/skills") is False
        assert _agent_user_allowed("/admin/tools") is False
        assert _agent_user_allowed("/admin/owners") is False
        assert _agent_user_allowed("/admin/integrations") is False

    def test_agent_user_allowed_on_self_scoped_paths(self):
        """agent_user acessa dashboard, status, me, knowledge, users e composio."""
        from core.auth import _agent_user_allowed

        assert _agent_user_allowed("/admin/dashboard") is True
        assert _agent_user_allowed("/admin/status") is True
        assert _agent_user_allowed("/admin/me") is True
        assert _agent_user_allowed("/admin/knowledge") is True
        assert _agent_user_allowed("/admin/users") is True
        assert _agent_user_allowed("/admin/users/5511888888888") is True
        assert _agent_user_allowed("/admin/users/5511888888888/folder-permissions") is True
        assert _agent_user_allowed("/api/v1/composio/status") is True
        assert _agent_user_allowed("/api/v1/composio/authorize") is True


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


class TestAdminEndpointsRBAC:
    def test_admin_me_endpoint_returns_identity(self):
        import asyncio
        from unittest.mock import MagicMock, patch
        from main import admin_me

        request = MagicMock()
        with patch("main._caller_role", return_value=("admin", "5511966830020")):
            res = asyncio.run(admin_me(request))
            import json
            body = json.loads(res.body.decode())
            assert body["role"] == "admin"
            assert body["phone"] == "5511966830020"
            assert body["is_admin"] is True

    def test_admin_users_list_for_analyst_returns_only_self(self):
        import asyncio
        from unittest.mock import MagicMock, patch
        from main import admin_users_list

        request = MagicMock()
        mock_user = {"phone": "5511988776655", "name": "Analista Teste"}
        with patch("main._caller_role", return_value=("agent_user", "5511988776655")):
            with patch("main.get_user", return_value=mock_user):
                with patch("main._enrich_user_connections"):
                    res = asyncio.run(admin_users_list(request))
                    import json
                    body = json.loads(res.body.decode())
                    assert len(body["users"]) == 1
                    assert body["users"][0]["phone"] == "5511988776655"


class TestMagicLinkAuth:
    """Testes para o gerador e validador de Magic Links."""

    def test_generate_and_verify_valid_token(self):
        from core.magic_link import generate_magic_link_token, verify_magic_link_token

        token = generate_magic_link_token("5511999887766", ttl_seconds=3600)
        assert token.startswith("ml.")
        claims = verify_magic_link_token(token)
        assert claims is not None
        assert claims["phone"] == "5511999887766"
        assert claims["role"] == "agent_user"

    def test_verify_expired_token(self):
        from core.magic_link import generate_magic_link_token, verify_magic_link_token

        token = generate_magic_link_token("5511999887766", ttl_seconds=-10)
        assert verify_magic_link_token(token) is None

    def test_verify_tampered_token(self):
        from core.magic_link import generate_magic_link_token, verify_magic_link_token

        token = generate_magic_link_token("5511999887766", ttl_seconds=3600)
        tampered = token[:-4] + "abcd"
        assert verify_magic_link_token(tampered) is None

    def test_resolve_caller_with_magic_link(self):
        from core.magic_link import generate_magic_link_token
        from core.auth import resolve_caller
        from unittest.mock import MagicMock

        token = generate_magic_link_token("5511999887766", ttl_seconds=3600)
        req = MagicMock()
        req.headers = {"Authorization": f"Bearer {token}"}
        req.query_params = {}
        req.cookies = {}
        role, phone = resolve_caller(req)
        assert role == "agent_user"
        assert phone == "5511999887766"


class TestInviteAndKnowledgeEndpoints:
    """Testes para convites via WhatsApp e isolamento de conhecimento."""

    def test_invite_endpoint_success(self):
        import asyncio
        from unittest.mock import MagicMock, patch, AsyncMock
        from main import admin_users_invite

        req = MagicMock()
        with patch("main._require_admin"):
            with patch("core.evolution_client.send_text", new_callable=AsyncMock, return_value=True):
                res = asyncio.run(admin_users_invite("5511917389901", req))
                import json
                body = json.loads(res.body.decode())
                assert body["status"] == "ok"
                assert body["phone"] == "5511917389901"
                assert "magic_link" in body
                assert "ml." in body["magic_link"]
                assert body["whatsapp_sent"] is True

    def test_knowledge_isolation_analyst(self):
        import asyncio
        import hashlib
        from unittest.mock import MagicMock, patch
        from main import admin_knowledge_documents

        req = MagicMock()
        req.query_params = {"limit": "50"}
        caller_phone = "5511917389901"
        caller_hash = hashlib.sha256(caller_phone.encode()).hexdigest()[:32]
        other_hash = hashlib.sha256("5511966830020".encode()).hexdigest()[:32]

        doc_mine = MagicMock()
        doc_mine.id = "doc1"
        doc_mine.to_dict.return_value = {
            "source_title": "Meu Doc Privado",
            "owner_hash": caller_hash,
            "text_content": "Conteúdo secreto do analista",
        }

        doc_other = MagicMock()
        doc_other.id = "doc2"
        doc_other.to_dict.return_value = {
            "source_title": "Doc de Outro Usuário",
            "owner_hash": other_hash,
            "text_content": "Conteúdo restrito de terceiro",
        }

        mock_db = MagicMock()
        mock_db.collection.return_value.limit.return_value.stream.return_value = [doc_mine, doc_other]

        with patch("main._caller_role", return_value=("agent_user", caller_phone)):
            with patch("agent_loader._get_firestore_client", return_value=mock_db):
                res = asyncio.run(admin_knowledge_documents(req))
                import json
                body = json.loads(res.body.decode())
                assert len(body["documents"]) == 1
                assert body["documents"][0]["title"] == "Meu Doc Privado"

