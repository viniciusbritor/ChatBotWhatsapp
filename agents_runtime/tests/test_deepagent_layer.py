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
        assert "manager-web" in managers


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

    def test_web_has_tools(self):
        from deepagent_layer import get_tools_for_manager
        tools = get_tools_for_manager("manager-web")
        names = [t.name for t in tools]
        assert "web_search_tool" in names

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
    def test_build_model_uses_deepseek_base_url(self):
        from unittest.mock import patch, MagicMock
        with patch("langchain_adapter.models.get_secret", return_value="sk-test"):
            with patch("langchain_openai.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()
                from langchain_adapter import build_default_chat_model
                build_default_chat_model()
                call_kwargs = mock_chat.call_args.kwargs
                assert call_kwargs["model"] == "deepseek-v4-flash"
                assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"
                assert call_kwargs["api_key"] == "sk-test"


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
