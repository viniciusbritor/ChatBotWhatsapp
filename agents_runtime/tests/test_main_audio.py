import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def request_with_body(body):
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    return request


class TestChatAudioRoute:
    @pytest.mark.asyncio
    async def test_audio_only_base64_is_accepted_and_masked(self):
        from main import chat

        body = {
            "phone": "5511999999999",
            "sender_name": "Vinicius",
            "extra": {
                "has_audio": True,
                "audio_base64": "YXVkaW8=",
                "audio_mimetype": "audio/ogg",
                "message_id": "audio-1",
            },
        }
        response_payload = {
            "reply": "Recebido",
            "delay_ms": 10,
            "presence": "composing",
            "metadata": {"agent_id": "jennifier"},
        }
        with patch("tools.audio_transcribe.transcribe_base64", new_callable=AsyncMock, return_value="Email pessoa@example.com") as base64_stt:
            with patch("tools.audio_transcribe.transcribe_url", new_callable=AsyncMock) as url_stt:
                with patch("main.orchestrate", new_callable=AsyncMock, return_value=response_payload) as orchestrate:
                    response = await chat(request_with_body(body))

        sent_body = orchestrate.await_args.args[0]
        assert sent_body["text"] == "Email [MASK_EMAIL]"
        assert sent_body["extra"]["audio_source"] == "base64"
        base64_stt.assert_awaited_once()
        url_stt.assert_not_awaited()
        assert json.loads(response.body)["reply"] == "Recebido"

    @pytest.mark.asyncio
    async def test_audio_url_is_used_only_without_base64(self):
        from main import chat

        body = {
            "phone": "5511999999999",
            "extra": {
                "has_audio": True,
                "audio_url": "https://evolution.coherenceai.com.br/audio.ogg",
                "audio_mimetype": "audio/ogg",
            },
        }
        with patch("tools.audio_transcribe.transcribe_base64", new_callable=AsyncMock) as base64_stt:
            with patch("tools.audio_transcribe.transcribe_url", new_callable=AsyncMock, return_value="mensagem por voz") as url_stt:
                with patch("main.orchestrate", new_callable=AsyncMock, return_value={"reply": "ok", "metadata": {}}) as orchestrate:
                    await chat(request_with_body(body))

        base64_stt.assert_not_awaited()
        url_stt.assert_awaited_once()
        assert orchestrate.await_args.args[0]["text"] == "mensagem por voz"

    @pytest.mark.asyncio
    async def test_invalid_audio_returns_controlled_response(self):
        from main import chat
        from tools.audio_transcribe import AudioValidationError

        body = {
            "phone": "5511999999999",
            "extra": {"has_audio": True, "audio_base64": "invalid"},
        }
        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            side_effect=AudioValidationError("audio_base64_invalid"),
        ):
            with patch("main.orchestrate", new_callable=AsyncMock) as orchestrate:
                response = await chat(request_with_body(body))

        payload = json.loads(response.body)
        assert payload["metadata"]["error"] == "audio_transcription_failed"
        assert payload["metadata"]["reason"] == "audio_base64_invalid"
        orchestrate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_text_is_used_when_audio_fails(self):
        from main import chat
        from tools.audio_transcribe import AudioValidationError

        body = {
            "phone": "5511999999999",
            "text": "texto alternativo",
            "extra": {"has_audio": True, "audio_base64": "invalid"},
        }
        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            side_effect=AudioValidationError("audio_base64_invalid"),
        ):
            with patch("main.orchestrate", new_callable=AsyncMock, return_value={"reply": "ok", "metadata": {}}) as orchestrate:
                await chat(request_with_body(body))

        assert orchestrate.await_args.args[0]["text"] == "texto alternativo"

    @pytest.mark.asyncio
    async def test_request_without_text_or_audio_is_rejected(self):
        from main import chat

        with pytest.raises(HTTPException) as error:
            await chat(request_with_body({"phone": "5511999999999", "extra": {}}))

        assert error.value.status_code == 422
        assert error.value.detail == "text or audio required"

    @pytest.mark.asyncio
    async def test_phone_is_always_required(self):
        from main import chat

        with pytest.raises(HTTPException) as error:
            await chat(request_with_body({"text": "oi", "extra": {}}))

        assert error.value.status_code == 422
        assert error.value.detail == "phone required"
