from unittest.mock import patch

import pytest


class TestPendingActions:
    def setup_method(self):
        from core.pending_actions import _local_actions

        _local_actions.clear()

    @pytest.mark.asyncio
    async def test_set_get_and_consume_local_action(self):
        from core.pending_actions import consume_pending_action, get_pending_action, set_pending_action

        with patch("core.pending_actions._get_firestore", return_value=None):
            await set_pending_action(
                "5511999999999",
                "nickname_consent",
                {"first_name": "Vinicius", "nickname": "Vini"},
            )
            action = await get_pending_action("5511999999999")
            consumed = await consume_pending_action("5511999999999", "nickname_consent")
            remaining = await get_pending_action("5511999999999")

        assert action["action_type"] == "nickname_consent"
        assert action["expires_at"].endswith("-03:00")
        assert consumed["payload"]["nickname"] == "Vini"
        assert remaining is None

    @pytest.mark.asyncio
    async def test_wrong_type_does_not_consume_action(self):
        from core.pending_actions import consume_pending_action, get_pending_action, set_pending_action

        with patch("core.pending_actions._get_firestore", return_value=None):
            await set_pending_action("5511999999999", "nickname_consent", {})
            result = await consume_pending_action("5511999999999", "group_consent")
            remaining = await get_pending_action("5511999999999")

        assert result is None
        assert remaining is not None

    @pytest.mark.asyncio
    async def test_expired_action_is_removed(self):
        from core.pending_actions import _local_actions, _owner_hash, get_pending_action

        owner_hash = _owner_hash("5511999999999")
        _local_actions[owner_hash] = {
            "owner_hash": owner_hash,
            "action_type": "nickname_consent",
            "payload": {},
            "expires_at": "2020-01-01T00:00:00-03:00",
        }
        with patch("core.pending_actions._get_firestore", return_value=None):
            result = await get_pending_action("5511999999999")

        assert result is None
        assert owner_hash not in _local_actions
