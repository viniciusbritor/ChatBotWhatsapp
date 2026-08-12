"""Testes do fix de scopes/merge de usuarios (Branch A F1/F3).

Cobre: merge do list_users prefere doc com mais scopes, desempate por
linked_at, save_user canonicaliza doc ID.
"""
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _doc(doc_id, phone, scopes, linked_at=None, updated_at=None):
    return {
        "id": doc_id,
        "phone": phone,
        "google_oauth_token": {"scopes": scopes, "token": "x"},
        "scopes": scopes,
        "google_oauth_linked_at": linked_at,
        "updated_at": updated_at,
    }


def _fake_db(docs):
    class FakeDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return self._data

    class FakeCollection:
        def __init__(self):
            self._docs = docs

        def stream(self):
            return iter([FakeDoc(d["id"], d) for d in self._docs])

    class FakeDb:
        def collection(self, name):
            return FakeCollection()

    return FakeDb()


def test_merge_prefers_more_scopes():
    from agent_loader import list_users

    docs = [
        _doc("11966830020", "11966830020", ["a", "b", "c", "d", "e"], linked_at=None),
        _doc("5511966830020", "5511966830020",
             ["a", "b", "c", "d", "e", "tasks", "contacts.readonly", "photoslibrary.readonly"],
             linked_at="2026-08-12T12:16:50-03:00"),
    ]
    with patch("agent_loader._get_firestore_client", return_value=_fake_db(docs)):
        users = list_users()
    assert len(users) == 1
    assert users[0]["phone"] == "5511966830020"
    assert len(users[0]["google_oauth_token"]["scopes"]) == 8


def test_merge_tiebreak_by_linked_at():
    from agent_loader import list_users

    docs = [
        _doc("5511966830020", "5511966830020", ["a", "b", "c", "d", "e"],
             linked_at="2026-08-12T12:16:50-03:00", updated_at="2026-08-12T12:16:50-03:00"),
        _doc("old", "5511966830020", ["a", "b", "c", "d", "e"],
             linked_at="2026-07-01T00:00:00-03:00", updated_at="2026-07-01T00:00:00-03:00"),
    ]
    with patch("agent_loader._get_firestore_client", return_value=_fake_db(docs)):
        users = list_users()
    assert users[0]["google_oauth_linked_at"] == "2026-08-12T12:16:50-03:00"


def test_user_doc_is_better_scopes():
    from agent_loader import _user_doc_is_better

    candidate = _doc("new", "5511966830020", ["a", "b", "c", "d", "e", "f"])
    current = _doc("old", "5511966830020", ["a", "b", "c", "d", "e"])
    assert _user_doc_is_better(candidate, current) is True
    assert _user_doc_is_better(current, candidate) is False


def test_user_doc_is_better_timestamp():
    from agent_loader import _user_doc_is_better

    candidate = _doc("new", "5511966830020", ["a", "b"],
                     linked_at="2026-08-12T12:16:50-03:00")
    current = _doc("old", "5511966830020", ["a", "b"],
                   linked_at="2026-07-01T00:00:00-03:00")
    assert _user_doc_is_better(candidate, current) is True


def test_save_user_canonicalizes_doc_id():
    from agent_loader import save_user

    written = {}

    class FakeDocRef:
        def set(self, data, merge=False):
            written["data"] = data
            return None

    class FakeColl:
        def document(self, doc_id):
            written["id"] = doc_id
            return FakeDocRef()

    class FakeDb:
        def collection(self, name):
            return FakeColl()

    with patch("agent_loader._get_firestore_client", return_value=FakeDb()):
        ok = save_user("11966830020", {"phone": "11966830020"})
    assert ok is True
    assert written["id"] == "5511966830020"
    assert written["data"]["phone"] == "5511966830020"
