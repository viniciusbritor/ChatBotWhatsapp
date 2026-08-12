"""Google Translate tools — traducao e deteccao de idioma (REST API v2).

Usa a Google Cloud Translation API com API Key (sem OAuth). A chave vem de
GOOGLE_TRANSLATE_API_KEY (env var) ou Secret Manager; se nao configurada,
tenta fallback para GOOGLE_MAPS_API_KEY (chave GCP generica).
"""
import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"

_CACHED_KEY: Dict[str, str] = {}


def _get_key() -> str:
    if _CACHED_KEY.get("value"):
        return _CACHED_KEY["value"]
    key = (
        os_env("GOOGLE_TRANSLATE_API_KEY")
        or _secret("GOOGLE_TRANSLATE_API_KEY")
        or os_env("GOOGLE_MAPS_API_KEY")
        or _secret("GOOGLE_MAPS_API_KEY")
        or ""
    ).strip()
    _CACHED_KEY["value"] = key
    return key


def os_env(name: str) -> str:
    import os
    return os.getenv(name, "")


def _secret(name: str) -> str:
    try:
        from core.secrets import get_secret
        return get_secret(name, "") or ""
    except Exception:
        return ""


async def translate_text(text: str, target_lang: str = "pt", source_lang: str = "") -> Dict[str, Any]:
    """Traduz um texto para o idioma alvo (default pt)."""
    key = _get_key()
    if not key:
        return {"error": "GOOGLE_TRANSLATE_API_KEY not configured"}
    try:
        body = {"q": text[:5000], "target": target_lang, "format": "text"}
        if source_lang:
            body["source"] = source_lang
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TRANSLATE_URL,
                params={"key": key},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        translated = (data.get("data", {}).get("translations") or [{}])[0]
        return {
            "texto_traduzido": translated.get("translatedText", ""),
            "idioma_detectado": translated.get("detectedSourceLanguage", source_lang),
            "idioma_alvo": target_lang,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("translate failed exc=%s", exc)
        return {"error": str(exc)[:200]}


async def detect_language(text: str) -> Dict[str, Any]:
    """Detecta o idioma de um texto."""
    key = _get_key()
    if not key:
        return {"error": "GOOGLE_TRANSLATE_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TRANSLATE_URL + "/detect",
                params={"key": key},
                json={"q": text[:5000]},
            )
            resp.raise_for_status()
            data = resp.json()
        detections = (data.get("data", {}).get("detections") or [[]])[0]
        best = detections[0] if detections else {}
        return {
            "idioma": best.get("language", ""),
            "confianca": best.get("confidence", 0),
            "confiavel": bool(best.get("isReliable")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("detect_language failed exc=%s", exc)
        return {"error": str(exc)[:200]}
