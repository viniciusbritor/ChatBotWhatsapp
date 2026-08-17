"""Tests Nível 2: E2E via arquitetura Jennifer - OneDrive."""
from unittest.mock import MagicMock, patch


class TestManagerOnedriveConfig:
    def test_manager_onedrive_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-onedrive" in MANAGER_PROMPTS

    def test_manager_onedrive_prompt_specific_to_onedrive(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-onedrive"].lower()
        assert "onedrive" in prompt
        assert "onedrive_list_items" in prompt

    def test_manager_onedrive_routing(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-onedrive")
        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "onedrive_list_items" in tool_names
        assert "onedrive_list_folder_children" in tool_names
        assert "onedrive_list_drives" in tool_names


class TestManagerOnedriveAllowlist:
    def test_onedrive_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "onedrive" in ALLOWED_TOOLKITS

    def test_onedrive_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("onedrive") is True


class TestManagerOnedriveKeywordDetection:
    def test_listar_arquivos_triggers_onedrive(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("listar arquivos no onedrive") == "onedrive"

    def test_onedrive_keyword_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("mostre meu onedrive") == "onedrive"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None


class TestManagerOnedriveE2EFlow:
    def test_list_items_tool_description(self):
        from deepagent_layer.tools import _build_onedrive_tools
        tools = _build_onedrive_tools()
        list_items_tool = next(t for t in tools if t.name == "onedrive_list_items")
        assert "item" in list_items_tool.description.lower() or "arquivo" in list_items_tool.description.lower()


class TestManagerOnedriveNotBreaking:
    def test_all_existing_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets", "manager-onedrive"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"