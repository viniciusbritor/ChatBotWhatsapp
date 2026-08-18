from unittest.mock import MagicMock, patch
from core import admin_notify

# Mock create_pending_approval para falhar
failing_mock = MagicMock(side_effect=Exception("firestore down"))

with patch("core.admin_notify.create_pending_approval", failing_mock, raising=False), \
     patch("core.admin_notify.resolve_owner_phone", return_value="5511966830020", raising=False), \
     patch("core.admin_notify.send_text", new=__import__('asyncio').coroutine(lambda: None) if False else MagicMock(), raising=False):
    # Mas o send_text sera chamado? Vou verificar:
    print("create_pending_approval:", admin_notify.create_pending_approval)
    print("resolve_owner_phone:", admin_notify.resolve_owner_phone)