import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from main import (
    _log_mark_read_result,
    _safe_mark_read,
    _schedule_mark_read,
    evolution_webhook,
)


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


def _noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_webhook_queues_valid_message():
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-001"
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        with patch("core.message_ledger.register_or_load", return_value=None):
            with patch("main._safe_mark_read",
                       new=AsyncMock(return_value={
                           "status": "ok",
                           "message_id": "WEBHOOK_001",
                           "remote_jid": "5511966830020@s.whatsapp.net",
                           "instance": "jennifer",
                       })):
                with patch("main._log_mark_read_result"):
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
        with patch("core.message_ledger.register_or_load", return_value=None):
            with patch("main._safe_mark_read",
                       new=AsyncMock(return_value={"status": "ok"})):
                with patch("main._log_mark_read_result"):
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
        with patch("core.message_ledger.register_or_load", return_value=None):
            with patch("main._safe_mark_read",
                       new=AsyncMock(return_value={"status": "ok"})):
                with patch("main._log_mark_read_result"):
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
        with patch("core.message_ledger.register_or_load", return_value=None):
            with patch("main._safe_mark_read",
                       new=AsyncMock(return_value={"status": "ok"})):
                with patch("main._log_mark_read_result"):
                    response = await evolution_webhook(_request(payload))
    assert json.loads(response.body)["queued"] is True


@pytest.mark.asyncio
async def test_safe_mark_read_returns_ok_on_success():
    fake = AsyncMock(return_value={"status": "ok", "message_id": "X"})
    with patch("core.evolution_client.mark_messages_read", new=fake):
        envelope = {
            "instance": "jennifer",
            "message_id": "MSG_OK",
            "remote_jid": "5511966830020@s.whatsapp.net",
        }
        result = await _safe_mark_read(envelope)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_safe_mark_read_returns_skipped_when_no_remote_jid():
    envelope = {"instance": "jennifer", "message_id": "MSG_X"}
    result = await _safe_mark_read(envelope)
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_safe_mark_read_returns_timeout_on_wait_for():
    fake = AsyncMock(side_effect=asyncio.TimeoutError)
    with patch("core.evolution_client.mark_messages_read", new=fake):
        envelope = {
            "instance": "jennifer",
            "message_id": "MSG_TIMEOUT",
            "remote_jid": "5511966830020@s.whatsapp.net",
        }
        result = await _safe_mark_read(envelope)
    assert result["status"] == "timeout"


@pytest.mark.asyncio
async def test_safe_mark_read_returns_failed_on_exception():
    fake = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("core.evolution_client.mark_messages_read", new=fake):
        envelope = {
            "instance": "jennifer",
            "message_id": "MSG_FAIL",
            "remote_jid": "5511966830020@s.whatsapp.net",
        }
        result = await _safe_mark_read(envelope)
    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"


def test_log_mark_read_result_ok_logs_event():
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = None
    task.result.return_value = {
        "status": "ok",
        "message_id": "MSG_OK",
        "remote_jid": "j",
        "instance": "jennifer",
    }
    with patch("main.logger") as logger:
        _log_mark_read_result(task)
    logger.info.assert_called_once()
    logger.warning.assert_not_called()


def test_log_mark_read_result_timeout_logs_warning():
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = None
    task.result.return_value = {
        "status": "timeout",
        "message_id": "MSG_T",
        "remote_jid": "j",
        "instance": "jennifer",
        "error_type": "TimeoutError",
    }
    with patch("main.logger") as logger:
        _log_mark_read_result(task)
    logger.warning.assert_called_once()
    args, _ = logger.warning.call_args
    assert args[0] == "evolution_mark_read_timeout"


def test_log_mark_read_result_exc_logs_warning():
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = RuntimeError("boom")
    task.result.side_effect = RuntimeError("not used")
    with patch("main.logger") as logger:
        _log_mark_read_result(task)
    logger.warning.assert_called_once()
    args, _ = logger.warning.call_args
    assert args[0] == "evolution_mark_read_failed"


@pytest.mark.asyncio
async def test_schedule_mark_read_registers_callback():
    envelope = {
        "instance": "jennifer",
        "message_id": "MSG_S",
        "remote_jid": "5511966830020@s.whatsapp.net",
    }
    with patch("main._safe_mark_read",
               new=AsyncMock(return_value={"status": "ok"})):
        with patch("main._log_mark_read_result") as callback:
            task = _schedule_mark_read(envelope)
            await task
    callback.assert_called_once_with(task)
