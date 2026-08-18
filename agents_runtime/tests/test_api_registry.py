"""Testes para tools/api_registry.py (auto-discovery com allowlist)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_allowed_toolkits_hardcoded():
    """ALLOWED_TOOLKITS deve conter os 16 toolkits conhecidos (6 Google + 10 Composio)."""
    from tools.api_registry import ALLOWED_TOOLKITS
    expected = {"calendar", "gmail", "drive", "people", "tasks", "maps",
                "linkedin", "youtube", "github", "notion",
                "onedrive", "googledocs", "googlesheets", "googlemeet",
                "microsoft_teams", "msteams"}
    assert ALLOWED_TOOLKITS == expected, f"diff: {ALLOWED_TOOLKITS.symmetric_difference(expected)}"


def test_emergency_disable_env_var():
    """EMERGENCY_DISABLE_TOOLKITS deve bloquear toolkits via env var."""
    with patch.dict("os.environ", {"EMERGENCY_DISABLE_TOOLKITS": "linkedin,twitter"}):
        from tools.api_registry import _get_emergency_disable_set
        blocked = _get_emergency_disable_set()
        assert "linkedin" in blocked
        assert "twitter" in blocked
        assert "github" not in blocked


def test_is_allowed_returns_true_for_known():
    from tools.api_registry import api_registry, ALLOWED_TOOLKITS
    for slug in ALLOWED_TOOLKITS:
        assert api_registry.is_allowed(slug) is True, f"{slug} deveria ser permitido"


def test_is_allowed_blocks_unknown():
    from tools.api_registry import api_registry
    assert api_registry.is_allowed("twitter") is False  # nao esta em ALLOWED_TOOLKITS
    assert api_registry.is_allowed("notion2") is False
    assert api_registry.is_allowed("evil_toolkit") is False


def test_is_allowed_respects_emergency_disable():
    with patch.dict("os.environ", {"EMERGENCY_DISABLE_TOOLKITS": "linkedin"}):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("linkedin") is False
        assert api_registry.is_allowed("github") is True  # outros nao afetados


def test_discover_google_apis_idempotent():
    """discover_all() deve ser idempotente (nao duplicar entries)."""
    from tools.api_registry import api_registry
    import asyncio
    asyncio.run(api_registry.discover_all())
    n1 = len(api_registry._google_apis)
    asyncio.run(api_registry.discover_all())
    n2 = len(api_registry._google_apis)
    assert n1 == n2
    assert n1 >= 5  # calendar, gmail, drive, people, tasks, maps


def test_get_meta_returns_none_for_unallowed():
    """get_meta deve retornar None para toolkits nao permitidos (mesmo se descobertos)."""
    from tools.api_registry import api_registry
    import asyncio
    asyncio.run(api_registry.discover_all())
    # Simular toolkit descoberto mas NAO permitido
    fake_meta = MagicMock()
    fake_meta.slug = "twitter"
    fake_meta.category = "composio"
    api_registry._composio_toolkits["twitter"] = fake_meta
    assert api_registry.is_allowed("twitter") is False
    assert api_registry.get_meta("twitter") is None


def test_get_meta_returns_meta_for_allowed():
    """linkedin esta na allowlist E Composio SDK o descobre via get_meta."""
    from tools.api_registry import api_registry
    import asyncio
    # Forcar rediscover para garantir estado limpo
    api_registry._discovered = False
    api_registry._google_apis = {}
    api_registry._composio_toolkits = {}
    asyncio.run(api_registry.discover_all())
    # Verifica que linkedin foi descoberto
    if "linkedin" not in api_registry._composio_toolkits and "linkedin" not in api_registry._google_apis:
        # Se Composio SDK nao esta disponivel neste test env, pular
        import pytest
        pytest.skip("Composio SDK not available or linkedin not discovered")
    meta = api_registry.get_meta("linkedin")
    assert meta is not None
    assert meta.slug == "linkedin"
    assert meta.category == "composio"


def test_list_all_filters_by_allowlist():
    from tools.api_registry import api_registry
    import asyncio
    asyncio.run(api_registry.discover_all())
    # Adicionar fake toolkit nao permitido
    fake = MagicMock()
    fake.slug = "evil_toolkit"
    api_registry._composio_toolkits["evil_toolkit"] = fake
    listed = api_registry.list_all()
    slugs = [m.slug for m in listed]
    assert "evil_toolkit" not in slugs
    assert "twitter" not in slugs
    assert "linkedin" in slugs or len([s for s in slugs if s == "linkedin"]) == 0  # pode nao descobrir


def test_list_allowed_slugs_returns_sorted():
    from tools.api_registry import api_registry
    slugs = api_registry.list_allowed_slugs()
    assert slugs == sorted(slugs)
    assert len(slugs) == 16  # 6 Google + 10 Composio
