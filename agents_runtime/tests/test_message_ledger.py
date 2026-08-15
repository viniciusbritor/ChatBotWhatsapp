"""Smoke tests for message_ledger claim() with Firestore transaction."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "test")
    monkeypatch.setenv("HOSTNAME", "test-host")


class TestClaimTransaction:
    """Verify claim() executes without NameError when Firestore is available."""

    def test_claim_returns_none_when_firestore_unavailable(self):
        """claim() returns None when _get_firestore() returns None (tests mock)."""
        from core.message_ledger import claim

        with patch("core.message_ledger._get_firestore", return_value=None):
            result = claim("test-message-id")
        assert result is None

    def test_claim_transaction_executes_without_name_error(self):
        """claim() with mocked Firestore client — verifies no NameError or
        AttributeError when the @firestore.transactional decorator runs."""
        from core.message_ledger import claim

        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value.to_dict.return_value = {"state": "response_ready"}
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        mock_db.transaction.return_value = MagicMock()

        with patch("core.message_ledger._get_firestore", return_value=mock_db):
            result = claim("test-message-id")
        assert result == {"state": "response_ready"}

    def test_mark_response_sanitizes_complex_reply(self):
        """mark_response sanitiza objetos não-serializáveis e bytes para evitar erro 400."""
        from core.message_ledger import mark_response, _sanitize_reply_for_firestore

        raw = {
            "reply": "ok",
            "_internal": "skip",
            "png_bytes": b"fake_png",
            "nested": {"bytes": b"data", "clean": 123},
        }
        sanitized = _sanitize_reply_for_firestore(raw)
        assert "_internal" not in sanitized
        assert "png_bytes" not in sanitized
        assert sanitized["nested"] == {"clean": 123}

        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("core.message_ledger._get_firestore", return_value=mock_db):
            mark_response("msg-123", raw)
        mock_doc_ref.update.assert_called_once()
        updates = mock_doc_ref.update.call_args[0][0]
        assert updates["state"] == "response_ready"
        assert "_internal" not in updates["reply"]

