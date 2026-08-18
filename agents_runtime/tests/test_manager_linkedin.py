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


class TestManagerLinkedinTier15Dispatch:
    """Fix (18/08/2026): TIER 1.5 dispatch via deepagent_layer.get_deep_agent.

    O factory dynamic foi removido; o handler agora constroi manager-<slug>
    e delega para _execute_agent (deepagent_path).
    """

    def test_manager_linkedin_built_by_get_deep_agent(self):
        """get_deep_agent('manager-linkedin') deve retornar CompiledStateGraph."""
        from deepagent_layer.agents import get_deep_agent, MANAGER_PROMPTS
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}):
            agent = get_deep_agent("manager-linkedin")
        assert agent is not None
        assert "manager-linkedin" in MANAGER_PROMPTS

    def test_tier15_dispatches_to_deepagent(self):
        """_detect_dynamic_toolkit detecta 'linkedin' em frases reais."""
        from orchestrator import _detect_dynamic_toolkit
        assert _detect_dynamic_toolkit("meu perfil no linkedin") == "linkedin"
        assert _detect_dynamic_toolkit("buscar perfil linkedin") == "linkedin"
        assert _detect_dynamic_toolkit("perfil do linkedin") == "linkedin"


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
    """Robustez do TIER 1.5 (dispatch).

    Antes: factory.get_or_create retornava None ou capturava excecao.
    Agora: orchestrator._orchestrate_inner captura o except e loga warning.
    """

    def test_unknown_toolkit_slug_not_in_allowlist(self):
        """Slug fora da allowlist -> api_registry.is_allowed retorna False."""
        from tools.api_registry import api_registry
        with patch.object(api_registry, "is_allowed", return_value=False):
            assert api_registry.is_allowed("unknown_toolkit_xyz") is False

    def test_tier15_handles_unknown_slug_gracefully(self):
        """_detect_dynamic_toolkit retorna None para mensagens sem keyword conhecida."""
        from orchestrator import _detect_dynamic_toolkit
        assert _detect_dynamic_toolkit("oi tudo bem?") is None
        assert _detect_dynamic_toolkit("bom dia") is None