"""Google Cloud Vision tools — OCR e deteccao de labels (REST API + API Key).

Chave: GOOGLE_VISION_API_KEY (env var) ou Secret Manager; fallback para
GOOGLE_MAPS_API_KEY (chave GCP generica).
"""
import base64
import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"

_CACHED_KEY: Dict[str, str] = {}


def _get_key() -> str:
    if _CACHED_KEY.get("value"):
        return _CACHED_KEY["value"]
    import os
    key = (
        os.getenv("GOOGLE_VISION_API_KEY", "")
        or _secret("GOOGLE_VISION_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY", "")
        or _secret("GOOGLE_MAPS_API_KEY")
        or ""
    ).strip()
    _CACHED_KEY["value"] = key
    return key


def _secret(name: str) -> str:
    try:
        from core.secrets import get_secret
        return get_secret(name, "") or ""
    except Exception:
        return ""


def _to_base64(image: Any) -> str:
    """Aceita bytes, str (base64) ou path de arquivo local."""
    if isinstance(image, bytes):
        return base64.b64encode(image).decode("ascii")
    if isinstance(image, str):
        if image.startswith(("data:", "iVBOR", "/9j/", "UklGR")):
            return image
        if image.startswith(("http://", "https://")):
            return image  # Vision aceita source.imageUri diretamente
        try:
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return image
    return str(image)


async def _annotate(image: Any, features: list, max_results: int = 5) -> Dict[str, Any]:
    key = _get_key()
    if not key:
        return {"error": "GOOGLE_VISION_API_KEY not configured"}
    content = _to_base64(image)
    req_image = {"content": content} if not content.startswith("http") else {"source": {"imageUri": content}}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _VISION_URL,
                params={"key": key},
                json={"requests": [{"image": req_image, "features": features}]},
            )
            resp.raise_for_status()
            data = resp.json()
        responses = data.get("responses") or [{}]
        if responses and "error" in responses[0]:
            return {"error": responses[0]["error"].get("message", "vision_error")}
        return responses[0] if responses else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("vision annotate failed exc=%s", exc)
        return {"error": str(exc)[:200]}


async def ocr_image(image: Any) -> Dict[str, Any]:
    """Extrai texto de uma imagem (OCR). Aceita bytes, base64, URL ou path."""
    data = await _annotate(image, [{"type": "TEXT_DETECTION", "maxResults": 1}])
    if "error" in data:
        return data
    annotations = data.get("textAnnotations") or []
    return {
        "texto": annotations[0].get("description", "") if annotations else "",
        "encontrou_texto": bool(annotations),
    }


async def detect_labels(image: Any, max_results: int = 5) -> Dict[str, Any]:
    """Identifica objetos/categorias em uma imagem."""
    data = await _annotate(image, [{"type": "LABEL_DETECTION", "maxResults": max_results}])
    if "error" in data:
        return data
    labels = data.get("labelAnnotations") or []
    return {
        "labels": [
            {
                "descricao": label.get("description", ""),
                "confianca": round(label.get("score", 0), 3),
            }
            for label in labels
        ],
        "count": len(labels),
    }
