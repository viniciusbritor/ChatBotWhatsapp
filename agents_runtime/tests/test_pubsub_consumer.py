import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from core.pubsub_consumer import (
    _dedupe,
    _seen_message_ids,
    _strip_bearer,
    dispatch,
    parse_pubsub_push_body,
    verify_pubsub_token,
)


AUDIENCE = "https://agents-runtime-test.example.run.app/pubsub/push"
SERVICE_ACCOUNT = "agents-runtime-push@example.iam.gserviceaccount.com"


def test_verify_pubsub_token_rejects_missing_configuration(monkeypatch):
    monkeypatch.delenv("PUBSUB_TOKEN_AUDIENCE", raising=False)
    monkeypatch.delenv("PUBSUB_PUSH_SERVICE_ACCOUNT", raising=False)
    assert verify_pubsub_token("Bearer token") is False


def test_verify_pubsub_token_accepts_verified_service_account():
    claims = {
        "iss": "https://accounts.google.com",
        "email": SERVICE_ACCOUNT,
        "email_verified": True,
    }
    with patch("core.pubsub_consumer.id_token.verify_oauth2_token", return_value=claims) as verify:
        result = verify_pubsub_token(
            "Bearer signed-token",
            audience=AUDIENCE,
            service_account=SERVICE_ACCOUNT,
        )
    assert result is True
    assert verify.call_args.kwargs["audience"] == AUDIENCE


def test_verify_pubsub_token_rejects_invalid_signature():
    with patch(
        "core.pubsub_consumer.id_token.verify_oauth2_token",
        side_effect=ValueError("invalid signature"),
    ):
        assert verify_pubsub_token(
            "Bearer invalid-token",
            audience=AUDIENCE,
            service_account=SERVICE_ACCOUNT,
        ) is False


def test_verify_pubsub_token_rejects_wrong_service_account():
    claims = {
        "iss": "accounts.google.com",
        "email": "other@example.iam.gserviceaccount.com",
        "email_verified": True,
    }
    with patch("core.pubsub_consumer.id_token.verify_oauth2_token", return_value=claims):
        assert verify_pubsub_token(
            "token",
            audience=AUDIENCE,
            service_account=SERVICE_ACCOUNT,
        ) is False


def test_verify_pubsub_token_rejects_unverified_email():
    claims = {
        "iss": "accounts.google.com",
        "email": SERVICE_ACCOUNT,
        "email_verified": False,
    }
    with patch("core.pubsub_consumer.id_token.verify_oauth2_token", return_value=claims):
        assert verify_pubsub_token(
            "token",
            audience=AUDIENCE,
            service_account=SERVICE_ACCOUNT,
        ) is False


def test_verify_pubsub_token_rejects_invalid_issuer():
    claims = {
        "iss": "https://issuer.example.com",
        "email": SERVICE_ACCOUNT,
        "email_verified": True,
    }
    with patch("core.pubsub_consumer.id_token.verify_oauth2_token", return_value=claims):
        assert verify_pubsub_token(
            "token",
            audience=AUDIENCE,
            service_account=SERVICE_ACCOUNT,
        ) is False


def test_strip_bearer_supports_expected_formats():
    assert _strip_bearer("") == ""
    assert _strip_bearer("Bearer signed") == "signed"
    assert _strip_bearer("bearer signed") == "signed"
    assert _strip_bearer("raw-token") == "raw-token"


def test_parse_pubsub_push_body_decodes_envelope():
    payload = {"message_id": "MSG_001", "text": "olá"}
    body = {
        "message": {
            "data": base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"),
            "messageId": "PUB_001",
            "attributes": {"source": "test"},
            "publishTime": "2026-07-21T12:00:00Z",
        }
    }
    result = parse_pubsub_push_body(body)
    assert json.loads(result["data"]) == payload
    assert result["message_id"] == "PUB_001"
    assert result["attributes"] == {"source": "test"}


def test_parse_pubsub_push_body_accepts_flat_and_invalid_data():
    flat = parse_pubsub_push_body({"data": "raw", "message_id": "FLAT_001"})
    assert flat["data"] == "raw"
    assert flat["message_id"] == "FLAT_001"
    invalid = parse_pubsub_push_body({"message": {"data": object(), "messageId": "INVALID_001"}})
    assert invalid["message_id"] == "INVALID_001"


def test_dedupe_accepts_first_and_rejects_duplicate():
    _seen_message_ids.clear()
    assert _dedupe("") is True
    assert _dedupe("DEDUPE_001") is True
    assert _dedupe("DEDUPE_001") is False


def test_dedupe_enforces_memory_limit(monkeypatch):
    _seen_message_ids.clear()
    monkeypatch.setattr("core.pubsub_consumer._SEEN_MAX", 1)
    assert _dedupe("LIMIT_001") is True
    assert _dedupe("LIMIT_002") is True
    assert len(_seen_message_ids) == 1


@pytest.mark.asyncio
async def test_dispatch_returns_handler_result_and_drops_duplicate():
    _seen_message_ids.clear()
    handler = AsyncMock(return_value={"status": "ok"})
    payload = {"message_id": "DISPATCH_001"}
    first = await dispatch(payload, handler)
    second = await dispatch(payload, handler)
    assert first == {"status": "ok"}
    assert second == {"status": "duplicate", "message_id": "DISPATCH_001"}
    handler.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_dispatch_forgets_failed_message_for_retry():
    _seen_message_ids.clear()
    payload = {"message_id": "RETRY_001"}
    failing = AsyncMock(side_effect=RuntimeError("offline"))
    with pytest.raises(RuntimeError, match="offline"):
        await dispatch(payload, failing)
    succeeding = AsyncMock(return_value={"status": "ok"})
    result = await dispatch(payload, succeeding)
    assert result == {"status": "ok"}
    succeeding.assert_awaited_once_with(payload)
