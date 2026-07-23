"""Whisper transcription with controlled Gemini 2.5 Flash fallback.

The Whisper model stays as the default local engine. The fallback is only
triggered when Whisper returns a transient failure (timeout, OOM, runtime
error). Consent is mandatory: callers must opt-in via ``STT_FALLBACK_CONSENT``
for the instance or pass ``consent=True`` explicitly. Audio bytes are never
persisted; the raw payload is sent to Gemini over HTTPS, the response is
masked, and a counter is incremented for FinOps observability.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from core.masker import mask_pii
from core.secrets import get_secret

logger = logging.getLogger(__name__)

STT_PRIMARY = "whisper-local"
STT_FALLBACK = "gemini-2.5-flash"

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
DAILY_FALLBACK_LIMIT = int(os.getenv("STT_FALLBACK_DAILY_LIMIT", "20"))

_fallback_counter: Dict[str, int] = {}
_fallback_counter_lock = asyncio.Lock()


def _fallback_consent_enabled() -> bool:
    return os.getenv("STT_FALLBACK_CONSENT", "false").lower() in {"1", "true", "yes"}


def _incremented_counter() -> int:
    today = time.strftime("%Y-%m-%d")
    return _fallback_counter.get(today, 0)


async def _increment_counter() -> int:
    today = time.strftime("%Y-%m-%d")
    async with _fallback_counter_lock:
        _fallback_counter[today] = _fallback_counter.get(today, 0) + 1
        return _fallback_counter[today]


def _gemini_api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY")
        or get_secret("GEMINI_API_KEY")
        or ""
    ).strip().lstrip("\ufeff")


async def _transcribe_with_gemini(audio_bytes: bytes, mimetype: str) -> str:
    """Send the audio to Gemini 2.5 Flash and return the transcript."""
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("gemini_api_key_missing")
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mimetype,
                            "data": encoded,
                        }
                    },
                    {
                        "text": "Transcreva este audio em portugues brasileiro. Responda somente com a transcricao."
                    },
                ]
            }
        ]
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GEMINI_ENDPOINT}?key={api_key}",
            json=body,
            headers={"Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"gemini_http_{response.status_code}")
    payload = response.json()
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("gemini_response_invalid") from exc
    return str(text).strip()


async def transcribe_with_fallback(
    primary,
    *,
    audio_bytes: bytes,
    mimetype: str,
    instance: str,
    consent: Optional[bool] = None,
) -> Dict[str, Any]:
    """Try Whisper first; on transient failure, call Gemini if consent + budget allow.

    Returns a dict with ``transcript``, ``provider`` and ``reason`` (when the
    fallback path was used). ``primary`` must be an awaitable that returns the
    local transcript string.
    """
    started = time.monotonic()
    try:
        transcript = await primary()
        return {
            "transcript": transcript,
            "provider": STT_PRIMARY,
            "reason": "",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as primary_exc:  # noqa: BLE001
        fallback_allowed = bool(consent) or _fallback_consent_enabled()
        if not fallback_allowed:
            logger.warning(
                "audio_fallback_skipped reason=no_consent error=%s",
                type(primary_exc).__name__,
            )
            raise
        counter = _incremented_counter()
        if counter >= DAILY_FALLBACK_LIMIT:
            logger.warning(
                "audio_fallback_skipped reason=daily_limit counter=%s",
                counter,
            )
            raise
        try:
            transcript = await _transcribe_with_gemini(audio_bytes, mimetype)
        except Exception as gemini_exc:  # noqa: BLE001
            logger.error(
                "audio_fallback_failed primary_error=%s gemini_error=%s",
                type(primary_exc).__name__,
                type(gemini_exc).__name__,
            )
            raise primary_exc
        await _increment_counter()
        masked = mask_pii(transcript)
        logger.info(
            "audio_fallback_used provider=%s instance=%s counter=%s primary_error=%s",
            STT_FALLBACK,
            instance,
            counter + 1,
            type(primary_exc).__name__,
        )
        return {
            "transcript": masked,
            "provider": STT_FALLBACK,
            "reason": f"whisper_{type(primary_exc).__name__}",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


def fallback_stats() -> Dict[str, Any]:
    today = time.strftime("%Y-%m-%d")
    return {
        "today": today,
        "count": _fallback_counter.get(today, 0),
        "daily_limit": DAILY_FALLBACK_LIMIT,
        "consent_enabled": _fallback_consent_enabled(),
        "primary": STT_PRIMARY,
        "fallback": STT_FALLBACK,
    }
