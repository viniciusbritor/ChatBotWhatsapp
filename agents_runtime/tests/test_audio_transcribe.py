"""Tests for the audio transcription cascade (MiniMax -> Gemini fallback)."""
import base64
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMimetypeValidation:
    def test_accepts_ogg(self):
        from core.audio_transcribe import _validate_mimetype

        assert _validate_mimetype("audio/ogg") == "audio/ogg"

    def test_accepts_mp3_with_charset(self):
        from core.audio_transcribe import _validate_mimetype

        assert _validate_mimetype("audio/mpeg; codecs=mp3") == "audio/mpeg"

    def test_rejects_unknown_mimetype(self):
        from core.audio_transcribe import _validate_mimetype

        with pytest.raises(ValueError, match="audio_mimetype_not_allowed"):
            _validate_mimetype("application/octet-stream")

    def test_rejects_video_mimetype(self):
        from core.audio_transcribe import _validate_mimetype

        with pytest.raises(ValueError, match="audio_mimetype_not_allowed"):
            _validate_mimetype("video/mp4")

    def test_normalizes_uppercase(self):
        from core.audio_transcribe import _validate_mimetype

        assert _validate_mimetype("AUDIO/OGG") == "audio/ogg"


class TestBase64Decode:
    def test_accepts_valid_base64(self):
        from core.audio_transcribe import transcribe_base64

        audio_bytes = b"\x00\x01\x02hello" * 100
        b64 = base64.b64encode(audio_bytes).decode("ascii")

        async def fake_transcribe(audio, mime, instance):
            return {"transcript": "hello world", "provider": "minimax", "reason": ""}

        with patch("core.audio_transcribe.transcribe_bytes", side_effect=fake_transcribe):
            import asyncio
            result = asyncio.run(transcribe_base64(b64, "audio/ogg", "Jennifer"))

        assert result["transcript"] == "hello world"

    def test_rejects_invalid_base64(self):
        from core.audio_transcribe import transcribe_base64

        with pytest.raises(Exception):
            import asyncio
            asyncio.run(transcribe_base64("not-valid-base64!@#", "audio/ogg", "Jennifer"))

    def test_accepts_minimax_format(self):
        from core.audio_transcribe import transcribe_base64

        audio_bytes = b"\xff\xfe\xfd" * 50
        b64 = base64.b64encode(audio_bytes).decode("ascii")

        async def fake_transcribe(audio, mime, instance):
            assert len(audio) == 150
            return {"transcript": "ok", "provider": "minimax", "reason": ""}

        with patch("core.audio_transcribe.transcribe_bytes", side_effect=fake_transcribe):
            import asyncio
            asyncio.run(transcribe_base64(b64, "audio/mp3", "Jennifer"))


class TestSizeValidation:
    def test_rejects_oversized_payload(self):
        from core.audio_transcribe import transcribe_bytes

        audio_bytes = b"\x00" * (30 * 1024 * 1024)
        import asyncio
        result = asyncio.run(transcribe_bytes(audio_bytes, "audio/ogg", "Jennifer"))
        assert result["reason"] == "too_large"
        assert result["provider"] == "none"

    def test_accepts_normal_payload(self):
        from core.audio_transcribe import transcribe_bytes

        def fake_transcribe(audio, mime, instance):
            return {"transcript": "ok", "provider": "minimax", "reason": ""}

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("core.audio_transcribe._transcribe", side_effect=fake_transcribe):
            with patch("core.audio_transcribe.asyncio.to_thread", side_effect=fake_to_thread):
                import asyncio
                result = asyncio.run(transcribe_bytes(b"\x00" * 100, "audio/ogg", "Jennifer"))
        assert result["transcript"] == "ok"

    def test_rejects_empty_payload(self):
        from core.audio_transcribe import transcribe_bytes

        import asyncio
        result = asyncio.run(transcribe_bytes(b"", "audio/ogg", "Jennifer"))
        assert result["reason"] == "empty"


class TestURLValidation:
    def test_requires_https(self):
        from core.audio_transcribe import _validate_audio_url

        with pytest.raises(ValueError, match="audio_url_https_required"):
            _validate_audio_url("http://evolution.coherenceai.com.br/audio.ogg")

    def test_rejects_userinfo(self):
        from core.audio_transcribe import _validate_audio_url

        with pytest.raises(ValueError, match="audio_url_invalid"):
            _validate_audio_url("https://user:pass@evolution.coherenceai.com.br/audio.ogg")

    def test_rejects_unknown_host(self, monkeypatch):
        from core.audio_transcribe import _validate_audio_url

        monkeypatch.setattr(
            "core.audio_transcribe._validate_public_host",
            lambda host: (_ for _ in ()).throw(ValueError("audio_url_host_not_allowed")),
        )
        with pytest.raises(ValueError):
            _validate_audio_url("https://unknown-host.example/audio.ogg")

    def test_accepts_allowlisted_host(self, monkeypatch):
        from core.audio_transcribe import _validate_audio_url

        monkeypatch.setattr(
            "core.audio_transcribe._validate_public_host", lambda host: None
        )
        url = _validate_audio_url("https://evolution.coherenceai.com.br/audio.ogg")
        assert url.startswith("https://evolution.coherenceai.com.br")


