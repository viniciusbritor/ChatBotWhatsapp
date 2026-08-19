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
            with patch("main.is_instance_registered", return_value=True):
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
            with patch("main.is_instance_registered", return_value=True):
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


def test_auto_webhook_path_is_public():
    """O caminho /admin/evolution/auto-webhook/* deve ser publico (sem auth)."""
    from core.auth import is_path_protected
    assert is_path_protected("/admin/evolution/auto-webhook/tk_test_123") is False
    # Sanity check: /admin/agents continua protegido.
    assert is_path_protected("/admin/agents") is True


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
    """INSTANCE_CREATE de instancia conhecida deve setar webhook dedicada via /relay
    e criar o doc em whatsapp_accounts (Front 1c)."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "Jennifer-prod"})
    fake_db = MagicMock()
    fake_collection = MagicMock()
    fake_doc = MagicMock()
    fake_db.collection.return_value = fake_collection
    fake_collection.document.return_value = fake_doc
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "Jennifer-prod"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})) as mock_set:
            with patch("agent_loader._get_firestore_client", return_value=fake_db):
                response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "created"
    assert body["instance"] == "Jennifer-prod"
    assert body["webhook_url"].endswith("/relay/jennifer-prod")
    assert body["firestore_linked"] is True
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args.args[0] == "Jennifer-prod"
    assert call_args.args[1].endswith("/relay/jennifer-prod")
    # Firestore: doc.set(merge=True) foi chamado com os dados minimos
    fake_collection.document.assert_called_with("jennifer-prod")
    set_call = fake_doc.set.call_args
    assert set_call.kwargs.get("merge") is True
    assert set_call.args[0]["name"] == "Jennifer-prod"
    assert set_call.args[0]["instance"] == "Jennifer-prod"
    assert set_call.args[0]["status"] == "pending_owner"


@pytest.mark.asyncio
async def test_auto_webhook_creates_webhook_case_insensitive(shared_secret):
    """Comparacao de instancia deve ser case-insensitive (tolerar variacoes)."""
    request = _request({"event": "INSTANCE_CREATE", "instance": "jennifer-prod"})
    fake_db = MagicMock()
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "Jennifer-prod"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})):
            with patch("agent_loader._get_firestore_client", return_value=fake_db):
                response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "created"
    assert body["instance"] == "jennifer-prod"  # lowercase passado
    # URL usa canonical name (casing da Evolution)
    assert body["webhook_url"].endswith("/relay/jennifer-prod")
    assert body["firestore_linked"] is True


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
    fake_db = MagicMock()
    with patch("core.evolution_admin.fetch_instances", AsyncMock(return_value=[
        {"name": "jennifer"},
    ])):
        with patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})):
            with patch("agent_loader._get_firestore_client", return_value=fake_db):
                response = await admin_evolution_auto_webhook(request, webhook_token="tk_test_123")
    import json as _json
    body = _json.loads(response.body)
    assert body["status"] == "created"
    assert body["instance"] == "jennifer"
    assert body["firestore_linked"] is True
# ---- Front 1b: /admin/instances/{instance_id}/register ----


@pytest.mark.asyncio
async def test_register_requires_admin():
    """POST /admin/instances/{instance_id}/register exige admin (SA token)."""
    from main import admin_instances_register
    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(return_value={"owner_phone": "5511966830020"})
    with patch("main._require_admin", side_effect=HTTPException(status_code=403, detail="admin_required")):
        with pytest.raises(HTTPException) as exc_info:
            await admin_instances_register("vinicius", request)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_register_missing_owner_phone_returns_422():
    from main import admin_instances_register
    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(return_value={})
    with patch("main._require_admin"):
        with pytest.raises(HTTPException) as exc_info:
            await admin_instances_register("vinicius", request)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_json_returns_400():
    from main import admin_instances_register
    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(side_effect=Exception("bad json"))
    with patch("main._require_admin"):
        with pytest.raises(HTTPException) as exc_info:
            await admin_instances_register("vinicius", request)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_register_success_returns_webhook_url():
    """POST /admin/instances/{instance_id}/register com owner_phone valido
    cria o doc em whatsapp_accounts/{id} e retorna a URL do webhook."""
    from main import admin_instances_register

    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(return_value={
        "owner_phone": "5511966830020",
        "admin_phones": ["5511966830020", "5511917389901"],
        "name": "Vinicius",
    })
    with patch("main._require_admin"):
        with patch("main._write_account", AsyncMock(return_value=True)) as mock_write:
            with patch("main.invalidate_instance_registry_cache") as mock_invalidate:
                response = await admin_instances_register("Vinicius", request)
    import json as _json
    body = _json.loads(response.body)
    assert body["instance"] == "Vinicius"
    assert body["webhook_url"].endswith("/relay/vinicius")
    assert body["owner_phone"] == "5511966830020"
    assert body["admin_phones"] == ["5511966830020", "5511917389901"]
    assert body["status"] == "registered"
    call_args = mock_write.call_args
    assert call_args.args[0] == "vinicius"
    assert call_args.args[1]["instance"] == "Vinicius"
    assert call_args.args[1]["owner_phone"] == "5511966830020"
    assert call_args.args[1]["admin_phones"] == ["5511966830020", "5511917389901"]
    invalidate_keys = [c.args[0] if c.args else c.kwargs.get("instance_name", "")
                       for c in mock_invalidate.call_args_list]
    assert "Vinicius" in invalidate_keys
    assert "vinicius" in invalidate_keys


@pytest.mark.asyncio
async def test_register_preserves_existing_credentials():
    """_write_account usa merge=True, entao google_oauth_token/composio
    existentes nao sao apagados quando o admin registra/usa o endpoint."""
    from main import admin_instances_register

    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(return_value={"owner_phone": "5511966830020"})
    with patch("main._require_admin"):
        with patch("main._write_account", AsyncMock(return_value=True)) as mock_write:
            await admin_instances_register("vinicius", request)
    call_kwargs = mock_write.call_args.args[1]
    assert "google_oauth_token" not in call_kwargs
    assert "composio_linked_at" not in call_kwargs


@pytest.mark.asyncio
async def test_register_strips_phone_formatting():
    """owner_phone deve ser normalizado para digits puros."""
    from main import admin_instances_register

    request = MagicMock()
    request.headers = {}
    request.json = AsyncMock(return_value={
        "owner_phone": "+55 (11) 96683-0020",
        "admin_phones": ["+55 11 91738-9901"],
    })
    with patch("main._require_admin"):
        with patch("main._write_account", AsyncMock(return_value=True)) as mock_write:
            await admin_instances_register("vinicius", request)
    call_kwargs = mock_write.call_args.args[1]
    assert call_kwargs["owner_phone"] == "5511966830020"
    assert call_kwargs["admin_phones"] == ["5511917389901"]
