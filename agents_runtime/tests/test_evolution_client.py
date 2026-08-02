"""Regression tests for core/evolution_client.py endpoints.

Covers:
- sendText with the v2 singular mark endpoint
- markMessageAsRead (singular) with v2 payload
- sendImage (sendMedia JSON) com mediatype='image' (01/08/2026 fix)
- case-insensitive instance resolution
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


PHONE = "5511966830020"
INSTANCE_RAW = "jennifer"
INSTANCE_CANONICAL = "Jennifer"


def _ok_json(payload: dict) -> httpx.Response:
    response = httpx.Response(200, json=payload)
    return response


def test_send_text_resolves_instance_case():
    from core.evolution_client import send_text

    instances = [
        {"id": "abc", "name": INSTANCE_CANONICAL, "connectionStatus": "open"},
        {"id": "xyz", "name": "Other", "connectionStatus": "open"},
    ]

    captured = {}

    class _StubSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url, headers=None, **kwargs):
            captured["get"] = url
            return httpx.Response(200, json=instances)

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, headers=None, json=None, **kwargs):
            captured["post_url"] = url
            captured["post_json"] = json
            return httpx.Response(201, json={"ok": True, "id": "x"})

    with patch("core.evolution_client.get_secret", return_value="token"):
        with patch("core.evolution_client.httpx.Client", _StubSyncClient):
            with patch("core.evolution_client.httpx.AsyncClient", _StubAsyncClient):
                import asyncio

                asyncio.run(send_text(INSTANCE_RAW, PHONE, "diag"))
    assert captured["post_url"].endswith(f"/message/sendText/{INSTANCE_CANONICAL}")


def test_mark_messages_read_uses_singular_endpoint():
    from core.evolution_client import mark_messages_read

    instances = [
        {"id": "abc", "name": INSTANCE_CANONICAL, "connectionStatus": "open"},
    ]

    captured = {}

    class _StubSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url, headers=None, **kwargs):
            return httpx.Response(200, json=instances)

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, headers=None, json=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(200, json={"ok": True})

    with patch("core.evolution_client.get_secret", return_value="token"):
        with patch("core.evolution_client.httpx.Client", _StubSyncClient):
            with patch("core.evolution_client.httpx.AsyncClient", _StubAsyncClient):
                import asyncio

                asyncio.run(
                    mark_messages_read(
                        "jennifer",
                        "5511966830020@s.whatsapp.net",
                        ["MSG-1", "MSG-2"],
                    )
                )
    assert captured["url"].endswith(f"/chat/markMessageAsRead/{INSTANCE_CANONICAL}")
    assert "readMessages" in captured["json"]
    assert captured["json"]["readMessages"][0]["id"] == "MSG-1"
    assert captured["json"]["readMessages"][0]["remoteJid"] == (
        "5511966830020@s.whatsapp.net"
    )


def test_send_image_uses_sendmedia_json_endpoint():
    """01/08/2026: sendImage antigo retorna 404. Migrar para
    /message/sendMedia/{instance} com JSON body (mediatype='image',
    media=base64, fileName)."""
    from core.evolution_client import send_image

    instances = [
        {"id": "abc", "name": INSTANCE_CANONICAL, "connectionStatus": "open"},
    ]

    captured = {}

    class _StubSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url, headers=None, **kwargs):
            captured["get"] = url
            return httpx.Response(200, json=instances)

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, headers=None, json=None, **kwargs):
            captured["post_url"] = url
            captured["post_json"] = json
            captured["post_kwargs"] = kwargs
            return httpx.Response(201, json={"ok": True, "id": "img-1"})

    with patch("core.evolution_client.get_secret", return_value="token"):
        with patch("core.evolution_client.httpx.Client", _StubSyncClient):
            with patch("core.evolution_client.httpx.AsyncClient", _StubAsyncClient):
                import asyncio

                png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
                result = asyncio.run(
                    send_image(
                        INSTANCE_RAW,
                        PHONE,
                        png_bytes,
                        filename="report.png",
                        caption="Resultados",
                    )
                )

    # Endpoint correto: sendMedia (nao sendImage)
    assert captured["post_url"].endswith(f"/message/sendMedia/{INSTANCE_CANONICAL}")
    assert "sendImage" not in captured["post_url"], (
        f"endpoint antigo sendImage retorna 404: {captured['post_url']}"
    )

    # Body JSON com mediatype=image e media em base64
    body = captured["post_json"]
    assert body is not None, "send_image deve usar JSON body"
    assert body["mediatype"] == "image"
    assert body["fileName"] == "report.png"
    assert body["caption"] == "Resultados"
    import base64
    assert base64.b64decode(body["media"]) == png_bytes

    # NUNCA usar multipart/form-data
    assert "files" not in captured["post_kwargs"]
    assert "data" not in captured["post_kwargs"]

    assert result["ok"] is True


def test_send_image_handles_evolution_error():
    """Falha da Evolution (>=400) deve levantar EvolutionDeliveryError."""
    from core.evolution_client import send_image, EvolutionDeliveryError

    instances = [
        {"id": "abc", "name": INSTANCE_CANONICAL, "connectionStatus": "open"},
    ]

    class _StubSyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url, headers=None, **kwargs):
            return httpx.Response(200, json=instances)

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, headers=None, json=None, **kwargs):
            return httpx.Response(404, json={"error": "Not Found"})

    with patch("core.evolution_client.get_secret", return_value="token"):
        with patch("core.evolution_client.httpx.Client", _StubSyncClient):
            with patch("core.evolution_client.httpx.AsyncClient", _StubAsyncClient):
                import asyncio

                with pytest.raises(EvolutionDeliveryError) as exc_info:
                    asyncio.run(send_image(INSTANCE_RAW, PHONE, b"\x89PNGtest"))

    assert "evolution_http_404" in str(exc_info.value)


def test_send_image_validates_inputs():
    """send_image deve rejeitar instance vazia ou bytes vazios."""
    from core.evolution_client import send_image, EvolutionDeliveryError

    with pytest.raises(EvolutionDeliveryError):
        import asyncio
        asyncio.run(send_image("", PHONE, b"\x89PNGtest"))

    with pytest.raises(EvolutionDeliveryError):
        import asyncio
        asyncio.run(send_image(INSTANCE_RAW, PHONE, b""))
