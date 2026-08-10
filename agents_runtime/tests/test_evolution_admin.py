"""Tests for Evolution admin client (instances, QR, webhook)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_http_client(method: str, status: int, json_data):
    """Cria AsyncMock de httpx.AsyncClient com __aenter__ retornando ele mesmo.

    O codigo usa `async with httpx.AsyncClient(...) as client` — o context
    manager precisa retornar o MESMO mock (senão o retorno do método vira
    um AsyncMock genérico).
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.status_code = status
    mock_response.json.return_value = json_data
    getattr(mock_client, method).return_value = mock_response
    return mock_client


class TestFetchInstances:
    def test_returns_list_on_success(self):
        from core.evolution_admin import fetch_instances

        mock_client = _mock_http_client("get", 200, [{"name": "Jennifer", "connectionStatus": "open"}])

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(fetch_instances())

        assert len(result) == 1
        assert result[0]["name"] == "Jennifer"

    def test_returns_empty_on_http_error(self):
        from core.evolution_admin import fetch_instances

        mock_client = _mock_http_client("get", 500, {})

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(fetch_instances())

        assert result == []


class TestGetConnectionState:
    def test_returns_state(self):
        from core.evolution_admin import get_connection_state

        mock_client = _mock_http_client("get", 200, {"instance": {"state": "open"}})

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(get_connection_state("Jennifer"))

        assert result["state"] == "open"

    def test_missing_api_key_returns_unknown(self):
        from core.evolution_admin import get_connection_state

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "")):
            result = asyncio.run(get_connection_state("Jennifer"))

        assert result["state"] == "unknown"


class TestCreateInstance:
    def test_requires_name(self):
        from core.evolution_admin import create_instance

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")):
            result = asyncio.run(create_instance(""))

        assert result.get("error") == "instance_name_required"

    def test_posts_whatsapp_baileys_payload(self):
        from core.evolution_admin import create_instance

        mock_client = _mock_http_client("post", 201, {"instance": {"instanceName": "novo"}})

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client), \
             patch("core.evolution_admin.set_webhook", AsyncMock(return_value={"set": True})):
            result = asyncio.run(create_instance("novo", webhook_url="https://x.example/webhook"))

        assert result.get("created") is True
        _, kwargs = mock_client.post.call_args
        payload = kwargs["json"]
        assert payload["instanceName"] == "novo"
        assert payload["integration"] == "WHATSAPP-BAILEYS"
        assert "webhook" not in payload  # webhook nao vai no create (vai via set_webhook)


class TestGetQrCode:
    def test_returns_base64(self):
        from core.evolution_admin import get_qr_code

        mock_client = _mock_http_client("get", 200, {"base64": "iVBORw0KGgo="})

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(get_qr_code("novo"))

        assert result["qr_base64"] == "iVBORw0KGgo="


class TestDeleteInstance:
    def test_deletes_with_v2_endpoint(self):
        from core.evolution_admin import delete_instance

        mock_client = _mock_http_client("delete", 200, {"status": "SUCCESS"})

        with patch("core.evolution_admin._config", return_value=("https://evo.test", "key123")), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(delete_instance("novo"))

        assert result.get("deleted") is True
        url = mock_client.delete.call_args.args[0]
        assert url.endswith("/instance/delete/novo")  # endpoint v2.x
