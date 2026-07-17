"""Whisper Worker - GPU L4 transcription via Cloud Run Job.
Receives HTTP POST with audio_url, transcribes with faster-whisper + CUDA,
sends text result back to agents-runtime /chat.
"""
import os
import sys
import json
import logging
import tempfile
import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}')
logger = logging.getLogger("whisper_worker")

AGENTS_RUNTIME_URL = os.getenv("AGENTS_RUNTIME_URL", "")
AGENTS_RUNTIME_SA_TOKEN = os.getenv("AGENTS_RUNTIME_SA_TOKEN", "")
EVO_API_KEY = os.getenv("EVO_API_KEY", "")

MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")


async def download_audio(audio_url: str, api_key: str) -> bytes:
    """Download audio from Evolution API."""
    headers = {"apikey": api_key}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(audio_url, headers=headers)
        resp.raise_for_status()
        return resp.content


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio using faster-whisper with CUDA."""
    from faster_whisper import WhisperModel
    import asyncio

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = WhisperModel(MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
        segments, _ = model.transcribe(tmp_path, beam_size=5, language="pt")
        text = " ".join(s.text for s in segments)
        return text.strip() or "[audio sem fala detectada]"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def send_transcription(phone: str, text: str, instance: str, sender_name: str):
    """Send transcribed text to agents-runtime /chat."""
    if not AGENTS_RUNTIME_URL or not AGENTS_RUNTIME_SA_TOKEN:
        logger.error("agents_runtime not configured")
        return

    url = f"{AGENTS_RUNTIME_URL.rstrip('/')}/chat"
    payload = {
        "instance": instance,
        "phone": phone,
        "text": text,
        "sender_name": sender_name,
        "extra": {"has_audio": False, "was_transcribed": True},
    }
    headers = {
        "Authorization": f"Bearer {AGENTS_RUNTIME_SA_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        logger.info(f"Transcription sent to agents-runtime: {resp.status_code}")


async def main():
    """Entry point for Cloud Run Job."""
    import asyncio

    data = {}
    try:
        input_data = sys.stdin.read()
        if input_data.strip():
            data = json.loads(input_data)
    except Exception:
        pass

    audio_url = data.get("audio_url") or os.getenv("AUDIO_URL", "")
    phone = data.get("phone") or os.getenv("PHONE", "")
    instance = data.get("instance") or os.getenv("INSTANCE", "Jennifer")
    sender_name = data.get("sender_name") or os.getenv("SENDER_NAME", "user")

    if not audio_url or not phone:
        logger.error("audio_url and phone required")
        return

    logger.info(f"Downloading audio for {phone}: {audio_url[:80]}...")
    audio_bytes = await download_audio(audio_url, EVO_API_KEY)
    logger.info(f"Audio downloaded: {len(audio_bytes)} bytes")

    text = await transcribe(audio_bytes)
    logger.info(f"Transcription: {text[:100]}")

    await send_transcription(phone, text, instance, sender_name)

    result = {"ok": True, "phone": phone, "text_preview": text[:100]}
    logger.info(json.dumps(result))
    return result


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
