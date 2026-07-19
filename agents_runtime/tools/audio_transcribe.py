import asyncio
import base64
import ipaddress
import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DOWNLOAD_ROOT = os.getenv("WHISPER_DOWNLOAD_ROOT", "/app/whisper_models")
AUDIO_MAX_BYTES = int(os.getenv("AUDIO_MAX_BYTES", str(25 * 1024 * 1024)))
AUDIO_MAX_DURATION_SEC = int(os.getenv("AUDIO_MAX_DURATION_SEC", "300"))
AUDIO_DOWNLOAD_TIMEOUT_SEC = float(os.getenv("AUDIO_DOWNLOAD_TIMEOUT_SEC", "30"))
AUDIO_URL_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv("AUDIO_URL_ALLOWED_HOSTS", "evolution.coherenceai.com.br").split(",")
    if host.strip()
}
ALLOWED_MIME_TYPES: Dict[str, str] = {
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
_model = None
_model_lock = threading.RLock()
_warmup_thread: Optional[threading.Thread] = None


class AudioValidationError(ValueError):
    pass


class AudioProcessingError(RuntimeError):
    pass


def _normalize_mimetype(mimetype: str) -> str:
    return str(mimetype or "audio/ogg").split(";", 1)[0].strip().lower()


def _validate_mimetype(mimetype: str) -> str:
    normalized = _normalize_mimetype(mimetype)
    if normalized not in ALLOWED_MIME_TYPES:
        raise AudioValidationError("audio_mimetype_not_allowed")
    return normalized


def _validate_size(audio_bytes: bytes) -> None:
    if not audio_bytes:
        raise AudioValidationError("audio_empty")
    if len(audio_bytes) > AUDIO_MAX_BYTES:
        raise AudioValidationError("audio_too_large")


def _decode_base64(audio_b64: str) -> bytes:
    value = str(audio_b64 or "").strip()
    if value.startswith("data:"):
        _, _, value = value.partition(",")
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise AudioValidationError("audio_base64_invalid") from exc
    _validate_size(decoded)
    return decoded


def _host_allowed(hostname: str) -> bool:
    normalized = str(hostname or "").lower().rstrip(".")
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in AUDIO_URL_ALLOWED_HOSTS
    )


def _validate_public_host(hostname: str) -> None:
    if not _host_allowed(hostname):
        raise AudioValidationError("audio_url_host_not_allowed")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except Exception as exc:
        raise AudioValidationError("audio_url_dns_failed") from exc
    if not addresses:
        raise AudioValidationError("audio_url_dns_failed")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise AudioValidationError("audio_url_private_address")


def _validate_audio_url(audio_url: str) -> str:
    parsed = urlparse(str(audio_url or ""))
    if parsed.scheme.lower() != "https":
        raise AudioValidationError("audio_url_https_required")
    if not parsed.hostname or parsed.username or parsed.password:
        raise AudioValidationError("audio_url_invalid")
    _validate_public_host(parsed.hostname)
    return parsed.geturl()


async def _download_audio(audio_url: str) -> bytes:
    validated_url = await asyncio.to_thread(_validate_audio_url, audio_url)
    headers: Dict[str, str] = {}
    evolution_key = os.getenv("EVOLUTION_API_KEY") or get_secret("EVOLUTION_API_KEY")
    if evolution_key:
        headers["apikey"] = evolution_key.strip().lstrip("\ufeff")
    timeout = httpx.Timeout(AUDIO_DOWNLOAD_TIMEOUT_SEC)
    chunks = []
    size = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", validated_url, headers=headers) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                raise AudioValidationError("audio_url_redirect_rejected")
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > AUDIO_MAX_BYTES:
                raise AudioValidationError("audio_too_large")
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > AUDIO_MAX_BYTES:
                    raise AudioValidationError("audio_too_large")
                chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    _validate_size(audio_bytes)
    return audio_bytes


def _probe_duration(file_path: str) -> float:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            file_path,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if process.returncode != 0:
        raise AudioValidationError("audio_invalid_or_unsupported")
    try:
        duration = float(json.loads(process.stdout)["format"]["duration"])
    except Exception as exc:
        raise AudioValidationError("audio_duration_unavailable") from exc
    if duration <= 0:
        raise AudioValidationError("audio_duration_invalid")
    if duration > AUDIO_MAX_DURATION_SEC:
        raise AudioValidationError("audio_too_long")
    return duration


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            Path(WHISPER_DOWNLOAD_ROOT).mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=WHISPER_DOWNLOAD_ROOT,
            )
            logger.info(
                "Whisper loaded: model=%s device=%s compute_type=%s",
                WHISPER_MODEL,
                WHISPER_DEVICE,
                WHISPER_COMPUTE_TYPE,
            )
        return _model


def warm_up() -> None:
    global _warmup_thread
    with _model_lock:
        if _model is not None or (
            _warmup_thread is not None and _warmup_thread.is_alive()
        ):
            return
        _warmup_thread = threading.Thread(
            target=_warm_up_model, daemon=True, name="whisper-warmup"
        )
        _warmup_thread.start()


def _warm_up_model() -> None:
    try:
        _get_model()
    except Exception as exc:
        logger.error("Whisper warm-up failed: %s", exc)


def _transcribe_file(file_path: str) -> str:
    _probe_duration(file_path)
    model = _get_model()
    segments, _ = model.transcribe(
        file_path,
        language="pt",
        vad_filter=True,
        beam_size=5,
    )
    text = " ".join(
        segment.text.strip() for segment in segments if segment.text.strip()
    ).strip()
    if not text:
        raise AudioProcessingError("audio_transcription_empty")
    return text


async def transcribe_bytes(audio_bytes: bytes, mimetype: str = "audio/ogg") -> str:
    normalized_mimetype = _validate_mimetype(mimetype)
    _validate_size(audio_bytes)
    suffix = ALLOWED_MIME_TYPES[normalized_mimetype]
    file_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(audio_bytes)
            file_path = temporary.name
        return await asyncio.to_thread(_transcribe_file, file_path)
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass


async def transcribe_base64(audio_b64: str, mimetype: str = "audio/ogg") -> str:
    _validate_mimetype(mimetype)
    audio_bytes = _decode_base64(audio_b64)
    return await transcribe_bytes(audio_bytes, mimetype)


async def transcribe_url(audio_url: str, mimetype: str = "audio/ogg") -> str:
    _validate_mimetype(mimetype)
    audio_bytes = await _download_audio(audio_url)
    return await transcribe_bytes(audio_bytes, mimetype)
