"""Transporte tools — Google Maps Distance + estimativa Uber."""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_UBER_RATE_PER_KM = float(os.getenv("UBER_RATE_PER_KM", "3.50"))


async def _google_maps_distance(origin: str, destination: str) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {"error": "google_maps_api_key_missing"}

    try:
        import httpx
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin,
            "destinations": destination,
            "key": api_key,
            "units": "metric",
            "language": "pt-BR",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if data.get("status") != "OK":
                return {"error": data.get("status", "unknown")}

            element = data["rows"][0]["elements"][0]
            if element["status"] != "OK":
                return {"error": element["status"]}

            return {
                "origin": data["origin_addresses"][0],
                "destination": data["destination_addresses"][0],
                "distance_km": round(element["distance"]["value"] / 1000, 1),
                "distance_text": element["distance"]["text"],
                "duration_min": round(element["duration"]["value"] / 60, 0),
                "duration_text": element["duration"]["text"],
            }
    except Exception as exc:
        logger.warning("Google Maps call failed: %s", exc)
        return {"error": str(exc)[:200]}


async def calcular_rota(origem: str, destino: str) -> Dict[str, Any]:
    result = await _google_maps_distance(origem, destino)
    if "error" in result and result["error"].startswith("google_maps"):
        return {"error": "Chave do Google Maps nao configurada. Contate o administrador."}
    return result


async def estimar_uber(origem: str, destino: str) -> Dict[str, Any]:
    result = await _google_maps_distance(origem, destino)
    if "error" in result:
        return result

    distancia_km = result.get("distance_km", 0)
    if distancia_km <= 0:
        return {"error": "distancia_invalida"}

    valor_base = 5.0
    estimativa = round(valor_base + distancia_km * _UBER_RATE_PER_KM, 2)

    return {
        **result,
        "uber_estimativa_brl": estimativa,
        "taxa_por_km": _UBER_RATE_PER_KM,
        "taxa_base": valor_base,
        "nota": "Estimativa aproximada. Valor real pode variar conforme demanda, transito e horario.",
    }
