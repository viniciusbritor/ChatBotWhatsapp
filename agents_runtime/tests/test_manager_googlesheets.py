"""Tests Nível 2: E2E via arquitetura Jennifer - Google Sheets."""
from unittest.mock import MagicMock, patch


class TestManagerGooglesheetsConfig:
    def test_manager_googlesheets_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-googlesheets" in MANAGER_PROMPTS

    def test_manager_googlesheets_prompt_specific_to_sheets(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-googlesheets"].lower()
        assert "planilha" in prompt or "sheets" in prompt
        assert "googlesheets_read_cells" in prompt
        assert "googlesheets_write_cells" in prompt

    def test_manager_googlesheets_routing(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-googlesheets")
        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "googlesheets_read_cells" in tool_names
        assert "googlesheets_write_cells" in tool_names
        assert "googlesheets_create_spreadsheet" in tool_names


class TestManagerGooglesheetsAllowlist:
    def test_googlesheets_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "googlesheets" in ALLOWED_TOOLKITS

    def test_googlesheets_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("googlesheets") is True


class TestManagerGooglesheetsKeywordDetection:
    def test_ler_planilha_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("ler planilha do google sheets") == "googlesheets"

    def test_google_sheets_keyword_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("me mostre a planilha google sheets") == "googlesheets"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("bom dia") is None


class TestManagerGooglesheetsE2EFlow:
    def test_read_cells_tool_description(self):
        from deepagent_layer.tools import _build_googlesheets_tools
        tools = _build_googlesheets_tools()
        read_tool = next(t for t in tools if t.name == "googlesheets_read_cells")
        assert "planilha" in read_tool.description.lower() or "sheet" in read_tool.description.lower()


class TestManagerGooglesheetsNotBreaking:
    def test_all_existing_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web",
                    "manager-linkedin", "manager-googledocs",
                    "manager-googlesheets"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"