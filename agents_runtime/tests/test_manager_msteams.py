"""Tests Nível 2: E2E via arquitetura Jennifer - Microsoft Teams."""
from unittest.mock import MagicMock, patch


class TestManagerMsteamsConfig:
    def test_manager_msteams_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-msteams" in MANAGER_PROMPTS

    def test_manager_msteams_prompt_specific_to_teams(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-msteams"].lower()
        assert "teams" in prompt
        assert "msteams_send_message" in prompt

    def test_manager_msteams_routing(self):
        from deepagent_layer.tools import _build_msteams_tools
        tools = _build_msteams_tools()
        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "msteams_send_message" in tool_names
        assert "msteams_list_channels" in tool_names
        assert "msteams_list_messages" in tool_names


class TestManagerMsteamsAllowlist:
    def test_msteams_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "msteams" in ALLOWED_TOOLKITS

    def test_microsoft_teams_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "microsoft_teams" in ALLOWED_TOOLKITS

    def test_msteams_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("msteams") is True


class TestManagerMsteamsKeywordDetection:
    def test_enviar_mensagem_triggers_msteams(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("enviar mensagem no teams") == "microsoft_teams"

    def test_microsoft_teams_keyword_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("microsoft teams") == "microsoft_teams"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None


class TestManagerMsteamsNotBreaking:
    def test_all_existing_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive",
                    "manager-googlemeet", "manager-msteams"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive",
                    "manager-googlemeet", "manager-msteams"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"