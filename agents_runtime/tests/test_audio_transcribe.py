import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAudioValidation:
    def test_rejects_unknown_mimetype(self):
        from tools.audio_transcribe import AudioValidationError, _validate_mimetype

        with pytest.raises(AudioValidationError, match="audio_mimetype_not_allowed"):
            _validate_mimetype("application/octet-stream")

    def test_rejects_invalid_base64(self):
        from tools.audio_transcribe import AudioValidationError, _decode_base64

        with pytest.raises(AudioValidationError, match="audio_base64_invalid"):
            _decode_base64("not-valid-base64")

    def test_rejects_large_audio(self, monkeypatch):
        from tools.audio_transcribe import AudioValidationError, _validate_size

        monkeypatch.setattr("tools.audio_transcribe.AUDIO_MAX_BYTES", 3)
        with pytest.raises(AudioValidationError, match="audio_too_large"):
            _validate_size(b"1234")

    def test_requires_https_url(self):
        from tools.audio_transcribe import AudioValidationError, _validate_audio_url

        with pytest.raises(AudioValidationError, match="audio_url_https_required"):
            _validate_audio_url("http://evolution.coherenceai.com.br/audio.ogg")

    def test_rejects_host_outside_allowlist(self):
        from tools.audio_transcribe import AudioValidationError, _validate_audio_url

        with pytest.raises(AudioValidationError, match="audio_url_host_not_allowed"):
            _validate_audio_url("https://example.com/audio.ogg")

    def test_rejects_private_dns_resolution(self):
        from tools.audio_transcribe import AudioValidationError, _validate_audio_url

        with patch(
            "tools.audio_transcribe.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
        ):
            with pytest.raises(AudioValidationError, match="audio_url_private_address"):
                _validate_audio_url("https://evolution.coherenceai.com.br/audio.ogg")

    def test_accepts_allowlisted_public_host(self):
        from tools.audio_transcribe import _validate_audio_url

        with patch(
            "tools.audio_transcribe.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("8.8.8.8", 0))],
        ):
            result = _validate_audio_url("https://evolution.coherenceai.com.br/audio.ogg")

        assert result == "https://evolution.coherenceai.com.br/audio.ogg"


class TestAudioTranscription:
    @pytest.mark.asyncio
    async def test_base64_decodes_and_uses_local_transcriber(self):
        from tools.audio_transcribe import transcribe_base64

        encoded = base64.b64encode(b"audio-bytes").decode()
        with patch(
            "tools.audio_transcribe.transcribe_bytes",
            new_callable=AsyncMock,
            return_value="transcricao",
        ) as transcribe:
            result = await transcribe_base64(encoded, "audio/ogg")

        assert result == "transcricao"
        assert transcribe.await_args.args[0] == b"audio-bytes"

    @pytest.mark.asyncio
    async def test_transcribe_bytes_removes_temporary_file(self):
        from tools.audio_transcribe import transcribe_bytes

        captured = []

        def fake_transcribe(file_path):
            captured.append(file_path)
            return "texto"

        with patch("tools.audio_transcribe._transcribe_file", side_effect=fake_transcribe):
            result = await transcribe_bytes(b"audio-bytes", "audio/ogg")

        assert result == "texto"
        assert captured
        assert not __import__("os").path.exists(captured[0])

    def test_probe_rejects_audio_over_five_minutes(self):
        from tools.audio_transcribe import AudioValidationError, _probe_duration

        process = MagicMock(returncode=0, stdout='{"format":{"duration":"301.0"}}')
        with patch("tools.audio_transcribe.subprocess.run", return_value=process):
            with pytest.raises(AudioValidationError, match="audio_too_long"):
                _probe_duration("audio.ogg")


class TestGeminiAudioFallback:
    """23/07/2026: Gemini e fallback controlado do Whisper quando o
    Whisper falha tecnicamente e o consentimento (env ou flag) esta ativo.
    """

    def test_cascade_uses_gemini_as_fallback(self, monkeypatch):
        from core.llm_provider import LLMProvider

        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        provider = LLMProvider()
        providers = provider._build_cascade_providers("MiniMax-M2.7-highspeed")

        names = [item[0] for item in providers]
        assert "minimax-hs" in names
        assert "gemini-2.5-flash" in names
        assert provider.gemini_available() is True

    @pytest.mark.asyncio
    async def test_llm_provider_delegates_base64_to_whisper(self, monkeypatch):
        from core.llm_provider import LLMProvider

        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        provider = LLMProvider()
        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            return_value="texto",
        ) as transcribe:
            result = await provider.transcribe_audio_base64(
                "YXVkaW8=", "audio/ogg"
            )

        assert result == "texto"
        transcribe.assert_awaited_once_with("YXVkaW8=", "audio/ogg")

    @pytest.mark.asyncio
    async def test_gemini_call_requires_key(self, monkeypatch):
        """23/07/2026: Gemini e fallback controlado do Whisper.

        Quando a chave nao esta configurada, o provider levanta
        ``gemini_key_not_configured`` em vez de fazer request.
        """
        from core.llm_provider import LLMError, LLMProvider

        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        provider = LLMProvider()
        with pytest.raises(LLMError, match="gemini_key_not_configured"):
            await provider._stt_gemini(b"fake-audio", "audio/ogg")
