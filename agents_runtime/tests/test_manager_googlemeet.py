"""Tests Nível 2: E2E via arquitetura Jennifer - Google Meet."""
from unittest.mock import MagicMock, patch


class TestManagerGooglemeetConfig:
    def test_manager_googlemeet_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-googlemeet" in MANAGER_PROMPTS

    def test_manager_googlemeet_prompt_specific_to_meet(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-googlemeet"].lower()
        assert "meet" in prompt
        assert "googlemeet_create_meeting" in prompt

    def test_manager_googlemeet_routing(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-googlemeet")
        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "googlemeet_create_meeting" in tool_names
        assert "googlemeet_list_meetings" in tool_names
        assert "googlemeet_get_meeting_link" in tool_names


class TestManagerGooglemeetAllowlist:
    def test_googlemeet_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "googlemeet" in ALLOWED_TOOLKITS

    def test_googlemeet_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("googlemeet") is True


class TestManagerGooglemeetKeywordDetection:
    def test_criar_reuniao_triggers_googlemeet(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("criar reuniao no google meet") == "googlemeet"

    def test_google_meet_keyword_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("agendar chamada no google meet") == "googlemeet"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None


class TestManagerGooglemeetNotBreaking:
    def test_all_existing_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive",
                    "manager-googlemeet"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive",
                    "manager-googlemeet"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"