class TestPublicHostCheck:
    def test_allows_evolution_hostname(self, monkeypatch):
        from core import audio_transcribe

        monkeypatch.setattr(
            audio_transcribe,
            "AUDIO_URL_ALLOWED_HOSTS",
            {"evolution.coherenceai.com.br"},
        )
        monkeypatch.setattr(
            "socket.getaddrinfo",
            lambda *a, **kw: [(None, None, None, None, ("8.8.8.8", 443))],
        )
        audio_transcribe._validate_public_host("evolution.coherenceai.com.br")

    def test_rejects_localhost(self):
        from core import audio_transcribe

        monkeypatch_holder = audio_transcribe.AUDIO_URL_ALLOWED_HOSTS | {"localhost"}
        with patch.object(audio_transcribe, "AUDIO_URL_ALLOWED_HOSTS", monkeypatch_holder):
            with patch(
                "socket.getaddrinfo",
                return_value=[(None, None, None, None, ("127.0.0.1", 0))],
            ):
                with pytest.raises(ValueError, match="audio_url_private_address"):
                    audio_transcribe._validate_public_host("localhost")

    def test_rejects_private_ip(self):
        from core import audio_transcribe

        monkeypatch_holder = audio_transcribe.AUDIO_URL_ALLOWED_HOSTS | {"any-host.example"}
        with patch.object(audio_transcribe, "AUDIO_URL_ALLOWED_HOSTS", monkeypatch_holder):
            with patch(
                "socket.getaddrinfo",
                return_value=[(None, None, None, None, ("192.168.1.1", 0))],
            ):
                with pytest.raises(ValueError, match="audio_url_private_address"):
                    audio_transcribe._validate_public_host("any-host.example")


class TestCascadeTranscribe:
    def test_returns_minimax_result_when_successful(self):
        from core.audio_transcribe import _transcribe

        def fake_minimax(*args, **kwargs):
            return "hello world"

        with patch("core.audio_transcribe._transcribe_with_minimax", side_effect=fake_minimax):
            result = _transcribe(b"audio", "audio/ogg", "Jennifer")
        assert result["transcript"] == "hello world"
        assert result["provider"].startswith("minimax:")
        assert result["reason"] == ""

    def test_falls_back_to_gemini_when_minimax_fails(self):
        from core.audio_transcribe import _transcribe

        def fake_minimax(*args, **kwargs):
            raise RuntimeError("minimax_stt_failed")

        def fake_gemini(*args, **kwargs):
            return "fallback transcript"

        with patch("core.audio_transcribe._transcribe_with_minimax", side_effect=fake_minimax):
            with patch("core.audio_transcribe._transcribe_with_gemini", side_effect=fake_gemini):
                result = _transcribe(b"audio", "audio/ogg", "Jennifer")
        assert result["transcript"] == "fallback transcript"
        assert result["provider"].startswith("gemini:")
        assert "minimax_" in result["reason"]

    def test_raises_when_both_providers_fail(self):
        from core.audio_transcribe import _transcribe

        def fake_minimax(*args, **kwargs):
            raise RuntimeError("minimax_stt_failed")

        def fake_gemini(*args, **kwargs):
            raise RuntimeError("gemini_stt_failed")

        with patch("core.audio_transcribe._transcribe_with_minimax", side_effect=fake_minimax):
            with patch("core.audio_transcribe._transcribe_with_gemini", side_effect=fake_gemini):
                with pytest.raises(RuntimeError, match="minimax_stt_failed"):
                    _transcribe(b"audio", "audio/ogg", "Jennifer")

    def test_falls_back_to_gemini_when_minimax_returns_empty(self):
        from core.audio_transcribe import _transcribe

        def fake_minimax(*args, **kwargs):
            raise RuntimeError("minimax_empty_response")

        def fake_gemini(*args, **kwargs):
            return "recovered transcript"

        with patch("core.audio_transcribe._transcribe_with_minimax", side_effect=fake_minimax):
            with patch("core.audio_transcribe._transcribe_with_gemini", side_effect=fake_gemini):
                result = _transcribe(b"audio", "audio/ogg", "Jennifer")
        assert result["transcript"] == "recovered transcript"


class TestGeminiFallbackConfiguration:
    def test_gemini_endpoint_uses_generativelanguage(self, monkeypatch):
        monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        monkeypatch.setenv("GEMINI_STT_MODEL", "gemini-2.5-flash")
        import importlib
        import core.audio_transcribe as at
        importlib.reload(at)
        assert at.GEMINI_STT_ENDPOINT.startswith("https://generativelanguage.googleapis.com")
        assert "gemini-2.5-flash" in at.GEMINI_STT_ENDPOINT

    def test_fallback_stats_exposes_cascade_config(self):
        from core.audio_transcribe import fallback_stats

        stats = fallback_stats()
        assert stats["primary"] == "MiniMax-M3"
        assert stats["fallback"] == "gemini-2.5-flash"
        assert stats["max_bytes"] >= 1024 * 1024
        assert stats["max_duration_sec"] >= 60