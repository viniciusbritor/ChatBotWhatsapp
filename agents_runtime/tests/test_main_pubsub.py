import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import pubsub_push


def _request(payload, message_id):
    envelope = {
        "message": {
            "data": base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"),
            "messageId": message_id,
        }
    }
    request = MagicMock()
    request.json = AsyncMock(return_value=envelope)
    request.headers = {"Authorization": "Bearer signed-token"}
    request.url = "https://agents-runtime.example.run.app/pubsub/push"
    return request


@pytest.mark.asyncio
async def test_pubsub_push_delivers_orchestrator_reply_to_evolution():
    payload = {
        "message_id": "PUSH_DELIVERY_001",
        "instance": "jennifer",
        "phone": "5511966830020",
        "remote_jid": "5511966830020@s.whatsapp.net",
        "text": "oi",
    }
    result = {
        "reply": "Olá!",
        "delay_ms": 1200,
        "presence": "composing",
        "metadata": {},
    }
    with patch("core.pubsub_consumer.verify_pubsub_token", return_value=True):
        with patch("main.orchestrate", new=AsyncMock(return_value=result)):
            with patch("core.evolution_client.send_text", new=AsyncMock(return_value={})) as send:
                response = await pubsub_push(_request(payload, "pubsub-delivery-001"))

    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["delivered"] is True
    send.assert_awaited_once_with(
        instance="jennifer",
        phone="5511966830020",
        text="Olá!",
        delay_ms=1200,
        presence="composing",
        remote_jid="5511966830020@s.whatsapp.net",
    )


@pytest.mark.asyncio
async def test_pubsub_push_delivery_failure_does_not_retry_to_avoid_storm():
    """Anti-retry-storm guard: send_text failures are LOGGED but return 200
    so Pub/Sub does not redeliver the message. The underlying problem is
    logged for observability; the user does not see exponential cost
    growth from a transient Evolution outage.
    """
    payload = {
        "message_id": "PUSH_RETRY_001",
        "instance": "jennifer",
        "phone": "5511966830020",
        "text": "oi",
    }
    result = {"reply": "Resposta", "delay_ms": 0, "presence": "composing", "metadata": {}}
    with patch("core.pubsub_consumer.verify_pubsub_token", return_value=True):
        with patch("main.orchestrate", new=AsyncMock(return_value=result)):
            with patch(
                "core.evolution_client.send_text",
                new=AsyncMock(side_effect=RuntimeError("evolution offline")),
            ):
                response = await pubsub_push(_request(payload, "pubsub-no-retry-001"))

    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["delivered"] is False


@pytest.mark.asyncio
async def test_pubsub_push_skips_send_when_phone_missing():
    """Empty phone (stale Pub/Sub retries from before OAuth per-user was
    required) must not crash or trigger 5xx. The reply is still generated
    for observability but is dropped.
    """
    payload = {
        "message_id": "PUSH_RETRY_NO_PHONE",
        "instance": "jennifer",
        "phone": "",
        "text": "oi",
    }
    result = {"reply": "Resposta", "delay_ms": 0, "presence": "composing", "metadata": {}}
    with patch("core.pubsub_consumer.verify_pubsub_token", return_value=True):
        with patch("main.orchestrate", new=AsyncMock(return_value=result)):
            with patch("core.evolution_client.send_text", new=AsyncMock(return_value={})) as send:
                response = await pubsub_push(_request(payload, "pubsub-no-phone-001"))

    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["delivered"] is False
    send.assert_not_called()
