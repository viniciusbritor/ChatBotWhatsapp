"""Tests for tools.locomotion.find_place (Google Places Text Search)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import locomotion  # noqa: E402

pytestmark = pytest.mark.asyncio


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, **kwargs):
        return _Resp(self._payload)


def _places_payload():
    return {
        "status": "OK",
        "results": [
            {
                "name": "EAP Emporio Alto dos Pinheiros",
                "formatted_address": "R. Vupabussu, 305 - Pinheiros, Sao Paulo - SP",
                "rating": 4.6,
                "user_ratings_total": 5619,
                "opening_hours": {"open_now": True},
                "place_id": "ChIJh2ktnrpXzpQR32ZpkbfI1y4",
            }
        ],
    }


async def test_find_place_ok():
    fake = _FakeClient(_places_payload())
    with patch("tools.locomotion._get_key", return_value="AIzaTESTE"), \
         patch("tools.locomotion._fetch", new_async(fake.get)):
        results = await locomotion.find_place("Emporio Alto Pinheiro", "Sao Paulo")
    assert results[0]["nome"] == "EAP Emporio Alto dos Pinheiros"
    assert results[0]["avaliacao"] == 4.6
    assert results[0]["aberto_agora"] is True
    assert results[0]["place_id"]


async def test_find_place_sem_chave():
    with patch("tools.locomotion._get_key", return_value=""):
        results = await locomotion.find_place("qualquer")
    assert "error" in results[0]


async def test_find_place_zeroresults():
    fake = _FakeClient({"status": "ZERO_RESULTS", "results": []})
    with patch("tools.locomotion._get_key", return_value="AIzaTESTE"), \
         patch("tools.locomotion._fetch", new_async(fake.get)):
        results = await locomotion.find_place("LugarInexistenteXYZ")
    assert results == []


async def test_find_place_erro_status():
    fake = _FakeClient({"status": "REQUEST_DENIED", "results": []})
    with patch("tools.locomotion._get_key", return_value="AIzaTESTE"), \
         patch("tools.locomotion._fetch", new_async(fake.get)):
        results = await locomotion.find_place("x")
    assert "error" in results[0]


def new_async(fn):
    async def _wrapper(*args, **kwargs):
        return await fn(*args, **kwargs)

    return _wrapper
