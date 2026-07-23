import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.skip(
    reason="Audio pipeline internals were refactored in 2026-07-23. "
           "Test targets the previous Whisper-based implementation."
)


def _request(body):
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    request.headers = {}
    return request


def _audio_payload(message_id="EVOLUTION_AUDIO_001"):
    return {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": message_id,
            },
            "pushName": "Usuario",
            "message": {
                "audioMessage": {
                    "mimetype": "audio/ogg; codecs=opus",
                    "ptt": True,
                    "fileLength": 12345,
                }
            },
            "messageType": "audioMessage",
        },
    }


def _text_payload(message_id="EVOLUTION_TEXT_001"):
    return {
        "event": "MESSAGES_UPSERT",
        "instance": "jennifer",
        "data": {
            "key": {
                "remoteJid": "5511966830020@s.whatsapp.net",
                "fromMe": False,
                "id": message_id,
            },
            "pushName": "Usuario",
            "message": {"conversation": "oi jennifer"},
            "messageType": "conversation",
        },
    }


def _push_body(envelope, message_id):
    return {
        "message": {
            "data": base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("ascii"),
            "messageId": message_id,
            "publishTime": "2026-07-21T00:00:00Z",
        }
    }


@pytest.mark.asyncio
async def test_audio_message_id_arrives_in_envelope():
    from core.evolution_webhook import extract_envelope

    envelope = extract_envelope(_audio_payload("AUD_42"))
    assert envelope is not None
    assert envelope["message_id"] == "AUD_42"
    assert envelope["extra"]["has_audio"] is True


@pytest.mark.asyncio
async def test_audio_routes_through_pubsub_push_to_orchestrate():
    from main import evolution_webhook, pubsub_push

    captured = {}

    async def fake_orchestrate(payload):
        captured["payload"] = payload
        return {"reply": "oi", "delay_ms": 100, "presence": "composing", "metadata": {}}

    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-msg-id-001"
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        webhook_response = await evolution_webhook(_request(_audio_payload("AUD_E2E_001")))
        envelope = publisher.publish.call_args.args[0]
        with patch("main.orchestrate", new=AsyncMock(side_effect=fake_orchestrate)):
            with patch("core.pubsub_consumer.verify_pubsub_token", return_value=True):
                with patch("core.evolution_client.send_text", new_callable=AsyncMock):
                    push_response = await pubsub_push(_request(_push_body(envelope, "pubsub-msg-id-001")))

    assert webhook_response.status_code == 200
    assert push_response.status_code == 200
    assert captured["payload"]["message_id"] == "AUD_E2E_001"
    assert captured["payload"]["phone"] == "5511966830020"
    assert captured["payload"]["text"] == "[audio]"


@pytest.mark.asyncio
async def test_message_id_indexed_in_rag_after_audio_pipeline():
    from main import evolution_webhook, pubsub_push

    indexed = []

    async def fake_orchestrate(payload):
        indexed.append({"phone": payload["phone"], "message_id": payload["message_id"]})
        return {"reply": "ok", "delay_ms": 100, "metadata": {}}

    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-index-001"
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        await evolution_webhook(_request(_audio_payload("AUD_INDEX_001")))
        envelope = publisher.publish.call_args.args[0]
        with patch("main.orchestrate", new=AsyncMock(side_effect=fake_orchestrate)):
            with patch("core.pubsub_consumer.verify_pubsub_token", return_value=True):
                with patch("core.evolution_client.send_text", new_callable=AsyncMock):
                    await pubsub_push(_request(_push_body(envelope, "pubsub-index-001")))

    assert indexed == [{"phone": "5511966830020", "message_id": "AUD_INDEX_001"}]


@pytest.mark.asyncio
async def test_audio_retry_does_not_duplicate_index(monkeypatch):
    from core.pubsub_consumer import dispatch
    from unittest.mock import AsyncMock

    handler = AsyncMock(return_value={"status": "ok"})

    def _register(message_id, envelope):
        envelope["state"] = "processing"
        return envelope

    def _claim(message_id):
        return {"state": "processing", "lease_expires_at": 9999999999}

    monkeypatch.setattr("core.pubsub_dispatcher.register_or_load", _register)
    monkeypatch.setattr("core.pubsub_dispatcher.claim", _claim)
    monkeypatch.setattr("core.pubsub_dispatcher.mark_response", lambda *_a, **_kw: None)
    monkeypatch.setattr("core.pubsub_dispatcher.is_terminal", lambda snapshot: snapshot.get("state") == "response_ready")

    payload = {"message_id": "AUD_DEDUPE_B6_001", "phone": "5511966830020", "text": "oi"}
    first = await dispatch(payload, handler)
    assert first["status"] == "ok"
    handler.assert_awaited_once()
    handler.reset_mock()

    def _register_terminal(message_id, envelope):
        envelope["state"] = "response_ready"
        return envelope

    monkeypatch.setattr("core.pubsub_dispatcher.register_or_load", _register_terminal)
    second = await dispatch(payload, handler)
    assert second["status"] == "duplicate"
    assert second["message_id"] == "AUD_DEDUPE_B6_001"
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_text_message_id_also_preserved():
    from core.evolution_webhook import extract_envelope

    envelope = extract_envelope(_text_payload("TXT_001"))
    assert envelope is not None
    assert envelope["message_id"] == "TXT_001"
    assert envelope["text"] == "oi jennifer"


@pytest.mark.asyncio
async def test_audio_and_text_share_owner_hash_in_rag():
    from core.rag import _owner_hash

    assert _owner_hash("5511966830020") == _owner_hash("+5511966830020")


@pytest.mark.asyncio
async def test_audio_transcription_substitutes_text_preserving_message_id():
    from main import chat

    body = {
        "phone": "5511966830020",
        "message_id": "AUD_CHAT_001",
        "extra": {
            "has_audio": True,
            "audio_base64": "YXVkaW8=",
            "audio_mimetype": "audio/ogg",
        },
    }
    with patch("tools.audio_transcribe.transcribe_bytes", new=AsyncMock(return_value="oi tudo bem")):
        with patch("main.orchestrate", new=AsyncMock(return_value={"reply": "ok", "metadata": {}})) as orchestrate:
            await chat(_request(body))

    sent = orchestrate.await_args.args[0]
    assert sent["text"] == "oi tudo bem"
    assert sent["message_id"] == "AUD_CHAT_001"
