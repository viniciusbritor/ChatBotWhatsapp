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

    def test_claim_transaction_does_not_crash_with_real_client_mock(self):
        """claim() with mocked Firestore client — the @transaction.transactional
        decorator must not raise NameError when _get_firestore returns a client."""
        from core.message_ledger import claim

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value.to_dict.return_value = {"state": "received"}
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        mock_transaction = MagicMock()
        mock_db.transaction.return_value = mock_transaction

        def _fake_transactional(fn):
            """Simulate @transaction.transactional decorator behavior."""
            return fn

        mock_transaction.transactional = _fake_transactional

        with patch("core.message_ledger._get_firestore", return_value=mock_db):
            result = claim("test-message-id")
        assert result is not None
        assert result["state"] == "processing"
