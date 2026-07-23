"""Regression tests for core/evolution_client.py endpoints.

Covers:
- sendText with the v2 singular mark endpoint
- markMessageAsRead (singular) with v2 payload
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
