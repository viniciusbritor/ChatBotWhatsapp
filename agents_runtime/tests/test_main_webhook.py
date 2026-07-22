import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from main import evolution_webhook


VALID_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "WEBHOOK_001",
        },
        "pushName": "Usuario",
        "message": {"conversation": "oi"},
        "messageType": "conversation",
    },
}


def _request(body=None, error=None):
    request = MagicMock()
    request.headers = {}
    if error is not None:
        request.json = AsyncMock(side_effect=error)
    else:
        request.json = AsyncMock(return_value=body)
    return request


@pytest.mark.asyncio
async def test_webhook_queues_valid_message():
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-001"
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        response = await evolution_webhook(_request(VALID_PAYLOAD))

    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload == {
        "queued": True,
        "message_id": "pubsub-001",
        "request_id": "WEBHOOK_001",
    }


@pytest.mark.asyncio
async def test_webhook_publishes_expected_attributes():
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-002"
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        await evolution_webhook(_request(VALID_PAYLOAD))

    _, kwargs = publisher.publish.call_args
    assert kwargs["topic"] == "chatbotwhatsapp-messages"
    assert kwargs["attributes"] == {
        "source": "evolution-webhook",
        "instance": "jennifer",
    }


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_json():
    with pytest.raises(HTTPException) as exc:
        await evolution_webhook(_request(error=ValueError("invalid")))
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_json"


@pytest.mark.asyncio
async def test_webhook_rejects_non_object_payload():
    with pytest.raises(HTTPException) as exc:
        await evolution_webhook(_request([]))
    assert exc.value.status_code == 422
    assert exc.value.detail == "payload must be an object"


@pytest.mark.asyncio
async def test_webhook_ignores_non_message_event():
    response = await evolution_webhook(
        _request({"event": "CONNECTION_UPDATE", "instance": "jennifer", "data": {}})
    )
    assert json.loads(response.body) == {
        "status": "ignored",
        "event": "CONNECTION_UPDATE",
    }


@pytest.mark.asyncio
async def test_webhook_ignores_filtered_message():
    payload = {
        **VALID_PAYLOAD,
        "data": {
            **VALID_PAYLOAD["data"],
            "key": {**VALID_PAYLOAD["data"]["key"], "fromMe": True},
        },
    }
    response = await evolution_webhook(_request(payload))
    assert json.loads(response.body) == {"status": "ignored", "reason": "filtered"}


@pytest.mark.asyncio
async def test_webhook_returns_generic_publish_error():
    publisher = MagicMock()
    publisher.publish.side_effect = RuntimeError("sensitive internal detail")
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        with pytest.raises(HTTPException) as exc:
            await evolution_webhook(_request(VALID_PAYLOAD))
    assert exc.value.status_code == 503
    assert exc.value.detail == "publish_failed"
    assert "sensitive" not in exc.value.detail


@pytest.mark.asyncio
async def test_webhook_accepts_lowercase_event():
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-lowercase"
    payload = {**VALID_PAYLOAD, "event": "messages.upsert"}
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        response = await evolution_webhook(_request(payload))
    assert json.loads(response.body)["queued"] is True
