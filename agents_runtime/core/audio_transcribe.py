"""Audio transcription: OpenAI Whisper-1 -> Gemini 2.5 Flash cascade.

Audio is forwarded to OpenAI's ``/v1/audio/transcriptions`` (whisper-1)
and, when that fails, to Gemini 2.5 Flash's generateContent audio input.
Raw audio bytes are never persisted; downloads are streamed and expire on
the Evolution CDN within minutes.

Public API:
- ``transcribe_bytes(audio_bytes, mimetype, instance=...)``
- ``transcribe_base64(audio_b64, mimetype, instance=...)``
- ``transcribe_url(audio_url, mimetype, instance=...)``
- ``fallback_stats()`` -> counters for FinOps observability.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import os
import socket
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)

GEMINI_STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
GEMINI_STT_ENDPOINT = f"{GEMINI_BASE_URL}/v1beta/models/{GEMINI_STT_MODEL}:generateContent"

AUDIO_MAX_BYTES = int(os.getenv("AUDIO_MAX_BYTES", str(25 * 1024 * 1024)))
AUDIO_MAX_DURATION_SEC = int(os.getenv("AUDIO_MAX_DURATION_SEC", "300"))
AUDIO_DOWNLOAD_TIMEOUT_SEC = float(os.getenv("AUDIO_DOWNLOAD_TIMEOUT_SEC", "30"))
AUDIO_URL_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv(
        "AUDIO_URL_ALLOWED_HOSTS", "evolution.coherenceai.com.br"
    ).split(",")
    if host.strip()
}
ALLOWED_MIME_TYPES = {
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
}

_fallback_counter: Dict[str, int] = {}
_fallback_counter_lock = asyncio.Lock()


def _audio_extension(mimetype: str) -> str:
    return ALLOWED_MIME_TYPES.get(mimetype.lower(), ".ogg")


def _normalize_mimetype(mimetype: str) -> str:
    return str(mimetype or "audio/ogg").split(";", 1)[0].strip().lower()


def _validate_mimetype(mimetype: str) -> str:
    normalized = _normalize_mimetype(mimetype)
    if normalized not in ALLOWED_MIME_TYPES:
        raise ValueError(f"audio_mimetype_not_allowed: {normalized}")
    return normalized


def _host_allowed(hostname: str) -> bool:
    normalized = str(hostname or "").lower().rstrip(".")
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in AUDIO_URL_ALLOWED_HOSTS
    )


def _validate_public_host(hostname: str) -> None:
    if not _host_allowed(hostname):
        raise ValueError("audio_url_host_not_allowed")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except Exception as exc:
        raise ValueError("audio_url_dns_failed") from exc
    if not addresses:
        raise ValueError("audio_url_dns_failed")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("audio_url_private_address")


def _validate_audio_url(audio_url: str) -> str:
    parsed = urlparse(str(audio_url or ""))
    if parsed.scheme.lower() != "https":
        raise ValueError("audio_url_https_required")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("audio_url_invalid")
    _validate_public_host(parsed.hostname)
    return parsed.geturl()


async def _download_audio(audio_url: str) -> bytes:
    validated_url = await asyncio.to_thread(_validate_audio_url, audio_url)
    evolution_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY")
    headers: Dict[str, str] = {}
    if evolution_key:
        headers["apikey"] = evolution_key.strip().lstrip("\ufeff")
    timeout = httpx.Timeout(AUDIO_DOWNLOAD_TIMEOUT_SEC)
    chunks = []
    size = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", validated_url, headers=headers) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                raise ValueError("audio_url_redirect_rejected")
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > AUDIO_MAX_BYTES:
                raise ValueError("audio_too_large")
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > AUDIO_MAX_BYTES:
                    raise ValueError("audio_too_large")
                chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    if not audio_bytes:
        raise ValueError("audio_empty")
    return audio_bytes


def _transcribe_with_openai(audio_bytes: bytes, mimetype: str) -> str:
    """Primary STT via OpenAI Whisper-1."""
    api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("openai_stt_key_not_configured")
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key.strip().lstrip('\ufeff')}",
    }
    files = {
        "file": (
            f"audio{_audio_extension(mimetype)}",
            audio_bytes,
            mimetype,
        ),
    }
    data = {
        "model": "whisper-1",
        "response_format": "json",
    }
    response = httpx.post(url, headers=headers, files=files, data=data, timeout=60)
    if response.status_code == 429:
        raise RuntimeError("openai_stt_quota_exceeded")
    if response.status_code == 401:
        raise RuntimeError("openai_stt_auth_failed")
    if response.status_code != 200:
        logger.error(
            "openai_stt_http_error status=%d response=%s",
            response.status_code,
            response.text[:500],
        )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("text") or ""
    if not text:
        raise RuntimeError("openai_stt_empty_response")
    return str(text).strip()


GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")


def _transcribe_with_groq(audio_bytes: bytes, mimetype: str) -> str:
    """Primary 100% Free STT via Groq Cloud (Whisper Large v3 Turbo)."""
    api_key = os.getenv("GROQ_API_KEY") or get_secret("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("groq_stt_key_not_configured")
    url = f"{GROQ_BASE_URL.rstrip('/')}/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key.strip().lstrip('\ufeff')}",
    }
    files = {
        "file": (
            f"audio{_audio_extension(mimetype)}",
            audio_bytes,
            mimetype,
        ),
    }
    data = {
        "model": GROQ_STT_MODEL,
        "response_format": "json",
        "language": "pt",
    }
    response = httpx.post(url, headers=headers, files=files, data=data, timeout=30)
    if response.status_code == 429:
        raise RuntimeError("groq_stt_quota_exceeded")
    if response.status_code == 401:
        raise RuntimeError("groq_stt_auth_failed")
    if response.status_code != 200:
        logger.error(
            "groq_stt_http_error status=%d response=%s",
            response.status_code,
            response.text[:500],
        )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("text") or ""
    if not text:
        raise RuntimeError("groq_stt_empty_response")
    return str(text).strip()


def _transcribe_with_gemini(audio_bytes: bytes, mimetype: str) -> str:
    """Fallback STT via Gemini 2.5 Flash."""
    api_key = os.getenv("GEMINI_API_KEY") or get_secret("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("gemini_stt_key_not_configured")
    url = f"{GEMINI_BASE_URL.rstrip('/')}/v1beta/models/{GEMINI_STT_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": api_key.strip().lstrip("\ufeff"),
        "Content-Type": "application/json",
    }
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mimetype,
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                    {
                        "text": "Transcreva este audio em portugues brasileiro. Responda somente com a transcricao."
                    },
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
    }
    response = httpx.post(url, headers=headers, json=body, timeout=120)
    if response.status_code == 429:
        raise RuntimeError("gemini_stt_quota_exceeded")
    if response.status_code == 401:
        raise RuntimeError("gemini_stt_auth_failed")
    if response.status_code != 200:
        logger.error(
            "gemini_stt_http_error status=%d response=%s",
            response.status_code,
            response.text[:500],
        )
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("gemini_stt_empty_response")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_chunks = [p.get("text", "") for p in parts if p.get("text")]
    if not text_chunks:
        raise RuntimeError("gemini_stt_empty_response")
    return "".join(text_chunks).strip()


def _transcribe(audio_bytes: bytes, mimetype: str, instance: str) -> Dict[str, Any]:
    """Cascade: Groq (Whisper Large v3) -> OpenAI Whisper-1 -> Gemini 2.5 Flash."""
    errors = []
    primary_error = None

    # 1. Groq Whisper (100% Free Tier)
    try:
        text = _transcribe_with_groq(audio_bytes, mimetype)
        logger.info("groq_stt_success_finops_zero_cost model=%s bytes=%d", GROQ_STT_MODEL, len(audio_bytes))
        return {
            "transcript": text,
            "provider": f"groq:{GROQ_STT_MODEL}",
            "reason": "",
        }
    except Exception as exc:  # noqa: BLE001
        if primary_error is None:
            primary_error = exc
        errors.append(f"groq_{type(exc).__name__}")
        logger.warning("groq_stt_failed error=%s", type(exc).__name__)

    # 2. OpenAI Whisper-1
    try:
        text = _transcribe_with_openai(audio_bytes, mimetype)
        return {
            "transcript": text,
            "provider": "openai:whisper-1",
            "reason": ";".join(errors),
        }
    except Exception as exc:  # noqa: BLE001
        if primary_error is None:
            primary_error = exc
        errors.append(f"openai_{type(exc).__name__}")
        logger.warning("openai_stt_failed error=%s", type(exc).__name__)

    # 3. Fallback: Gemini 2.5 Flash
    try:
        text = _transcribe_with_gemini(audio_bytes, mimetype)
        return {
            "transcript": text,
            "provider": f"gemini:{GEMINI_STT_MODEL}",
            "reason": ";".join(errors),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "audio_stt_all_failed errors=%s gemini=%s",
            errors,
            type(exc).__name__,
        )
        raise primary_error or exc


async def transcribe_bytes(
    audio_bytes: bytes,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> Dict[str, Any]:
    """Transcribe raw audio bytes. Cascade: OpenAI Whisper-1 -> Gemini 2.5 Flash."""
    if not audio_bytes:
        return {"transcript": "", "provider": "none", "reason": "empty"}
    if len(audio_bytes) > AUDIO_MAX_BYTES:
        return {"transcript": "", "provider": "none", "reason": "too_large"}
    normalized = _validate_mimetype(mimetype)
    return await asyncio.to_thread(_transcribe, audio_bytes, normalized, instance)


async def transcribe_base64(
    audio_b64: str,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> Dict[str, Any]:
    normalized = _validate_mimetype(mimetype)
    audio_bytes = base64.b64decode(audio_b64, validate=True)
    return await transcribe_bytes(audio_bytes, normalized, instance)


async def transcribe_url(
    audio_url: str,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> Dict[str, Any]:
    normalized = _validate_mimetype(mimetype)
    audio_bytes = await _download_audio(audio_url)
    return await transcribe_bytes(audio_bytes, normalized, instance)


def fallback_stats() -> Dict[str, Any]:
    return {
        "primary": "openai:whisper-1",
        "fallback": GEMINI_STT_MODEL,
        "max_bytes": AUDIO_MAX_BYTES,
        "max_duration_sec": AUDIO_MAX_DURATION_SEC,
        "allowed_hosts": sorted(AUDIO_URL_ALLOWED_HOSTS),
    }


# Public API alias preserved for callers expecting a string-only return.
async def transcribe_bytes_str(
    audio_bytes: bytes,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> str:
    return (await transcribe_bytes(audio_bytes, mimetype, instance))["transcript"]


async def transcribe_base64_str(
    audio_b64: str,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> str:
    return (await transcribe_base64(audio_b64, mimetype, instance))["transcript"]


async def transcribe_url_str(
    audio_url: str,
    mimetype: str = "audio/ogg",
    instance: str = "",
) -> str:
    return (await transcribe_url(audio_url, mimetype, instance))["transcript"]
