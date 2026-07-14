"""Tests for Fase 7 (LGPD + Commands + Audit)."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestLGPDCleanup:
    def test_cleanup_history_no_firestore(self):
        from core.lgpd import cleanup_old_history
        with patch("core.lgpd._get_firestore", return_value=None):
            result = cleanup_old_history()
        assert result["deleted"] == 0

    def test_cleanup_audit_no_firestore(self):
        from core.lgpd import cleanup_old_audit
        with patch("core.lgpd._get_firestore", return_value=None):
            result = cleanup_old_audit()
        assert result["deleted"] == 0

    def test_export_user_data_no_firestore(self):
        from core.lgpd import export_user_data
        with patch("core.lgpd._get_firestore", return_value=None):
            result = export_user_data("+5511999999999")
        assert "error" in result

    def test_delete_user_data_no_firestore(self):
        from core.lgpd import delete_user_data
        with patch("core.lgpd._get_firestore", return_value=None):
            result = delete_user_data("+5511999999999")
        assert "error" in result


class TestCommands:
    def test_detect_silence(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, silêncio") == "off"
        assert detect_command("jennifer silencio") == "off"
        assert detect_command("Jennifer, Silêncio!") == "off"

    def test_detect_zen(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, modo zen") == "zen"

    def test_detect_turbo(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, modo turbo") == "turbo"

    def test_detect_emergencias(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, só emergências") == "emergencies"
        assert detect_command("jennifer so emergencias") == "emergencies"

    def test_detect_retomar(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, retomar") == "normal"

    def test_detect_grupo(self):
        from core.commands import detect_command
        assert detect_command("Jennifer, grupo off") == "group_off"
        assert detect_command("Jennifer, grupo on") == "group_on"

    def test_no_command(self):
        from core.commands import detect_command
        assert detect_command("Oi tudo bem?") is None
        assert detect_command("Como vai?") is None
        assert detect_command("") is None

    @pytest.mark.asyncio
    async def test_apply_command_no_firestore(self):
        from core.commands import apply_command
        with patch("core.commands._get_firestore", return_value=None):
            result = await apply_command("+5511999999999", "off")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handle_command_if_any(self):
        from core.commands import handle_command_if_any

        with patch("core.commands.apply_command", new_callable=AsyncMock) as mock_apply:
            mock_apply.return_value = {"new_mode": "off", "message": "OK"}
            result = await handle_command_if_any("+5511999999999", "Jennifer, silêncio")
        assert result["new_mode"] == "off"

    @pytest.mark.asyncio
    async def test_handle_no_command(self):
        from core.commands import handle_command_if_any
        result = await handle_command_if_any("+5511999999999", "Oi tudo bem?")
        assert result is None


class TestAudit:
    def test_log_action_no_firestore(self):
        from core.audit import log_action
        with patch("core.audit._get_firestore", return_value=None):
            result = log_action("user", "TEST", "target", {"key": "value"})
        assert result is False

    def test_log_chat(self):
        from core.audit import log_chat
        with patch("core.audit.log_action", return_value=True) as mock_log:
            result = log_chat("+5511999999999", "jennifier", "oi", "Oi!", 100, 50)
        assert result is True
        assert mock_log.called