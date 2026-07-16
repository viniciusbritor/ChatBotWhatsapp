"""Google Maps tools: calc_route, geocode, search_places."""
import os, logging, asyncio

logger = logging.getLogger(__name__)
MAPS_API_KEY = None


def _get_key():
    global MAPS_API_KEY
    if not MAPS_API_KEY:
        from core.secrets import get_secret
        MAPS_API_KEY = (os.getenv("GOOGLE_MAPS_API_KEY") or get_secret("GOOGLE_MAPS_API_KEY") or "").strip()
    return MAPS_API_KEY


async def _fetch(url: str, params: dict = None, timeout: int = 15) -> dict:
    import requests
    import functools
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(requests.get, url, params=params or {}, timeout=timeout))


async def calc_route(origem: str, destino: str) -> dict:
    key = _get_key()
    if not key:
        return {"error": "GOOGLE_MAPS_API_KEY not configured"}
    try:
        resp = await _fetch("https://maps.googleapis.com/maps/api/directions/json", {
            "origin": origem, "destination": destino, "key": key, "language": "pt-BR"
        })
        data = resp.json()
        if data.get("status") != "OK":
            return {"error": data.get("status", "unknown")}
        leg = data["routes"][0]["legs"][0]
        dist_km = leg["distance"]["value"] / 1000
        dur_min = leg["duration"]["value"] / 60
        uber = max(5.50 + (dist_km * 2.80) + (dur_min * 0.35), 8.00)
        return {
            "origem": leg.get("start_address", origem),
            "destino": leg.get("end_address", destino),
            "distancia_km": round(dist_km, 1),
            "duracao_min": round(dur_min, 0),
            "duracao_texto": leg["duration"]["text"],
            "preco_uber": round(uber, 2),
            "preco_99": round(uber * 0.85, 2),
            "tarifa_minima": 8.00,
        }
    except Exception as e:
        logger.error(f"calc_route failed: {e}")
        return {"error": str(e)}


async def geocode(endereco: str) -> dict:
    key = _get_key()
    if not key:
        return {"error": "GOOGLE_MAPS_API_KEY not configured"}
    try:
        resp = await _fetch("https://maps.googleapis.com/maps/api/geocode/json", {
            "address": endereco, "key": key, "language": "pt-BR"
        })
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return {"error": data.get("status", "no results")}
        r = data["results"][0]
        loc = r["geometry"]["location"]
        return {
            "endereco_formatado": r.get("formatted_address", endereco),
            "latitude": loc["lat"],
            "longitude": loc["lng"],
            "bairro": next((c["long_name"] for c in r.get("address_components", []) if "sublocality" in c.get("types", [])), ""),
            "cidade": next((c["long_name"] for c in r.get("address_components", []) if "administrative_area_level_2" in c.get("types", [])), ""),
        }
    except Exception as e:
        logger.error(f"geocode failed: {e}")
        return {"error": str(e)}


async def search_places(local: str, tipo: str = "restaurant") -> list:
    key = _get_key()
    if not key:
        return [{"error": "GOOGLE_MAPS_API_KEY not configured"}]
    try:
        geo = await _fetch("https://maps.googleapis.com/maps/api/geocode/json", {"address": local, "key": key})
        geo_data = geo.json()
        if geo_data.get("status") != "OK":
            return [{"error": f"Local nao encontrado: {local}"}]
        loc = geo_data["results"][0]["geometry"]["location"]
        places = await _fetch("https://maps.googleapis.com/maps/api/place/nearbysearch/json", {
            "location": f"{loc['lat']},{loc['lng']}", "radius": 3000, "type": tipo, "key": key, "language": "pt-BR"
        })
        data = places.json()
        results = []
        for r in data.get("results", [])[:5]:
            results.append({
                "nome": r.get("name", ""),
                "endereco": r.get("vicinity", ""),
                "avaliacao": r.get("rating", 0),
                "aberto_agora": "opening_hours" in r and r["opening_hours"].get("open_now", False),
                "tipos": r.get("types", []),
            })
        return results
    except Exception as e:
        logger.error(f"search_places failed: {e}")
        return [{"error": str(e)}]
