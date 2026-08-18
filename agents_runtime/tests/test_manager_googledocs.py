"""Tests Nível 2: E2E via arquitetura Jennifer - Google Docs."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestManagerGoogledocsConfig:
    def test_manager_googledocs_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-googledocs" in MANAGER_PROMPTS

    def test_manager_googledocs_prompt_specific_to_docs(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-googledocs"].lower()
        assert "google docs" in prompt or "docs" in prompt
        assert "googledocs_create_document" in prompt
        assert "googledocs_read_document" in prompt

    def test_manager_googledocs_routing(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-googledocs")
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "googledocs_create_document" in tool_names
        assert "googledocs_read_document" in tool_names
        assert "googledocs_search_documents" in tool_names
        assert "googledocs_export_pdf" in tool_names


class TestManagerGoogledocsAllowlist:
    def test_googledocs_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "googledocs" in ALLOWED_TOOLKITS

    def test_googledocs_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("googledocs") is True


class TestManagerGoogledocsKeywordDetection:
    def test_criar_doc_triggers_googledocs(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("criar um doc no google docs") == "googledocs"

    def test_google_docs_keyword_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("leia esse google docs") == "googledocs"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None


class TestManagerGoogledocsE2EFlow:
    def test_create_doc_uses_create_document_tool(self):
        from deepagent_layer.tools import _build_googledocs_tools
        tools = _build_googledocs_tools()
        create_doc_tool = next(t for t in tools if t.name == "googledocs_create_document")
        assert "documento" in create_doc_tool.description.lower() or "doc" in create_doc_tool.description.lower()

    def test_export_pdf_uses_export_tool(self):
        from deepagent_layer.tools import _build_googledocs_tools
        tools = _build_googledocs_tools()
        export_tool = next(t for t in tools if t.name == "googledocs_export_pdf")
        assert "pdf" in export_tool.description.lower()


class TestManagerGoogledocsTier15Dispatch:
    """Fix (18/08/2026): TIER 1.5 dispatch via get_deep_agent (factory removido)."""

    def test_manager_googledocs_built_by_get_deep_agent(self):
        from unittest.mock import patch
        from deepagent_layer.agents import get_deep_agent, MANAGER_PROMPTS
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}):
            agent = get_deep_agent("manager-googledocs")
        assert agent is not None
        assert "manager-googledocs" in MANAGER_PROMPTS

    def test_tier15_dispatches_googledocs(self):
        from orchestrator import _detect_dynamic_toolkit
        assert _detect_dynamic_toolkit("criar um doc no google docs") == "googledocs"
        assert _detect_dynamic_toolkit("buscar no googledocs") == "googledocs"
        assert _detect_dynamic_toolkit("abrir meu googledocs") == "googledocs"


class TestManagerGoogledocsNotBreaking:
    def test_all_existing_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier",
                    "manager-linkedin", "manager-googledocs"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web",
                    "manager-linkedin", "manager-googledocs"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"

    def test_jennifier_returns_empty_tools(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-jennifier")
        assert tools == []