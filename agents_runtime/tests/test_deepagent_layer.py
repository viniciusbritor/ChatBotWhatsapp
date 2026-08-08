"""Tests for the DeepAgents integration layer.

These tests verify that the DeepAgents factory builds, caches, and falls
back gracefully when the framework is unavailable. They do NOT make
real LLM calls — all invocations are mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestListSupportedManagers:
    def test_returns_known_managers(self):
        from deepagent_layer import list_supported_managers
        managers = list_supported_managers()
        assert "manager-calendar" in managers
        assert "manager-email" in managers
        assert "manager-drive" in managers


class TestGetToolsForManager:
    def test_calendar_has_tools(self):
        from deepagent_layer import get_tools_for_manager
        tools = get_tools_for_manager("manager-calendar")
        names = [t.name for t in tools]
        assert "list_calendar_events" in names
        assert "create_calendar_event" in names
        assert "calendar_freebusy" in names

    def test_email_has_tools(self):
        from deepagent_layer import get_tools_for_manager
        tools = get_tools_for_manager("manager-email")
        names = [t.name for t in tools]
        assert "search_gmail" in names
        assert "get_gmail_thread" in names
        assert "send_gmail" in names

    def test_drive_has_tools(self):
        from deepagent_layer import get_tools_for_manager
        tools = get_tools_for_manager("manager-drive")
        names = [t.name for t in tools]
        assert "search_drive_files" in names
        assert "list_drive_folder" in names
        assert "create_drive_folder" in names

    def test_unknown_manager_returns_empty(self):
        from deepagent_layer import get_tools_for_manager
        tools = get_tools_for_manager("manager-unknown")
        assert tools == []


class TestGetDeepAgentCaching:
    def test_cache_returns_same_instance(self):
        from deepagent_layer import agents
        agents.reset_cache()
        with patch("deepagent_layer.agents._build_agent") as build:
            build.return_value = MagicMock(name="agent-mock")
            a1 = agents.get_deep_agent("manager-calendar")
            a2 = agents.get_deep_agent("manager-calendar")
            assert a1 is a2
            assert build.call_count == 1
        agents.reset_cache()

    def test_cache_reset(self):
        from deepagent_layer import agents
        with patch("deepagent_layer.agents._build_agent") as build:
            build.return_value = MagicMock(name="agent-mock")
            agents.get_deep_agent("manager-email")
            agents.reset_cache()
            agents.get_deep_agent("manager-email")
            assert build.call_count == 2
        agents.reset_cache()

    def test_unknown_manager_returns_none(self):
        from deepagent_layer.agents import get_deep_agent
        with patch("deepagent_layer.agents._build_agent") as build:
            build.return_value = None
            assert get_deep_agent("manager-fictional") is None


class TestBuildModel:
    def test_build_model_uses_deepseek_base_url(self, monkeypatch):
        from unittest.mock import patch, MagicMock
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        with patch("langchain_adapter.models.get_secret", return_value="sk-test"):
            with patch("langchain_openai.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()
                from langchain_adapter import build_default_chat_model
                build_default_chat_model()
                call_kwargs = mock_chat.call_args.kwargs
                assert call_kwargs["model"] == "deepseek-v4-flash"
                assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"
                assert call_kwargs["api_key"] == "sk-test"

    def test_build_model_respects_env_base_url_override(self, monkeypatch):
        from unittest.mock import patch, MagicMock
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        with patch("langchain_adapter.models.get_secret", return_value="sk-test"):
            with patch("langchain_openai.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()
                from langchain_adapter import build_default_chat_model
                build_default_chat_model()
                call_kwargs = mock_chat.call_args.kwargs
                assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"


class TestExecuteDeepAgent:
    @pytest.mark.asyncio
    async def test_returns_none_when_deepagent_layer_unavailable(self):
        from orchestrator import _execute_deep_agent

        with patch.dict("sys.modules", {"deepagent_layer": None}):
            agent = {"id": "manager-calendar", "role": "manager"}
            payload = {"phone": "5511999999999", "first_name": "Test"}
            result = await _execute_deep_agent(agent, "oi", payload, {})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_manager_unsupported(self):
        from orchestrator import _execute_deep_agent
        from deepagent_layer import agents

        agents.reset_cache()
        with patch("deepagent_layer.agents._build_agent") as build:
            build.return_value = None
            agent = {"id": "manager-fictional", "role": "manager"}
            payload = {"phone": "5511999999999", "first_name": "Test"}
            result = await _execute_deep_agent(agent, "oi", payload, {})
            assert result is None
        agents.reset_cache()

    @pytest.mark.asyncio
    async def test_returns_reply_dict_on_success(self):
        from orchestrator import _execute_deep_agent
        from deepagent_layer import agents

        agents.reset_cache()
        ai_message = MagicMock()
        ai_message.type = "ai"
        ai_message.content = "Voce tem 2 eventos hoje!"
        deep_mock = MagicMock()
        deep_mock.ainvoke = AsyncMock(
            return_value={"messages": [ai_message]}
        )

        with patch("deepagent_layer.agents._build_agent", return_value=deep_mock):
            agent = {"id": "manager-calendar", "role": "manager"}
            payload = {"phone": "5511999999999", "first_name": "Test"}
            result = await _execute_deep_agent(agent, "minha agenda", payload, {})
        agents.reset_cache()

        assert result is not None
        assert "reply" in result
        assert "Voce tem 2 eventos" in result["reply"]
        assert result["metadata"]["runtime"] == "deepagents"
        assert result["metadata"]["agent_id"] == "manager-calendar"

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_timeout(self):
        from orchestrator import _execute_deep_agent
        from deepagent_layer import agents
        import asyncio

        agents.reset_cache()

        deep_mock = MagicMock()
        deep_mock.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("deepagent_layer.agents._build_agent", return_value=deep_mock):
            agent = {"id": "manager-calendar", "role": "manager"}
            payload = {"phone": "5511999999999", "first_name": "Test"}
            result = await _execute_deep_agent(agent, "test", payload, {})
        agents.reset_cache()

        assert result is not None
        assert result["metadata"].get("error") == "deepagent_timeout"

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_empty_response(self):
        from orchestrator import _execute_deep_agent
        from deepagent_layer import agents

        agents.reset_cache()
        deep_mock = MagicMock()
        deep_mock.ainvoke = AsyncMock(
            return_value={"messages": []}
        )

        with patch("deepagent_layer.agents._build_agent", return_value=deep_mock):
            agent = {"id": "manager-calendar", "role": "manager"}
            payload = {"phone": "5511999999999", "first_name": "Test"}
            result = await _execute_deep_agent(agent, "test", payload, {})
        agents.reset_cache()

        assert result is not None
        assert result["metadata"].get("error") == "deepagent_empty"


@pytest.fixture(autouse=True)
def _cleanup_agents_cache():
    from deepagent_layer import agents
    agents.reset_cache()
    yield
    agents.reset_cache()


class TestManagerPromptsAntiHallucination:
    """Garante que os prompts dos 3 managers Google (calendar/email/drive)
    seguem as regras anti-alucinacao de UI admin (bug 01/08/2026).

    O bug original era: o prompt de manager-drive dizia 'NUNCA diga que
    esta sem acesso' enquanto o codigo retornava 'folder_permission_required'
    com URL /admin/users/.../folder-permissions. A LLM inventava uma UI
    'Admin > Usuarios > Permissoes' que nao existe. Estes testes
    protegem contra a regressao.
    """
    # Substrings proibidas NAO podem aparecer FORA de uma guarda
    # 'NAO ...' / 'NUNCA ...'. Ou seja: o prompt pode MENCIONAR a string
    # para ENSINAR a LLM a nao usa-la, mas nao pode usa-la em user-facing.
    NEGATIVE_GUARDS = (
        "NAO invente URLs internas",
        "NAO invente caminhos de menu",
        "NAO exponha termos tecnicos",
        "NUNCA diga",
    )

    @pytest.mark.parametrize("manager_id", [
        "manager-calendar",
        "manager-email",
        "manager-drive",
    ])
    def test_prompt_has_explicit_negation_guards(self, manager_id):
        """Prompt deve conter guardas explicitas 'NAO/NUNCA' sobre
        alucinacao de UI admin. Sem essas guardas, o bug volta."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS[manager_id]
        # Todos os 3 managers devem ter o bloco [ERRO DE PERMISSAO]
        assert "[ERRO DE PERMISSAO]" in prompt, (
            f"{manager_id} must have an explicit [ERRO DE PERMISSAO] block "
            f"to prevent admin UI hallucination"
        )
        assert "NAO invente URLs internas" in prompt
        assert "NAO invente caminhos de menu" in prompt
        assert "NAO exponha termos tecnicos" in prompt

    @pytest.mark.parametrize("manager_id", [
        "manager-calendar",
        "manager-email",
        "manager-drive",
    ])
    def test_recognizes_permission_error_codes(self, manager_id):
        """Prompt deve instruir a LLM a reconhecer os codigos reais de erro."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS[manager_id]
        for token in ("folder_permission_required", "scope_missing", "oauth_missing"):
            assert token in prompt, (
                f"{manager_id} prompt must mention {token!r} so LLM "
                f"recognizes the real tool error code."
            )

    @pytest.mark.parametrize("manager_id", [
        "manager-calendar",
        "manager-email",
        "manager-drive",
    ])
    def test_points_to_real_portal_url(self, manager_id):
        """Prompt deve apontar para o Portal Coherence real (nao inventar URL)."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS[manager_id]
        assert "Portal" in prompt
        assert "coherence" in prompt.lower()

    @pytest.mark.parametrize("manager_id", [
        "manager-calendar",
        "manager-email",
        "manager-drive",
    ])
    def test_no_positive_use_of_admin_urls(self, manager_id):
        """Prompt NAO deve usar /admin/... em contexto positivo (so em NAO/NUNCA)."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS[manager_id]
        # Remove todos os trechos 'NAO ...' ou 'NUNCA ...' e checa se sobra
        # algum /admin/ em contexto positivo.
        sanitized = prompt
        for guard in self.NEGATIVE_GUARDS:
            # remove sentences starting with guard
            import re
            sanitized = re.sub(
                rf"{guard}[^.]*\.",
                "",
                sanitized,
            )
        # Se sobrou /admin/ no texto sanitizado, e uso positivo
        assert "/admin/" not in sanitized, (
            f"{manager_id} prompt uses /admin/ in POSITIVE context "
            f"(outside NAO/NUNCA guards). Bot may leak admin URLs to users."
        )
        # E nao pode ter a frase literal "Admin > Usuarios" como instrucao
        assert "Admin > Usuarios" not in prompt or \
               "NAO invente caminhos de menu ('Admin > Usuarios > Permissoes')" in prompt, (
            f"{manager_id} prompt mentions 'Admin > Usuarios' as instruction "
            f"instead of as anti-hallucination warning."
        )

    def test_legacy_drive_prompt_contradiction_removed(self):
        """manager-drive NAO deve mais ter a frase antiga 'voce SEMPRE tem acesso'
        que conflitava com erros reais de permissao."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-drive"]
        assert "voce SEMPRE tem acesso" not in prompt
        assert "NUNCA diga 'estou sem acesso ao Drive'" not in prompt
