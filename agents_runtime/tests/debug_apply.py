from unittest.mock import MagicMock, patch
from core import approval_store

mock_db = MagicMock()
mock_doc_ref = MagicMock()

class FakeSnapshot:
    exists = True
    def to_dict(self):
        return {
            'run_id': 'abc',
            'phone': '551',
            'name': 'Pedro',
            'intent': 'email',
            'message': 'test',
            'status': 'pending',
            'created_at': '2026-01-01',
        }

# Substituir MagicMock por classe real
class FakeDocumentRef:
    def get(self, *args, **kwargs):
        return FakeSnapshot()
    def update(self, *args, **kwargs):
        pass

def fake_collection(name):
    mock = MagicMock()
    if name == "approval_requests":
        mock.document.return_value = FakeDocumentRef()
    return mock

mock_db.collection.side_effect = fake_collection

with patch.object(approval_store, '_db', return_value=mock_db):
    mock_tx = MagicMock()
    mock_db.transaction.return_value = mock_tx
    applied = approval_store.apply_decision('abc', 'approved', '5511966830020')
    print('applied:', applied)