"""Tests for cross-scope audit logging (F4d.9)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_cross_scope_attempt_logged_when_not_member():
    from agent_orchestration import knowledge_retriever

    envelope = {
        "phone": "+5511966830020",
        "extra": {"remote_jid": "120363@g.us"},
    }
    db = MagicMock()
    membership_doc = MagicMock()
    membership_doc.exists = False
    db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = membership_doc

    log_calls: list = []

    def fake_log_action(actor, action, target, details):
        log_calls.append({"actor": actor, "action": action,
                          "target": target, "details": details})

    fake_audit = MagicMock(log_action=fake_log_action)
    with patch("core.rag._get_firestore", return_value=db), \
         patch.dict("sys.modules", {"core.audit": fake_audit}):
        result = await knowledge_retriever.retrieve(
            envelope,
            "alguma coisa sobre X",
            limit=10,
            min_score=0.5,
        )

    assert result["decision"] == "denied"
    cross_scope_logs = [c for c in log_calls if c["action"] == "CROSS_SCOPE_ATTEMPT"]
    assert len(cross_scope_logs) >= 1
    assert cross_scope_logs[0]["target"] == "+5511966830020"