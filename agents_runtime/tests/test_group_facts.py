"""Testes de grupo/fatos publicos (Branch B G1/G2/G5/G7)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.asyncio


class _FakeDoc:
    def __init__(self, data, exists=True):
        self._data = data or {}
        self._exists = exists

    def to_dict(self):
        return dict(self._data)

    @property
    def exists(self):
        return self._exists


class _FakeRef:
    def __init__(self, data=None):
        self._data = data

    def get(self):
        return _FakeDoc(self._data, exists=bool(self._data))

    def set(self, data, merge=False):
        if merge and self._data:
            self._data.update(data)
        else:
            self._data.clear()
            self._data.update(data)
        return None

    def update(self, data):
        self._data.update(data)
        return None

    def delete(self):
        self._data.clear()


class _FakeDb:
    def __init__(self, group_members=None, group_facts=None):
        self._gm = group_members or {}
        self._gf = group_facts or {}

    def collection(self, name):
        if name == "group_members":
            return _FakeGroupMembersColl(self._gm)
        if name == "group_facts":
            return _FakeGroupFactsColl(self._gf)
        return _FakeColl([])


class _FakeGroupMembersColl:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        if doc_id not in self._docs:
            self._docs[doc_id] = {}
        return _FakeRef(self._docs[doc_id])


class _FakeGroupFactsColl:
    def __init__(self, docs):
        self._docs = docs
        self._last_query = None

    def document(self, doc_id):
        if doc_id not in self._docs:
            self._docs[doc_id] = {}
        return _FakeRef(self._docs[doc_id])

    def where(self, field, op, value):
        self._last_query = (field, op, value)
        return self

    def limit(self, n):
        return self

    def stream(self):
        if self._last_query and self._last_query[2]:
            out = []
            for did, d in self._docs.items():
                if self._last_query[2] in d.get("witness_hashes", []):
                    out.append(_FakeDoc(d))
            return iter(out)
        return iter([_FakeDoc(d) for d in self._docs.values()])


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


async def test_sync_group_members_salva_snapshot():
    from tools import group

    fake_db = _FakeDb()
    evo_groups = [{
        "id": "120363@g.us",
        "subject": "P&D",
        "participants": [
            {"id": "1@lid", "phoneNumber": "5511997931324@s.whatsapp.net", "admin": "superadmin"},
            {"id": "2@lid", "phoneNumber": "5511966830020@s.whatsapp.net", "admin": "admin"},
        ],
    }]

    class _Resp:
        status_code = 200

        def json(self):
            return evo_groups

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            return _Resp()

    with patch("tools.group._get_firestore", return_value=fake_db), \
         patch("tools.group._evolution_headers", return_value={"apikey": "k"}), \
         patch("httpx.AsyncClient", return_value=_Client()):
        result = await group.sync_group_members()
    assert result["synced_groups"] == 1
    assert "120363@g.us" in fake_db._gm
    assert "5511997931324" in fake_db._gm["120363@g.us"]["member_phones"]


async def test_save_fact_grava_witnesses():
    from tools import group

    gm = {
        "120363@g.us": {
            "member_phones": ["5511966830020", "5511997931324"],
            "members": [{"phone": "5511966830020", "name": "Vini"}, {"phone": "5511997931324", "name": "Clarissa"}],
        }
    }
    fake_db = _FakeDb(group_members=gm)
    with patch("tools.group._get_firestore", return_value=fake_db), \
         patch("tools.group._group_member_phones", return_value=["5511966830020", "5511997931324"]):
        result = await group.save_fact("5511997931324", "120363@g.us", "faÃ§o 30 anos amanhÃ£", "Clarissa")
    assert "fact_id" in result
    assert result["witnesses"] == 2
    saved = list(fake_db._gf.values())[0]
    assert group._owner_hash("5511966830020") in saved["witness_hashes"]
    assert group._owner_hash("5511997931324") in saved["witness_hashes"]


async def test_search_facts_so_presenciou():
    from tools import group

    gh_vinicius = group._owner_hash("5511966830020")
    gh_maycon = group._owner_hash("5511999999999")
    facts = {
        "f1": {
            "fact": "faÃ§o 30 anos amanhÃ£",
            "group_jid": "120363@g.us",
            "revealed_by_name": "Clarissa",
            "witness_hashes": [gh_vinicius, group._owner_hash("5511997931324")],
            "created_at": "2026-08-12T00:00:00Z",
        },
        "f2": {
            "fact": "outro fato",
            "group_jid": "120363@g.us",
            "revealed_by_name": "X",
            "witness_hashes": [gh_maycon],
            "created_at": "2026-08-12T00:00:00Z",
        },
    }
    fake_db = _FakeDb(group_facts=facts)
    with patch("tools.group._get_firestore", return_value=fake_db):
        result = await group.search_facts("5511966830020", "")
    assert result["count"] == 1
    assert result["facts"][0]["fact"] == "faÃ§o 30 anos amanhÃ£"


async def test_search_facts_filtra_por_query():
    from tools import group

    gh = group._owner_hash("5511966830020")
    facts = {
        "f1": {"fact": "mora em SÃ£o Paulo", "witness_hashes": [gh], "created_at": "2026-08-12T00:00:00Z"},
        "f2": {"fact": "gosta de pizza", "witness_hashes": [gh], "created_at": "2026-08-12T00:00:00Z"},
    }
    fake_db = _FakeDb(group_facts=facts)
    with patch("tools.group._get_firestore", return_value=fake_db):
        result = await group.search_facts("5511966830020", "pizza")
    assert result["count"] == 1
    assert "pizza" in result["facts"][0]["fact"]


async def test_enrich_member_name():
    from tools import group

    gm = {
        "120363@g.us": {"members": [{"phone": "5511997931324", "name": ""}]},
    }
    fake_db = _FakeDb(group_members=gm)
    with patch("tools.group._get_firestore", return_value=fake_db):
        ok = await group.enrich_member_name("120363@g.us", "5511997931324", "Clarissa")
    assert ok is True
    assert fake_db._gm["120363@g.us"]["members"][0]["name"] == "Clarissa"
