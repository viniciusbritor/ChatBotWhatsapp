"""Tests for Fase B fixes: telemetry on missing message_id + audio failure audit."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _request_with_body(body):
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    return request


class TestMessageIdTelemetry:
    def test_missing_message_id_logs_warning(self, caplog):
        from orchestrator import _message_id

        payload = {"phone": "5511966830020", "instance": "jennifer", "text": "oi", "extra": {}}
        with caplog.at_level(logging.WARNING, logger="orchestrator"):
            result = _message_id(payload)

        assert result is None
        assert any(
            "message_id_missing" in record.message
            and "owner_hash=" in record.message
            and "5511966830020" not in record.message
            for record in caplog.records
        )

    def test_present_message_id_does_not_log_warning(self, caplog):
        from orchestrator import _message_id

        payload = {"phone": "5511966830020", "message_id": "ABC123", "extra": {}}
        with caplog.at_level(logging.WARNING, logger="orchestrator"):
            result = _message_id(payload)

        assert result == "ABC123"
        assert not any(
            "message_id_missing" in record.message for record in caplog.records
        )

    def test_message_id_found_in_extra(self):
        from orchestrator import _message_id

        payload = {"phone": "5511966830020", "extra": {"message_id": "EXTRA_42"}}
        assert _message_id(payload) == "EXTRA_42"

    def test_message_id_found_in_extra_key_dict(self):
        from orchestrator import _message_id

        payload = {"phone": "5511966830020", "extra": {"key": {"id": "KEY_42"}}}
        assert _message_id(payload) == "KEY_42"


class TestAudioFailureAudit:
    @pytest.mark.asyncio
    async def test_audit_persists_audio_failure_to_rag(self):
        from main import chat
        from tools.audio_transcribe import AudioValidationError

        body = {
            "phone": "5511966830020",
            "sender_name": "Vinicius",
            "message_id": "AUD_FAIL_001",
            "extra": {"has_audio": True, "audio_base64": "invalid"},
        }

        indexed_calls = []

        async def fake_index(body, error_code):
            indexed_calls.append({"body": dict(body), "error_code": error_code})
            return {"status": "indexed", "doc_id": "audit-doc-1"}

        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            side_effect=AudioValidationError("audio_base64_invalid"),
        ):
            with patch(
                "main.index_audio_failure_for_audit",
                new=AsyncMock(side_effect=fake_index),
            ) as audit_mock:
                response = await chat(_request_with_body(body))

        import json
        payload = json.loads(response.body)
        assert payload["metadata"]["error"] == "audio_transcription_failed"
        assert payload["metadata"]["audit_indexed"] is True
        assert payload["metadata"]["reason"] == "audio_base64_invalid"

        audit_mock.assert_awaited_once()
        call_body, call_error = audit_mock.await_args.args
        assert call_body["phone"] == "5511966830020"
        assert call_body["message_id"] == "AUD_FAIL_001"
        assert call_error == "audio_base64_invalid"

    @pytest.mark.asyncio
    async def test_audit_indexed_for_unexpected_audio_errors(self):
        from main import chat

        body = {
            "phone": "5511966830020",
            "sender_name": "Vinicius",
            "message_id": "AUD_FAIL_002",
            "extra": {"has_audio": True, "audio_url": "https://evolution.coherenceai.com.br/audio.ogg"},
        }

        with patch(
            "tools.audio_transcribe.transcribe_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("whisper oom"),
        ):
            with patch(
                "main.index_audio_failure_for_audit",
                new=AsyncMock(return_value={"status": "indexed"}),
            ) as audit_mock:
                response = await chat(_request_with_body(body))

        import json
        payload = json.loads(response.body)
        assert payload["metadata"]["error"] == "audio_transcription_unavailable"
        assert payload["metadata"]["audit_indexed"] is True

        audit_mock.assert_awaited_once()
        call_error = audit_mock.await_args.args[1]
        assert "unavailable" in call_error
        assert "RuntimeError" in call_error

    @pytest.mark.asyncio
    async def test_audit_not_called_when_text_fallback_present(self):
        from main import chat
        from tools.audio_transcribe import AudioValidationError

        body = {
            "phone": "5511966830020",
            "text": "texto alternativo",
            "extra": {"has_audio": True, "audio_base64": "invalid"},
        }

        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            side_effect=AudioValidationError("audio_base64_invalid"),
        ):
            with patch(
                "main.orchestrate",
                new_callable=AsyncMock,
                return_value={"reply": "ok", "metadata": {}},
            ) as orchestrate:
                with patch(
                    "main.index_audio_failure_for_audit",
                    new=AsyncMock(return_value={"status": "indexed"}),
                ) as audit_mock:
                    await chat(_request_with_body(body))

        orchestrate.assert_awaited_once()
        audit_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_index_audio_failure_for_audit_function(self):
        from orchestrator import index_audio_failure_for_audit

        body = {
            "phone": "5511966830020",
            "message_id": "AUD_DIRECT_001",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

        with patch(
            "orchestrator._index_message",
            new=AsyncMock(return_value={"status": "indexed", "doc_id": "audit-x"}),
        ) as index_mock:
            result = await index_audio_failure_for_audit(body, "audio_base64_invalid")

        assert result["status"] == "indexed"
        index_mock.assert_awaited_once()
        call_args = index_mock.await_args
        assert call_args.args[0] == "5511966830020"
        assert "[audio transcription failed" in call_args.args[1]
        assert "audio_base64_invalid" in call_args.args[1]
        assert call_args.kwargs["message_id"] == "audio-fail:AUD_DIRECT_001"
        assert call_args.kwargs["agent_id"] == "audio-transcriber"
        assert call_args.kwargs["response_identity"] == "AudioAudit"

    @pytest.mark.asyncio
    async def test_audit_metadata_reports_index_failure(self):
        from main import chat
        from tools.audio_transcribe import AudioValidationError

        body = {
            "phone": "5511966830020",
            "message_id": "AUD_FAIL_003",
            "extra": {"has_audio": True, "audio_base64": "invalid"},
        }

        with patch(
            "tools.audio_transcribe.transcribe_base64",
            new_callable=AsyncMock,
            side_effect=AudioValidationError("audio_base64_invalid"),
        ):
            with patch(
                "main.index_audio_failure_for_audit",
                new=AsyncMock(return_value={"status": "error"}),
            ):
                response = await chat(_request_with_body(body))

        import json
        payload = json.loads(response.body)
        assert payload["metadata"]["audit_indexed"] is False
        assert payload["metadata"]["audit_status"] == "error"

    @pytest.mark.asyncio
    async def test_audit_skipped_without_phone(self):
        from orchestrator import index_audio_failure_for_audit

        body = {"message_id": "X", "extra": {}}
        result = await index_audio_failure_for_audit(body, "any_error")
        assert result["status"] == "skipped"
        assert result["reason"] == "missing_phone"
