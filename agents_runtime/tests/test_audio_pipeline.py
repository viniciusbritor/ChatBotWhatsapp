"""Testes do core.audio_pipeline (STT real no caminho de producao)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio_pipeline import transcribe_envelope_audio


@pytest.mark.asyncio
async def test_sem_audio_retorna_transcript_none():
    result = await transcribe_envelope_audio({"extra": {"has_audio": False}})
    assert result == {"transcript": None}


@pytest.mark.asyncio
async def test_audio_url_transcreve_e_mascara():
    async def fake_transcribe(url, mime, instance=None):
        return {"transcript": "meu email e fulano@exemplo.com", "provider": "minimax:MiniMax-M3", "reason": ""}

    payload = {"instance": "Jennifer", "extra": {"has_audio": True, "audio_url": "https://evolution.coherenceai.com.br/chat/getMedia/Jennifer?messageId=x"}}
    with patch("core.audio_transcribe.transcribe_url", side_effect=fake_transcribe):
        result = await transcribe_envelope_audio(payload)
    assert result["provider"] == "minimax:MiniMax-M3"
    assert result["source"] == "url"
    assert "fulano@exemplo.com" not in result["transcript"]  # PII mascarado


@pytest.mark.asyncio
async def test_audio_base64_usa_transcribe_base64():
    async def fake_transcribe(b64, mime, instance=None):
        return {"transcript": "ola", "provider": "gemini:gemini-2.5-flash", "reason": "fallback"}

    payload = {"extra": {"has_audio": True, "audio_base64": "AAAA", "audio_mimetype": "audio/ogg"}}
    with patch("core.audio_transcribe.transcribe_base64", side_effect=fake_transcribe):
        result = await transcribe_envelope_audio(payload)
    assert result["transcript"] == "ola"
    assert result["source"] == "base64"


@pytest.mark.asyncio
async def test_audio_sem_payload_retorna_erro():
    payload = {"extra": {"has_audio": True}}
    result = await transcribe_envelope_audio(payload)
    assert result == {"error": "audio_payload_missing"}


@pytest.mark.asyncio
async def test_falha_seguranca_retorna_codigo():
    async def fake_transcribe(url, mime, instance=None):
        raise ValueError("audio_url_host_not_allowed")

    payload = {"extra": {"has_audio": True, "audio_url": "https://evil.example/x.ogg"}}
    with patch("core.audio_transcribe.transcribe_url", side_effect=fake_transcribe):
        result = await transcribe_envelope_audio(payload)
    assert result == {"error": "audio_url_host_not_allowed"}


@pytest.mark.asyncio
async def test_falha_generica_retorna_unavailable():
    async def fake_transcribe(url, mime, instance=None):
        raise ConnectionError("boom")

    payload = {"extra": {"has_audio": True, "audio_url": "https://evolution.coherenceai.com.br/x.ogg"}}
    with patch("core.audio_transcribe.transcribe_url", side_effect=fake_transcribe):
        result = await transcribe_envelope_audio(payload)
    assert result == {"error": "unavailable:ConnectionError"}
