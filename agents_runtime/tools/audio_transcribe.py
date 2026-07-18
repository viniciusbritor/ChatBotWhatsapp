"""Audio transcription tool - Whisper self-hosted with background load."""
import os
import asyncio
import logging
import tempfile
import threading
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DOWNLOAD_ROOT = os.getenv("WHISPER_DOWNLOAD_ROOT", "/app/whisper_models")

_model = None
_model_lock = threading.Lock()
_load_started = False


def _ensure_model():
    """Lazy load Whisper model (thread-safe)."""
    global _model, _load_started
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        if _load_started:
            return None

        _load_started = True
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper model {WHISPER_MODEL} (background)...")
            _model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=WHISPER_DOWNLOAD_ROOT,
            )
            logger.info("Whisper model loaded")
            return _model
        except Exception as e:
            logger.error(f"Failed to load Whisper: {e}")
            _load_started = False
            return None


def warm_up():
    """Trigger background load of Whisper model."""
    def _load():
        _ensure_model()
    thread = threading.Thread(target=_load, daemon=True, name="whisper-loader")
    thread.start()
    logger.info("Whisper warm-up started in background")


async def transcribe_from_url(
    audio_key: Dict[str, Any],
    instance: str,
    evo_api_key: str,
    language: str = "pt",
    max_duration_sec: int = 300,
) -> Dict[str, Any]:
    """Download audio from Evolution API and transcribe.

    Args:
        audio_key: WhatsApp key from webhook payload (data.key)
        instance: Evolution instance name
        evo_api_key: Evolution API key for auth header
        language: Language code (default pt)
        max_duration_sec: Max duration to process (default 5min)

    Returns:
        {"text": str, "language": str, "duration_sec": float}
    """
    try:
        url = f"https://evolution.coherenceai.com.br/chat/getMedia/{instance}"
        evo_key = evo_api_key.lstrip("\ufeff") if evo_api_key else ""
        async with httpx.AsyncClient(timeout=60, verify=False) as client:
            resp = await client.post(
                url,
                json={"key": audio_key, "convertToMp4": False},
                headers={"apikey": evo_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            audio_bytes = resp.content
    except Exception as e:
        logger.error(f"Audio download failed: {e}")
        return {"text": "", "error": f"download_failed: {e}"}

    if not audio_bytes:
        return {"text": "", "error": "empty_audio"}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        model = _ensure_model()
        if model is None:
            return {
                "text": "",
                "error": "model_not_loaded",
                "message": "Whisper model not loaded. First audio takes longer.",
            }

        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: model.transcribe(
                tmp_path,
                beam_size=5,
                language=language,
                vad_filter=True,
            ),
        )

        text = " ".join([s.text.strip() for s in segments]).strip()

        return {
            "text": text,
            "language": info.language,
            "duration_sec": info.duration,
        }
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return {"text": "", "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def is_model_loaded() -> bool:
    """Check if Whisper model is loaded."""
    return _model is not None