"""Testes para deepagent_layer/dynamic_manager_factory.py."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_get_or_create_returns_none_for_not_allowed():
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
        mock_reg.is_allowed.return_value = False
        result = dynamic_factory.get_or_create("twitter")
    assert result is None


def test_get_or_create_returns_none_for_unknown_meta():
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
        mock_reg.is_allowed.return_value = True
        mock_reg.get_meta.return_value = None
        result = dynamic_factory.get_or_create("unknown_tool")
    assert result is None


def test_get_or_create_returns_none_when_module_missing():
    """Se o modulo tools/X_composio.py nao existe, retorna None."""
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
        mock_reg.is_allowed.return_value = True
        mock_meta = MagicMock()
        mock_meta.slug = "fake_tool"
        mock_meta.module_path = "tools.fake_tool_composio"  # nao existe
        mock_reg.get_meta.return_value = mock_meta
        result = dynamic_factory.get_or_create("fake_tool")
    assert result is None


def test_cache_hit_returns_same_instance():
    """A segunda chamada para o mesmo slug retorna instancia cacheada."""
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    dynamic_factory.clear_cache()
    with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg, \
         patch("deepagent_layer.dynamic_manager_factory.DynamicManagerFactory._build_agent") as mock_build:
        mock_reg.is_allowed.return_value = True
        mock_meta = MagicMock()
        mock_meta.slug = "linkedin"
        mock_meta.module_path = "tools.linkedin_composio"
        mock_meta.category = "composio"
        mock_meta.name = "LinkedIn"
        mock_reg.get_meta.return_value = mock_meta

        mock_agent = MagicMock()
        mock_build.return_value = mock_agent

        # Pre-popular cache
        first = dynamic_factory.get_or_create("linkedin")
        second = dynamic_factory.get_or_create("linkedin")

    assert first is mock_agent
    assert second is mock_agent
    assert mock_build.call_count == 1  # chamado apenas uma vez


def test_lru_eviction():
    """Quando o cache excede o limite, evict o menos usado."""
    from deepagent_layer.dynamic_manager_factory import dynamic_factory, _MAX_CACHE_SIZE
    dynamic_factory.clear_cache()
    with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg, \
         patch("deepagent_layer.dynamic_manager_factory.DynamicManagerFactory._build_agent") as mock_build:
        mock_reg.is_allowed.return_value = True
        mock_build.return_value = MagicMock()

        # Criar _MAX_CACHE_SIZE + 5 managers
        for i in range(_MAX_CACHE_SIZE + 5):
            mock_meta = MagicMock()
            mock_meta.slug = f"tool_{i}"
            mock_meta.module_path = f"tools.tool_{i}_composio"
            mock_meta.category = "composio"
            mock_meta.name = f"Tool {i}"
            mock_reg.get_meta.return_value = mock_meta
            dynamic_factory.get_or_create(f"tool_{i}")

        stats = dynamic_factory.get_cache_stats()
        # Cache deve ter no maximo _MAX_CACHE_SIZE
        assert stats["size"] <= _MAX_CACHE_SIZE


def test_invalidate_specific_slug():
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    dynamic_factory.clear_cache()
    dynamic_factory._cache["linkedin"] = MagicMock()
    assert dynamic_factory.invalidate("linkedin") is True
    assert "linkedin" not in dynamic_factory._cache
    assert dynamic_factory.invalidate("linkedin") is False  # ja nao existe


def test_clear_cache():
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    dynamic_factory._cache["a"] = MagicMock()
    dynamic_factory._cache["b"] = MagicMock()
    dynamic_factory.clear_cache()
    assert len(dynamic_factory._cache) == 0


def test_get_cache_stats():
    from deepagent_layer.dynamic_manager_factory import dynamic_factory
    dynamic_factory.clear_cache()
    stats = dynamic_factory.get_cache_stats()
    assert "size" in stats
    assert "max_size" in stats
    assert "cached_slugs" in stats
    assert stats["size"] == 0


def test_build_system_prompt_template():
    """Template fixo baseado em metadados."""
    from deepagent_layer.dynamic_manager_factory import _build_system_prompt
    from tools.api_registry import ApiMeta
    meta = ApiMeta(
        slug="linkedin",
        name="LinkedIn",
        category="composio",
        description="LinkedIn via Composio (perfil, posts, artigos)",
        auth_type="composio_user_id",
    )
    prompt = _build_system_prompt(meta)
    assert "LinkedIn" in prompt
    assert "composio" in prompt
    assert "Jennifer" in prompt
    assert "portugues brasileiro" in prompt.lower()


def test_discover_async_funcs_skips_private():
    """Funcao async privada (comeca com _) nao deve ser descoberta."""
    from deepagent_layer.dynamic_manager_factory import _discover_async_funcs

    mod = MagicMock()
    public_func = MagicMock()
    public_func.__name__ = "my_profile"
    private_func = MagicMock()
    private_func.__name__ = "_helper"

    with patch("inspect.getmembers", return_value=[
        ("my_profile", public_func),
        ("_helper", private_func),
        ("ClassName", MagicMock),  # nao coroutine
    ]):
        with patch("inspect.iscoroutinefunction", side_effect=lambda x: x in [public_func]):
            funcs = _discover_async_funcs(mod)
    assert len(funcs) == 1
    assert funcs[0][0] == "my_profile"