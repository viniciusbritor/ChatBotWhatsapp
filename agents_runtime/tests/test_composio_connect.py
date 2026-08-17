"""Testes para o cache TTL 120s de composio_connect.get_status (Guardrail §0.7)."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cache():
    """Limpa cache em memoria antes de cada teste."""
    from tools import composio_connect
    composio_connect._STATUS_CACHE.clear()
    yield
    composio_connect._STATUS_CACHE.clear()


@pytest.mark.asyncio
async def test_cache_ttl_hits_within_window():
    """Dentro de 120s, get_status NAO chama a API Composio de novo."""
    from tools import composio_connect

    fake_config = MagicMock()
    fake_config.toolkit.slug = "youtube"
    fake_config.name = "YouTube"
    fake_config.id = "cfg-youtube"

    fake_acct = MagicMock()
    fake_acct.toolkit.slug = "youtube"
    fake_acct.id = "acct-youtube"

    fake_configs = MagicMock(items=[fake_config])
    fake_accts = MagicMock(items=[fake_acct])
    fake_client = MagicMock()
    fake_client.auth_configs.list.return_value = fake_configs
    fake_client.connected_accounts.list.return_value = fake_accts

    with patch.object(composio_connect, "_client", return_value=fake_client):
        r1 = await composio_connect.get_status("5511966830020")
        r2 = await composio_connect.get_status("5511966830020")

    assert r1 == r2
    # API chamada apenas 1x (cache hit na 2a)
    assert fake_client.auth_configs.list.call_count == 1
    assert fake_client.connected_accounts.list.call_count == 1


@pytest.mark.asyncio
async def test_cache_ttl_misses_after_window(monkeypatch):
    """Apos 120s, get_status chama a API Composio de novo."""
    from tools import composio_connect

    fake_config = MagicMock()
    fake_config.toolkit.slug = "youtube"
    fake_config.name = "YouTube"
    fake_config.id = "cfg-youtube"

    fake_acct = MagicMock()
    fake_acct.toolkit.slug = "youtube"
    fake_acct.id = "acct-youtube"

    fake_configs = MagicMock(items=[fake_config])
    fake_accts = MagicMock(items=[fake_acct])
    fake_client = MagicMock()
    fake_client.auth_configs.list.return_value = fake_configs
    fake_client.connected_accounts.list.return_value = fake_accts

    # Forca tempo avancar alem do TTL
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(time, "time", lambda: fake_now["t"])

    with patch.object(composio_connect, "_client", return_value=fake_client):
        await composio_connect.get_status("5511966830020")
        # Dentro da janela
        assert fake_client.auth_configs.list.call_count == 1
        fake_now["t"] += 119  # ainda dentro
        await composio_connect.get_status("5511966830020")
        assert fake_client.auth_configs.list.call_count == 1
        # Passou do TTL
        fake_now["t"] += 2  # 121s total
        await composio_connect.get_status("5511966830020")
        assert fake_client.auth_configs.list.call_count == 2


@pytest.mark.asyncio
async def test_cache_per_user_isolation():
    """Cache por user_id e isolado - chamada para user A NAO afeta user B."""
    from tools import composio_connect

    fake_client = MagicMock()
    fake_client.auth_configs.list.return_value = MagicMock(items=[])
    fake_client.connected_accounts.list.return_value = MagicMock(items=[])

    with patch.object(composio_connect, "_client", return_value=fake_client):
        await composio_connect.get_status("5511966830020")
        await composio_connect.get_status("5511973391993")

    # Cada user chama a API 1x (cache miss na primeira)
    assert fake_client.connected_accounts.list.call_count == 2


def test_invalidate_status_cache_clears_specific_user():
    from tools import composio_connect
    composio_connect._STATUS_CACHE["5511966830020"] = {"ts": time.time(), "data": {"phone": "5511966830020"}}
    composio_connect._STATUS_CACHE["5511973391993"] = {"ts": time.time(), "data": {"phone": "5511973391993"}}

    n = composio_connect.invalidate_status_cache("5511966830020")

    assert n == 1
    assert "5511966830020" not in composio_connect._STATUS_CACHE
    assert "5511973391993" in composio_connect._STATUS_CACHE


def test_invalidate_status_cache_clears_all():
    from tools import composio_connect
    composio_connect._STATUS_CACHE["5511966830020"] = {"ts": time.time(), "data": {"phone": "5511966830020"}}
    composio_connect._STATUS_CACHE["5511973391993"] = {"ts": time.time(), "data": {"phone": "5511973391993"}}

    n = composio_connect.invalidate_status_cache(None)

    assert n == 2
    assert composio_connect._STATUS_CACHE == {}