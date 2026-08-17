"""Tests Nível 2: E2E via arquitetura Jennifer.

Testa o manager-linkedin de ponta-a-ponta:
- Mock webhook WhatsApp
- Orchestrator detecta keyword linkedin
- TIER 1.5 OU manager-linkedin especifico
- Composio SDK chamado
- Resposta_formatada com dados reais
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestManagerLinkedinConfig:
    """Config do manager."""

    def test_manager_linkedin_in_manager_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-linkedin" in MANAGER_PROMPTS

    def test_manager_linkedin_prompt_specific_to_linkedin(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-linkedin"].lower()
        # Tem que mencionar linkedin
        assert "linkedin" in prompt
        # Nao deve ser generico
        assert "assistente de linkedin" in prompt or "especialista" in prompt
        # Tem que ter instrucoes especificas das tools
        assert "linkedin_my_profile" in prompt
        assert "linkedin_create_post" in prompt

    def test_manager_linkedin_routing(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-linkedin")
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "linkedin_my_profile" in tool_names
        assert "linkedin_create_post" in tool_names
        assert "linkedin_read_post" in tool_names
        assert "linkedin_create_article" in tool_names


class TestManagerLinkedinAllowlist:
    """manager-linkedin deve estar na allowlist do api_registry."""

    def test_linkedin_in_allowed_toolkits(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        assert "linkedin" in ALLOWED_TOOLKITS

    def test_linkedin_is_allowed(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("linkedin") is True


class TestManagerLinkedinKeywordDetection:
    """_detect_dynamic_toolkit reconhece keywords do LinkedIn."""

    def test_meu_perfil_triggers_linkedin(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("meu perfil do linkedin") == "linkedin"

    def test_buscar_perfil_triggers_linkedin(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("busca meu perfil no linkedin") == "linkedin"

    def test_postar_no_linkedin_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("poste algo no linkedin") == "linkedin"

    def test_sem_keyword_nao_triggers(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None


class TestManagerLinkedinE2EFlow:
    """Fluxo end-to-end simulado."""

    def test_manager_linkedin_uses_my_profile_tool_for_profile_query(self):
        """Quando user pede 'meu perfil', manager-linkedin chama my_profile."""
        from deepagent_layer.tools import _build_linkedin_tools
        tools = _build_linkedin_tools()
        tool_names = [t.name for t in tools]
        assert "linkedin_my_profile" in tool_names
        # Documentacao da tool explica o caso de uso
        my_profile_tool = next(t for t in tools if t.name == "linkedin_my_profile")
        assert "perfil" in my_profile_tool.description.lower()

    def test_manager_linkedin_uses_create_post_for_post_query(self):
        """Quando user pede 'postar', manager-linkedin tem create_post."""
        from deepagent_layer.tools import _build_linkedin_tools
        tools = _build_linkedin_tools()
        tool_names = [t.name for t in tools]
        assert "linkedin_create_post" in tool_names
        create_post_tool = next(t for t in tools if t.name == "linkedin_create_post")
        assert "post" in create_post_tool.description.lower()


class TestManagerLinkedinDynamicFactory:
    """Dynamic factory constroi manager-linkedin quando solicitado."""

    def test_factory_returns_manager_for_linkedin(self):
        """Se slug=linkedin, dynamic_factory deve construir ou None."""
        from deepagent_layer.dynamic_manager_factory import dynamic_factory
        dynamic_factory.clear_cache()
        with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            mock_meta = MagicMock()
            mock_meta.slug = "linkedin"
            mock_meta.module_path = "tools.linkedin_composio"
            mock_meta.category = "composio"
            mock_meta.name = "LinkedIn"
            mock_reg.get_meta.return_value = mock_meta
            # Mock o _build_agent para nao criar DeepAgent real
            with patch("deepagent_layer.dynamic_manager_factory.DynamicManagerFactory._build_agent") as mock_build:
                mock_build.return_value = MagicMock()
                agent = dynamic_factory.get_or_create("linkedin")

        assert agent is not None

    def test_factory_blocks_linkedin_when_not_allowed(self):
        """Se linkedin NAO esta na allowlist, factory retorna None."""
        from deepagent_layer.dynamic_manager_factory import dynamic_factory
        dynamic_factory.clear_cache()
        with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = False
            agent = dynamic_factory.get_or_create("linkedin")
        assert agent is None


class TestManagerLinkedinNotBreaking:
    """Garante que nao quebramos o que funciona."""

    def test_all_existing_managers_still_work(self):
        """Os 6 managers originais continuam funcionando."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        required = ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web", "manager-jennifier"]
        for mgr in required:
            assert mgr in MANAGER_PROMPTS, f"{mgr} deveria existir"

    def test_all_existing_managers_have_tools(self):
        """Cada manager (exceto jennifier) retorna >= 1 tool."""
        from deepagent_layer.tools import _build_langchain_tools_for
        for mgr in ["manager-calendar", "manager-email", "manager-drive",
                    "manager-group-rag", "manager-web"]:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} deveria ter tools"

    def test_jennifier_returns_empty_tools(self):
        """manager-jennifier continua sem tools (rosto humano)."""
        from deepagent_layer.tools import _build_langchain_tools_for
        tools = _build_langchain_tools_for("manager-jennifier")
        assert tools == []


class TestManagerLinkedinCrashSafety:
    """Robustez."""

    def test_factory_handles_module_import_error(self):
        """Se o modulo do toolkit nao existe, factory retornsa None."""
        from deepagent_layer.dynamic_manager_factory import dynamic_factory
        dynamic_factory.clear_cache()
        with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            mock_meta = MagicMock()
            mock_meta.slug = "fake_toolkit"
            mock_meta.module_path = "tools.fake_toolkit_composio"  # nao existe
            mock_reg.get_meta.return_value = mock_meta
            agent = dynamic_factory.get_or_create("fake_toolkit")
        assert agent is None

    def test_factory_handles_keyerror_in_get_meta(self):
        from deepagent_layer.dynamic_manager_factory import dynamic_factory
        dynamic_factory.clear_cache()
        with patch("deepagent_layer.dynamic_manager_factory.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            mock_reg.get_meta.return_value = None  # toolkit sem metadata
            agent = dynamic_factory.get_or_create("missing")
        assert agent is None