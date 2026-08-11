"""Tests for tools.weather (Open-Meteo, sem API key)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import weather  # noqa: E402

_GEO_URL = weather._GEO_URL
_FORECAST_URL = weather._FORECAST_URL
pytestmark = pytest.mark.asyncio


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_geo_response():
    return {"results": [{"name": "Sao Paulo", "latitude": -23.55, "longitude": -46.63, "country": "Brasil", "admin1": "Sao Paulo"}]}


def _fake_forecast_current():
    return {
        "current": {
            "temperature_2m": 27.3,
            "relative_humidity_2m": 61,
            "apparent_temperature": 28.0,
            "weather_code": 1,
            "wind_speed_10m": 12.5,
        }
    }


def _fake_forecast_daily():
    return {
        "daily": {
            "time": ["2026-08-11", "2026-08-12", "2026-08-13"],
            "weather_code": [61, 0, 95],
            "temperature_2m_max": [28.0, 30.1, 25.4],
            "temperature_2m_min": [18.2, 19.5, 17.0],
            "precipitation_probability_max": [80, 5, 95],
            "wind_speed_10m_max": [15.0, 10.2, 22.4],
        }
    }


class _FakeClient:
    """httpx.AsyncClient fake que roteia por URL."""

    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, **kwargs):
        for key, payload in self._responses.items():
            if key in url:
                return _Resp(payload)
        return _Resp({"results": []})


async def test_geocode_cidade():
    fake = _FakeClient({_GEO_URL: _fake_geo_response()})
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather._geocode("Sao Paulo")
    assert result["latitude"] == -23.55
    assert result["nome"] == "Sao Paulo"


async def test_geocode_nao_encontrada():
    fake = _FakeClient({})
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather._geocode("CidadeInexistenteXYZ")
    assert "error" in result


async def test_current_ok():
    fake = _FakeClient({
        _GEO_URL: _fake_geo_response(),
        _FORECAST_URL: _fake_forecast_current(),
    })
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather.current("Sao Paulo")
    assert result["temperatura_c"] == 27.3
    assert result["umidade_pct"] == 61
    assert result["vento_kmh"] == 12.5
    assert result["condicao"]  # condicao pt-BR nao vazia


async def test_current_cidade_inexistente():
    fake = _FakeClient({})
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather.current("Atlantida")
    assert "error" in result


async def test_forecast_ok():
    fake = _FakeClient({
        _GEO_URL: _fake_geo_response(),
        _FORECAST_URL: _fake_forecast_daily(),
    })
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather.forecast("Sao Paulo", dias=3)
    assert len(result["dias"]) == 3
    assert result["dias"][0]["max_c"] == 28.0
    assert result["dias"][0]["prob_chuva_pct"] == 80
    assert result["dias"][2]["condicao"] == "trovoada"


async def test_forecast_dias_clamp():
    fake = _FakeClient({
        _GEO_URL: _fake_geo_response(),
        _FORECAST_URL: _fake_forecast_daily(),
    })
    with patch("tools.weather.httpx.AsyncClient", return_value=fake):
        result = await weather.forecast("Sao Paulo", dias=0)
    assert len(result.get("dias", [])) <= 7
