"""Testes para os novos endpoints do relay (/relay/{nome}) e do registrador
auto-webhook (/admin/evolution/auto-webhook/{token}).

Esses dois endpoints foram adicionados na Parte1 do plano de Jennifer-prod
para suportar o padrao:
  - URL dedicada por instancia via nginx coringa /relay/<nome> -> runtime
  - Auto-preenchimento do webhook quando uma instancia e criada
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from main import admin_evolution_auto_webhook, evolution_webhook


VALID_PAYLOAD = {
    "event": "MESSAGES_UPSERT",
    "instance": "jennifer",
    "data": {
        "key": {
            "remoteJid": "5511966830020@s.whatsapp.net",
            "fromMe": False,
            "id": "RELAY_001",
        },
        "pushName": "Tester",
        "message": {"conversation": "oi pelo relay"},
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
async def test_relay_path_queues_message_like_legacy_webhook():
    """/relay/jennifer deve cair no mesmo handler e publicar no Pub/Sub."""
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-relay-001"
    request = _request(VALID_PAYLOAD)
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        with patch("core.message_ledger.register_or_load", return_value=None):
            with patch("main._schedule_mark_read") as mock_mark:
                response = await evolution_webhook(request, instance_path="jennifer")
    assert response.body is not None
    import json as _json
    payload = _json.loads(response.body)
    assert payload["queued"] is True
    assert payload["message_id"] == "pubsub-relay-001"
    mock_mark.assert_called()


@pytest.mark.asyncio
async def test_relay_path_with_subpath_also_works():
    """/relay/jennifer-prod e /relay/{qualquer-coisa} aceitam o mesmo handler."""
    publisher = MagicMock()
    publisher.publish.return_value = "pubsub-relay-002"
    payload = dict(VALID_PAYLOAD)
    payload["instance"] = "jennifer-prod"
    payload["data"]["key"]["id"] = "RELAY_002"
    request = _request(payload)
    with patch("core.pubsub_publisher.get_publisher", return_value=publisher):
        with patch("core.message_ledger.register_or_load", return_value=None):
            response = await evolution_webhook(request, instance_path="jennifer-prod")
    import json as _json
    body = _json.loads(response.body)
    assert body["queued"] is True


@pytest.fixture
def shared_secret(monkeypatch):
    """Configura o secret compartilhado para o registrador auto-webhook."""
    monkeypatch.setenv("AGENT_AUTO_WEBHOOK_SHARED_SECRET", "tk_test_123")


@pytest.mark.asyncio
async def test_auto_webhook_rejects_wrong_token():
    """Token errado deve retornar 404 (oculta a existencia do endpoint)."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "jennifer"})
    with patch.dict("os.environ", {"AGENT_AUTO_WEBHOOK_SHARED_SECRET": "tk_correct"}):
        with pytest.raises(HTTPException) as exc_info:
            await admin_evolution_auto_webhook(request, webhook_token="wrong")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_auto_webhook_rejects_missing_secret_config():
    """Se AGENT_AUTO_WEBHOOK_SHARED_SECRET nao estiver configurado, retorna 404."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "jennifer"})
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("AGENT_AUTO_WEBHOOK_SHARED_SECRET", None)
        with pytest.raises(HTTPException) as exc_info:
            await admin_evolution_auto_webhook(request, webhook_token="any")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_auto_webhook_ignores_non_instance_create_events(shared_secret):
    """Eventos nao-criacao (MESSAGES_UPSERT, CONNECTION_UPDATE) devem ser ignorados
    para nao causar ruido/duplicacao no webhook global."""
    request = _request({"event": "MESSAGES_UPSERT", "instance": "jennifer"})
    response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "ignored"
    assert "reason" in body


@pytest.mark.asyncio
async def test_auto_webhook_skips_unknown_instance(shared_secret):
    """INSTANCE_CREATE de instancia nao presente no Evolution deve ser ignorado."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "fantasma"})
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "jennifer"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})) as mock_set:
            response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "skipped"
    assert body["reason"] == "instance_not_in_evolution"
    mock_set.assert_not_called()


@pytest.mark.asyncio
async def test_auto_webhook_creates_webhook_for_known_instance(shared_secret):
    """INSTANCE_CREATE de instancia conhecida deve setar webhook dedicada via /relay."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "jennifer-prod"})
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "jennifer-prod"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})) as mock_set:
            response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "created"
    assert body["instance"] == "jennifer-prod"
    assert body["webhook_url"].endswith("/relay/jennifer-prod")
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args.args[0] == "jennifer-prod"
    assert call_args.args[1].endswith("/relay/jennifer-prod")


@pytest.mark.asyncio
async def test_auto_webhook_invalid_json_returns_400(shared_secret):
    request = _request(error=Exception("bad json"))
    with pytest.raises(HTTPException) as exc_info:
        await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_auto_webhook_missing_instance_returns_422(shared_secret):
    request = _request({"event": "INSTANCE_CREATE"})
    with pytest.raises(HTTPException) as exc_info:
        await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_auto_webhook_accepts_instanceName_payload(shared_secret):
    """Evolution v2 as vezes envia 'instanceName' em vez de 'instance'."""
    request = _request({"event": "INSTANCE_CREATE", "instanceName": "jennifer"})
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "jennifer"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})):
            response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "created"
    assert body["instance"] == "jennifer"