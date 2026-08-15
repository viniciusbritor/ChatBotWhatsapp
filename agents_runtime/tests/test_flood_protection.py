"""Unit tests for Flood Protection, Anti-DDoS, Circuit Breaker and FinOps Shield."""
import pytest
from unittest.mock import MagicMock, patch

from core.flood_protection import (
    check_and_record_message,
    is_user_quarantined,
    quarantine_user,
    unquarantine_user,
    record_usage_metrics,
    get_user_finops_metrics,
    get_all_finops_overview,
    _USER_MESSAGE_TIMESTAMPS,
    _QUARANTINE_CACHE,
)
from core.admin_notify import create_unblock_token, parse_unblock_token, generate_unblock_url


@pytest.fixture(autouse=True)
def _clean_state():
    _USER_MESSAGE_TIMESTAMPS.clear()
    _QUARANTINE_CACHE.clear()
    yield
    _USER_MESSAGE_TIMESTAMPS.clear()
    _QUARANTINE_CACHE.clear()


class TestFloodProtection:
    """Test rate limiting and quarantine logic."""

    def test_burst_messages_triggers_quarantine(self):
        """Disparo de 5 mensagens dentro da janela coloca o usuario em quarentena."""
        phone = "5511999990001"
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_doc.to_dict.return_value = {}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("core.flood_protection._get_firestore_client", return_value=mock_db):
            for i in range(4):
                blocked, details = check_and_record_message(phone, "group1@g.us", "Jennifer", f"msg {i}")
                assert not blocked
                assert details == {}

            # 5ª mensagem atinge o threshold
            blocked, details = check_and_record_message(phone, "group1@g.us", "Jennifer", "msg 5")
            assert blocked is True
            assert details.get("quarantined") is True
            assert details.get("burst_count") == 5
            assert details.get("phone") == phone

    def test_is_user_quarantined_returns_true_when_active(self):
        """Verifica que o status de quarentena é retornado corretamente."""
        phone = "5511999990002"
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"is_quarantined": True, "quarantine_reason": "flood"}
        mock_db.collection.return_value.document.return_value = mock_doc

        with patch("core.flood_protection._get_firestore_client", return_value=mock_db):
            assert is_user_quarantined(phone) is True

    def test_unquarantine_user_clears_cache_and_state(self):
        """Desbloquear usuario zera o estado de quarentena e a janela deslizante."""
        phone = "5511999990003"
        _USER_MESSAGE_TIMESTAMPS[phone] = [100.0, 101.0, 102.0]
        _QUARANTINE_CACHE[phone] = (True, 100.0)

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc

        with patch("core.flood_protection._get_firestore_client", return_value=mock_db):
            success = unquarantine_user(phone)
            assert success is True
            assert is_user_quarantined(phone) is False
            assert phone not in _USER_MESSAGE_TIMESTAMPS


class TestUnblockTokens:
    """Test HMAC SHA-256 tokens for 1-click WhatsApp unblock."""

    def test_create_and_parse_unblock_token(self):
        phone = "5511966830020"
        with patch("core.admin_notify._state_secret", return_value="super-secret-key-123"):
            token = create_unblock_token(phone)
            assert token != ""
            assert "." in token

            parsed = parse_unblock_token(token)
            assert parsed == phone

    def test_invalid_unblock_token_returns_none(self):
        with patch("core.admin_notify._state_secret", return_value="super-secret-key-123"):
            assert parse_unblock_token("invalid.token") is None
            assert parse_unblock_token("") is None

    def test_generate_unblock_url_includes_params(self):
        phone = "5511966830020"
        with patch("core.admin_notify._state_secret", return_value="super-secret-key-123"):
            url = generate_unblock_url(phone)
            assert "/admin/unblock-user?" in url
            assert f"phone={phone}" in url
            assert "token=" in url


class TestFinOpsMetrics:
    """Test usage and cost calculations."""

    def test_record_usage_metrics_increments_firestore(self):
        phone = "5511999990004"
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc

        with patch("core.flood_protection._get_firestore_client", return_value=mock_db):
            costs = {"deepseek_input_tokens": 1000, "deepseek_output_tokens": 500}
            record_usage_metrics(phone, "group1@g.us", "Jennifer", costs)
            mock_doc.set.assert_called_once()
            updates = mock_doc.set.call_args[0][0]
            assert "total_messages" in updates
            assert "estimated_cost_usd" in updates
            assert "estimated_cost_brl" in updates

    def test_get_all_finops_overview_aggregates_data(self):
        mock_db = MagicMock()
        doc1 = MagicMock()
        doc1.id = "5511999990001"
        doc1.to_dict.return_value = {
            "name": "User 1",
            "total_messages": 10,
            "estimated_cost_usd": 0.05,
            "is_quarantined": False,
        }
        doc2 = MagicMock()
        doc2.id = "5511999990002"
        doc2.to_dict.return_value = {
            "name": "Bot Attacker",
            "total_messages": 50,
            "estimated_cost_usd": 0.25,
            "is_quarantined": True,
        }
        mock_db.collection.return_value.stream.return_value = [doc1, doc2]

        with patch("core.flood_protection._get_firestore_client", return_value=mock_db):
            overview = get_all_finops_overview()
            assert overview["total_messages"] == 60
            assert overview["total_cost_usd"] == pytest.approx(0.30)
            assert overview["active_users_count"] == 1
            assert overview["quarantined_users_count"] == 1
            assert len(overview["users"]) == 2
