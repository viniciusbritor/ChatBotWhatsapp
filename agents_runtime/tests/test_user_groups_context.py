"""Testes de _user_groups_context (Camadas 1+2: denormalizacao + cache TTL)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import user_groups_cache
from orchestrator import _user_groups_context


class _FakeDoc:
    def __init__(self, data, exists=True):
        self._data = data
        self._exists = exists

    def to_dict(self):
        return dict(self._data or {})

    @property
    def exists(self):
        return self._exists


class _FakeRef:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _FakeDoc(self._data, exists=self._data is not None)


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return _FakeRef(self._docs.get(doc_id))


class _FakeDb:
    def __init__(self, users=None):
        self._users = users or {}

    def collection(self, name):
        if name == "usuarios":
            return _FakeColl(self._users)
        raise AssertionError(f"unexpected collection: {name}")


class _BoomDb:
    def collection(self, name):
        raise AssertionError("db acessado em cache hit")


async def _call(phone, fake_db):
    with patch("core.message_ledger._get_firestore", return_value=fake_db):
        return await _user_groups_context(phone)


@pytest.mark.asyncio
async def test_cache_hit_nao_toca_no_db():
    user_groups_cache.clear()
    user_groups_cache.set("5511966830020", "Grupos em comum com o usuario: P&D")
    result = await _call("5511966830020", _BoomDb())
    assert "P&D" in result


@pytest.mark.asyncio
async def test_miss_le_doc_denormalizado_e_cacheia():
    user_groups_cache.clear()
    fake_db = _FakeDb({
        "5511966830020": {
            "group_memberships": [
                {"gid": "g1", "subject": "P&D"},
                {"gid": "g2", "subject": "Atas"},
            ],
        },
    })
    result = await _call("5511966830020", fake_db)
    assert result == "Grupos em comum com o usuario: P&D, Atas"
    assert user_groups_cache.get("5511966830020") == result


@pytest.mark.asyncio
async def test_dm_sem_grupos_cacheia_vazio():
    user_groups_cache.clear()
    fake_db = _FakeDb({})
    result = await _call("5511966830020", fake_db)
    assert result == ""
    assert user_groups_cache.get("5511966830020") == ""


@pytest.mark.asyncio
async def test_input_nao_canonico_e_normalizado():
    user_groups_cache.clear()
    fake_db = _FakeDb({
        "5511966830020": {
            "group_memberships": [{"gid": "g1", "subject": "P&D"}],
        },
    })
    result = await _call("11966830020", fake_db)
    assert "P&D" in result


def test_ttl_expirado_refaz_leitura():
    user_groups_cache.clear()
    user_groups_cache._CACHE["5511966830020"] = (0.0, "stale")
    with patch.object(
        user_groups_cache,
        "_clock",
        return_value=user_groups_cache.USER_GROUPS_CACHE_TTL_SEC + 1000,
    ):
        assert user_groups_cache.get("5511966830020") is None


def test_invalidate_remove_entrada():
    user_groups_cache.clear()
    user_groups_cache.set("5511966830020", "ctx")
    user_groups_cache.invalidate("5511966830020")
    assert user_groups_cache.get("5511966830020") is None
