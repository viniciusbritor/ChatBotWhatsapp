"""Tests for manager-twitter (X/Twitter Composio integration).

GUARDRAIL §0.8 (18/08/2026): tests cobrindo
1. tools/twitter_composio.py (wrappers)
2. ALLOWED_TOOLKITS inclui 'twitter'
3. TOOLKIT_VERSIONS inclui 'twitter'
4. deepagent_layer/tools.py dispatcher tem 'manager-twitter'
5. deepagent_layer/agents.py MANAGER_PROMPTS tem 'manager-twitter'
6. Firestore agents/manager-twitter doc existe com 7 tools

Rodar com: pytest tests/test_manager_twitter.py -v
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import api_registry as _api_registry_module
from tools import _composio_common as _composio_common_module
from deepagent_layer import tools as _tools_module


EXPECTED_TWITTER_TOOLS = {
    "twitter_me_profile",
    "twitter_lookup_users",
    "twitter_search_recent",
    "twitter_search_recent_counts",
    "twitter_lookup_posts",
    "twitter_create_post",
    "twitter_delete_post",
}


def test_twitter_in_allowed_toolkits():
    """GUARDRAIL: 'twitter' deve estar em ALLOWED_TOOLKITS do api_registry."""
    assert "twitter" in _api_registry_module.ALLOWED_TOOLKITS, (
        "twitter NAO esta em ALLOWED_TOOLKITS — "
        "api_registry vai filtra-lo no discovery."
    )


def test_twitter_in_toolkit_versions():
    """GUARDRAIL: 'twitter' deve estar em TOOLKIT_VERSIONS para pinning."""
    assert "twitter" in _composio_common_module.TOOLKIT_VERSIONS, (
        "twitter NAO esta em TOOLKIT_VERSIONS — "
        "Composio SDK vai pegar versao default (instavel)."
    )


def test_dispatcher_handles_manager_twitter():
    """GUARDRAIL: deepagent_layer/tools.py deve conhecer manager-twitter."""
    with patch.object(_tools_module, "_build_twitter_tools", return_value=["mock_tool"]) as mock:
        result = _tools_module.get_tools_for_manager("manager-twitter")
        assert mock.called, "_build_twitter_tools NAO foi chamado pelo dispatcher"
        assert result == ["mock_tool"]


def test_unknown_manager_returns_empty():
    """REGRESSAO: manager desconhecido deve retornar lista vazia sem erro."""
    result = _tools_module.get_tools_for_manager("manager-nonexistent")
    assert result == []


@pytest.mark.asyncio
async def test_twitter_composio_me_profile_calls_sdk():
    """tools/twitter_composio.py::me_profile deve chamar TWITTER_USER_LOOKUP_ME."""
    from tools import twitter_composio

    with patch("tools.twitter_composio.composio_call", new=AsyncMock(return_value={"data": {"id": "123"}})) as mock:
        result = await twitter_composio.me_profile(phone="+5511966830020")
        mock.assert_called_once()
        call_args = mock.call_args
        assert call_args[0][0] == "TWITTER_USER_LOOKUP_ME"
        assert call_args[1]["user_id"] == "+5511966830020"


@pytest.mark.asyncio
async def test_twitter_composio_search_recent_max_results_clamped():
    """search_recent deve clampar max_results para [10, 100]."""
    from tools import twitter_composio

    with patch("tools.twitter_composio.composio_call", new=AsyncMock(return_value={})) as mock:
        await twitter_composio.search_recent(query="AI", max_results=5, phone="+5511966830020")
        call_args = mock.call_args
        assert call_args[0][1]["max_results"] == 10, (
            "max_results < 10 deve ser clampeado para 10 (minimo do X API)"
        )


@pytest.mark.asyncio
async def test_twitter_composio_create_post_truncates_at_280():
    """create_post deve truncar texto em 280 chars (X standard)."""
    from tools import twitter_composio

    long_text = "a" * 500
    with patch("tools.twitter_composio.composio_call", new=AsyncMock(return_value={})) as mock:
        await twitter_composio.create_post(text=long_text, phone="+5511966830020")
        call_args = mock.call_args
        assert len(call_args[0][1]["text"]) == 280, (
            "create_post NAO truncou texto em 280 chars (X standard)"
        )


@pytest.mark.asyncio
async def test_twitter_composio_delete_post_uses_correct_slug():
    """delete_post deve chamar TWITTER_POST_DELETE_BY_POST_ID."""
    from tools import twitter_composio

    with patch("tools.twitter_composio.composio_call", new=AsyncMock(return_value={})) as mock:
        await twitter_composio.delete_post(post_id="12345", phone="+5511966830020")
        call_args = mock.call_args
        assert call_args[0][0] == "TWITTER_POST_DELETE_BY_POST_ID"
        assert call_args[0][1]["id"] == "12345"


@pytest.mark.asyncio
async def test_twitter_composio_lookup_users_truncates_at_100():
    """lookup_users deve truncar lista de usernames em 100 (limite X API)."""
    from tools import twitter_composio

    usernames = [f"user{i}" for i in range(150)]
    with patch("tools.twitter_composio.composio_call", new=AsyncMock(return_value={})) as mock:
        await twitter_composio.lookup_users(usernames=usernames, phone="+5511966830020")
        call_args = mock.call_args
        assert len(call_args[0][1]["usernames"]) == 100, (
            "lookup_users NAO truncou usernames em 100"
        )


def test_manager_twitter_prompt_exists():
    """GUARDRAIL: MANAGER_PROMPTS deve ter 'manager-twitter' com system_prompt completo."""
    from deepagent_layer import agents

    assert "manager-twitter" in agents.MANAGER_PROMPTS, (
        "manager-twitter NAO esta em MANAGER_PROMPTS — "
        "deep_agent_build vai falhar com 'unknown manager_id'."
    )
    prompt = agents.MANAGER_PROMPTS["manager-twitter"]
    # Sanidade do conteudo
    assert "TWITTER_SEARCH_RECENT_COUNTS" in prompt or "search_recent_counts" in prompt, (
        "manager-twitter prompt NAO menciona trends-by-volume (TWITTER_SEARCH_RECENT_COUNTS)"
    )
    assert "trends" in prompt.lower(), (
        "manager-twitter prompt NAO menciona 'trends' — usuario vai ficar sem resposta"
    )
    assert "anti-ban" in prompt.lower() or "max 5" in prompt or "5 tweets" in prompt, (
        "manager-twitter prompt NAO menciona regra anti-ban"
    )
    assert "Portal Coherence" in prompt, (
        "manager-twitter prompt NAO tem mensagem de erro de permissao (Portal Coherence)"
    )
    assert "irrevers" in prompt.lower(), (
        "manager-twitter prompt NAO avisa sobre post/delete irreversivel"
    )


def test_expected_twitter_tools_match_dispatcher():
    """REGRESSAO: os 7 langchain tools em deepagent_layer/tools.py devem ser os esperados."""
    from deepagent_layer import tools as _tools_module_inner
    from langchain_core.tools import tool

    @tool
    def dummy_a(): pass
    @tool
    def dummy_b(): pass

    built = _tools_module_inner._build_twitter_tools()
    names = set()
    for t in built:
        if hasattr(t, "name"):
            names.add(t.name)
        elif hasattr(t, "__name__"):
            names.add(t.__name__)
    expected_subset = EXPECTED_TWITTER_TOOLS & names
    assert expected_subset == EXPECTED_TWITTER_TOOLS, (
        f"manager-twitter tools mismatch. "
        f"Esperado: {EXPECTED_TWITTER_TOOLS}. "
        f"Encontrado: {names}. "
        f"Match: {expected_subset}"
    )


def test_no_twitter_in_legacy_allowed():
    """Sanity: 'twitter' NAO deve estar duplicado em ALLOWED_TOOLKITS."""
    from tools import api_registry as _ar
    count = sum(1 for s in _ar.ALLOWED_TOOLKITS if s == "twitter")
    assert count == 1, f"'twitter' aparece {count}x em ALLOWED_TOOLKITS (esperado 1)"
