"""Weather tools — condicao atual e previsao (Open-Meteo, sem API key).

Open-Meteo e gratuito e nao exige cadastro/chave. O geocoding e feito
inline pelo arquivo cities.csv da propria Open-Meteo (endpoint /v1/search).
"""
import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_CONDITION_PT = {
    0: "ceu limpo",
    1: "predominantemente limpo",
    2: "parcialmente nublado",
    3: "encoberto",
    45: "nevoeiro",
    48: "nevoeiro com deposito de gelo",
    51: "garoa leve",
    53: "garoa moderada",
    55: "garoa densa",
    61: "chuva leve",
    63: "chuva moderada",
    65: "chuva forte",
    66: "chuva congelante leve",
    67: "chuva congelante forte",
    71: "neve leve",
    73: "neve moderada",
    75: "neve forte",
    77: "graos de neve",
    80: "pancadas de chuva leve",
    81: "pancadas de chuva moderada",
    82: "pancadas de chuva violenta",
    85: "pancadas de neve leve",
    86: "pancadas de neve forte",
    95: "trovoada",
    96: "trovoada com granizo leve",
    99: "trovoada com granizo forte",
}


def _condicao_pt(code: int) -> str:
    return _CONDITION_PT.get(int(code), "condicao desconhecida")


async def _geocode(cidade: str) -> Dict[str, Any]:
    """Resolve cidade para lat/lon usando o geocoder da Open-Meteo."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _GEO_URL,
            params={"name": cidade, "count": 1, "language": "pt", "format": "json"},
        )
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
        if not results:
            return {"error": f"cidade nao encontrada: {cidade}"}
        r = results[0]
        return {
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "nome": r.get("name", cidade),
            "pais": r.get("country", ""),
            "admin1": r.get("admin1", ""),
        }


async def current(cidade: str) -> Dict[str, Any]:
    """Condicao atual do tempo para uma cidade.

    Retorna temperatura, sensacao, umidade, vento e condicao (pt-BR).
    """
    geo = await _geocode(cidade)
    if "error" in geo:
        return geo
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _FORECAST_URL,
                params={
                    "latitude": geo["latitude"],
                    "longitude": geo["longitude"],
                    "current": (
                        "temperature_2m,relative_humidity_2m,apparent_temperature,"
                        "weather_code,wind_speed_10m"
                    ),
                    "timezone": "America/Sao_Paulo",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        cur = data.get("current") or {}
        return {
            "cidade": geo["nome"],
            "regiao": geo.get("admin1", ""),
            "pais": geo.get("pais", ""),
            "temperatura_c": round(cur.get("temperature_2m", 0), 1),
            "sensacao_c": round(cur.get("apparent_temperature", 0), 1),
            "umidade_pct": cur.get("relative_humidity_2m", 0),
            "vento_kmh": round(cur.get("wind_speed_10m", 0), 1),
            "condicao": _condicao_pt(cur.get("weather_code", 0)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("weather.current failed cidade=%s exc=%s", cidade, exc)
        return {"error": str(exc)[:200]}


async def forecast(cidade: str, dias: int = 3) -> Dict[str, Any]:
    """Previsao do tempo para os proximos N dias (1-7)."""
    dias = max(1, min(int(dias), 7))
    geo = await _geocode(cidade)
    if "error" in geo:
        return geo
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _FORECAST_URL,
                params={
                    "latitude": geo["latitude"],
                    "longitude": geo["longitude"],
                    "daily": (
                        "weather_code,temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max,wind_speed_10m_max"
                    ),
                    "forecast_days": dias,
                    "timezone": "America/Sao_Paulo",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        daily = data.get("daily") or {}
        dias_list: List[Dict[str, Any]] = []
        for i in range(dias):
            dias_list.append({
                "data": (daily.get("time") or [])[i],
                "condicao": _condicao_pt((daily.get("weather_code") or [0])[i]),
                "max_c": round((daily.get("temperature_2m_max") or [0])[i], 1),
                "min_c": round((daily.get("temperature_2m_min") or [0])[i], 1),
                "prob_chuva_pct": (daily.get("precipitation_probability_max") or [0])[i],
                "vento_max_kmh": round((daily.get("wind_speed_10m_max") or [0])[i], 1),
            })
        return {
            "cidade": geo["nome"],
            "regiao": geo.get("admin1", ""),
            "pais": geo.get("pais", ""),
            "dias": dias_list,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("weather.forecast failed cidade=%s exc=%s", cidade, exc)
        return {"error": str(exc)[:200]}
