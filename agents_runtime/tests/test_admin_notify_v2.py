"""Tests para core/admin_notify.py::notify_admin_access_request (FASE 2)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def mock_admin_notify(monkeypatch):
    """Mock resolve_owner_phone e send_text via setattr direto."""

    def fake_resolve():
        return "5511966830020"

    monkeypatch.setattr("agent_loader.resolve_owner_phone", fake_resolve)

    mock_send = AsyncMock(return_value=True)
    # A funcao usa `from core.evolution_client import send_text` dentro do escopo.
    # Patchamos no MOMENTO da importacao usando MockPatch via side_effect.
    # Estrategia: substituir o modulo core.evolution_client com um mock.
    import core.evolution_client as evo_mod
    monkeypatch.setattr(evo_mod, "send_text", mock_send, raising=False)

    # Tambem patchamos o nome local que admin_notify usa
    monkeypatch.setattr("core.admin_notify.resolve_owner_phone", fake_resolve, raising=False)
    monkeypatch.setattr("core.admin_notify.send_text", mock_send, raising=False)
    monkeypatch.setattr("core.admin_notify.create_pending_approval", lambda **kw: "run-test-1234", raising=False)
    monkeypatch.setattr("core.approval_store.create_pending_approval", lambda **kw: "run-test-1234")

    # Reset do cooldown cache (5 min por phone).
    from core import admin_notify
    admin_notify._NOTIFIED_PHONES_CACHE.clear()

    return mock_send


def _get_sent_message(mock_send):
    """Extrai a mensagem do mock send_text (kwargs)."""
    if not mock_send.call_args_list:
        return ""
    return mock_send.call_args_list[-1].kwargs.get("text", "")


class TestNotifyAdminAccessRequestMessageFormat:
    """Mensagem WhatsApp SEM link, COM instrucoes claras."""

    @pytest.mark.asyncio
    async def test_message_has_fast_path(self, mock_admin_notify):
        """Mensagem tem opcoes 'OK, APROVADO' e 'NAO, REJEITADO'."""
        from core import admin_notify

        result = await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro Costa",
            message_text="quero meu perfil do linkedin",
        )

        assert result is True
        sent_message = _get_sent_message(mock_admin_notify)
        assert "✅" in sent_message
        assert "OK, APROVADO" in sent_message
        assert "❌" in sent_message
        assert "NÃO, REJEITADO" in sent_message

    @pytest.mark.asyncio
    async def test_message_has_rich_path_link(self, mock_admin_notify):
        from core import admin_notify

        await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="test",
        )

        sent_message = _get_sent_message(mock_admin_notify)
        assert "portal.coherence-ai.com.br" in sent_message
        assert "gerencie" in sent_message.lower()

    @pytest.mark.asyncio
    async def test_message_has_run_id(self, mock_admin_notify):
        from core import admin_notify

        await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="",
        )

        sent_message = _get_sent_message(mock_admin_notify)
        assert "run-test-1234" in sent_message
        assert "Run ID" in sent_message

    @pytest.mark.asyncio
    async def test_no_old_style_link_in_message(self, mock_admin_notify):
        from core import admin_notify

        await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="",
        )

        sent_message = _get_sent_message(mock_admin_notify)
        assert "admin/approve-user" not in sent_message
        assert "token=" not in sent_message


class TestNotifyAdminAccessRequestCreatesPending:
    @pytest.mark.asyncio
    async def test_calls_create_pending_approval(self, mock_admin_notify):
        from core import admin_notify

        await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="quero meu email",
        )

        # create_pending_approval foi mockado para retornar "run-test-1234"
        # Entao o run_id no message deve ser "run-test-1234"
        sent_message = _get_sent_message(mock_admin_notify)
        assert sent_message != ""
        assert "run-test-1234" in sent_message

    @pytest.mark.asyncio
    async def test_returns_false_when_create_pending_fails(self, monkeypatch):
        from core import admin_notify
        from unittest.mock import MagicMock

        # Mock que lanca excecao quando chamado.
        failing_mock = MagicMock(side_effect=Exception("firestore down"))
        monkeypatch.setattr(
            "core.admin_notify.create_pending_approval",
            failing_mock,
            raising=False,
        )

        result = await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="",
        )

        assert result is False


class TestNotifyAdminAccessRequestGuards:
    @pytest.mark.asyncio
    async def test_returns_false_for_admin_phone(self, mock_admin_notify):
        from core import admin_notify

        result = await admin_notify.notify_admin_access_request(
            phone="5511966830020",  # MESMO phone do admin
            sender_name="Admin",
            message_text="",
        )

        assert result is False
        mock_admin_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_phone(self, mock_admin_notify):
        from core import admin_notify

        result = await admin_notify.notify_admin_access_request(
            phone="",
            sender_name="Pedro",
            message_text="",
        )

        assert result is False
        mock_admin_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_admin_phone(self, monkeypatch):
        from core import admin_notify

        def fake_resolve_empty():
            return ""

        monkeypatch.setattr("core.admin_notify.resolve_owner_phone", fake_resolve_empty, raising=False)
        monkeypatch.setattr("agent_loader.resolve_owner_phone", fake_resolve_empty)

        result = await admin_notify.notify_admin_access_request(
            phone="5511988776655",
            sender_name="Pedro",
            message_text="",
        )

        assert result is False
        from core.evolution_client import send_text
        send_text.assert_not_called()