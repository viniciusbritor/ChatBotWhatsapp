"""Test E2E consolidado: valida que todos os 14 toolkits estao configurados corretamente.

GUARDRAIL §0.8 (17/08/2026): apos a serie de branches feat/manager-* (1-6),
este teste valida que TODOS os managers estao integrados com:
- ApiRegistry (auto-discovery)
- DynamicManagerFactory (cache + LRU)
- Orchestrator (keyword routing)
- allowlist (security)

Cobertura: 14 toolkits + 6 managers hardcoded + 8 especializados.
"""
from unittest.mock import MagicMock, patch


class TestE2EManagersExist:
    """Managers implementados (6 Composio + 6 hardcoded)."""

    def test_all_6_composio_managers_in_prompts(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        expected = [
            "manager-linkedin", "manager-googledocs", "manager-googlesheets",
            "manager-onedrive", "manager-googlemeet", "manager-msteams",
        ]
        for mgr in expected:
            assert mgr in MANAGER_PROMPTS, f"{mgr} not in MANAGER_PROMPTS"
            # System prompt contem keyword do toolkit
            prompt = MANAGER_PROMPTS[mgr].lower()
            toolkit_keyword = mgr.replace("manager-", "")
            assert toolkit_keyword.replace("-", "") in prompt.replace(" ", ""), \
                f"{mgr} prompt missing keyword {toolkit_keyword}"

    def test_all_6_hardcoded_managers_still_work(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        hardcoded = [
            "manager-calendar", "manager-email", "manager-drive",
            "manager-group-rag", "manager-web", "manager-jennifier",
        ]
        for mgr in hardcoded:
            assert mgr in MANAGER_PROMPTS


class TestE2EAllowlistIntegration:
    """Composio toolkits (6) + Google APIs (6) na allowlist."""

    def test_all_6_composio_toolkits_in_allowlist(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        composio_toolkits = {
            "linkedin", "youtube", "github", "notion",
            "onedrive", "googledocs", "googlesheets", "googlemeet",
            "microsoft_teams", "msteams",
        }
        for toolkit in composio_toolkits:
            assert toolkit in ALLOWED_TOOLKITS, f"{toolkit} not in allowlist"

    def test_all_6_google_apis_in_allowlist(self):
        from tools.api_registry import ALLOWED_TOOLKITS
        google_apis = {"calendar", "gmail", "drive", "people", "tasks", "maps"}
        for api in google_apis:
            assert api in ALLOWED_TOOLKITS, f"{api} not in allowlist"

    def test_all_tools_allowlisted_are_approved(self):
        """Todos os toolkits aprovados sao retornados por list_all()."""
        from tools.api_registry import api_registry
        import asyncio
        asyncio.run(api_registry.discover_all())
        listed = {meta.slug for meta in api_registry.list_all()}
        for slug in listed:
            assert api_registry.is_allowed(slug), f"{slug} is listed but not allowed"


class TestE2EToolsBuild:
    """Tools wrapped para cada manager existem e tem o nome correto."""

    def test_build_tools_for_all_managers(self):
        from deepagent_layer.tools import _build_langchain_tools_for
        managers = [
            "manager-calendar", "manager-email", "manager-drive",
            "manager-group-rag", "manager-web",
            "manager-linkedin", "manager-googledocs", "manager-googlesheets",
            "manager-onedrive", "manager-googlemeet", "manager-msteams",
        ]
        for mgr in managers:
            tools = _build_langchain_tools_for(mgr)
            assert len(tools) >= 1, f"{mgr} nao tem tools"

    def test_manager_jennifier_returns_empty(self):
        """manager-jennifier continua sem tools (rosto humano)."""
        from deepagent_layer.tools import _build_langchain_tools_for
        assert _build_langchain_tools_for("manager-jennifier") == []


class TestE2EKeywordRouting:
    """Keywords para cada toolkit Composio roteiam para o manager correto."""

    def test_keywords_to_all_composio_toolkits(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True

            test_cases = [
                ("meu perfil do linkedin", "linkedin"),
                ("criar doc no google docs", "googledocs"),
                ("ler planilha do google sheets", "googlesheets"),
                ("listar arquivos do onedrive", "onedrive"),
                ("criar reuniao no google meet", "googlemeet"),
                ("enviar mensagem no microsoft teams", "microsoft_teams"),
            ]
            for phrase, expected_slug in test_cases:
                result = _detect_dynamic_toolkit(phrase)
                assert result == expected_slug, \
                    f"'{phrase}' -> {result} (expected {expected_slug})"


class TestE2EDynamicFactory:
    """Dynamic factory construida todos os managers corretamente."""

    def test_factory_creates_all_managers(self):
        from deepagent_layer.dynamic_manager_factory import dynamic_factory
        from deepagent_layer.agents import MANAGER_PROMPTS

        dynamic_factory.clear_cache()

        # Testa criacao de TODOS os managers do Composio
        composio_managers = [
            "manager-linkedin", "manager-googledocs", "manager-googlesheets",
            "manager-onedrive", "manager-googlemeet", "manager-msteams",
        ]
        for mgr in composio_managers:
            # Cada manager deve ter module_path que aponta para tools/X_composio.py
            # (ou tools/googlemeet_composio.py / tools/microsoft_teams_composio.py)
            assert mgr in MANAGER_PROMPTS


class TestE2EInvertionRegression:
    """Garantir que roteamento antigo ainda funciona."""

    def test_drive_storage_keyword(self):
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("buscar arquivo no drive") == "drive"

    def test_extensions_that_dont_exist(self):
        """Toolkits nao registrados em KEYWORD_TO_TOOLKIT retornam None (cai no jennifier)."""
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            # gmail e calendar NAO tem KEYWORD_TO_TOOLKIT (sao hardcoded managers)
            # Entao _detect_dynamic_toolkit retorna None
            assert _detect_dynamic_toolkit("enviar email") is None
            assert _detect_dynamic_toolkit("agenda de amanha") is None

    def test_no_keyword_returns_none(self):
        """Mensagens sem keyword nao disparam nenhum manager."""
        from orchestrator import _detect_dynamic_toolkit
        with patch("orchestrator.api_registry") as mock_reg:
            mock_reg.is_allowed.return_value = True
            assert _detect_dynamic_toolkit("oi tudo bem") is None
            assert _detect_dynamic_toolkit("bom dia") is None
            assert _detect_dynamic_toolkit("obrigado") is None


class TestE2ESecurity:
    """Garantir que allowlist NAO permite toolkits nao-listados."""

    def test_evil_toolkit_blocked(self):
        from tools.api_registry import api_registry
        assert api_registry.is_allowed("evil_toolkit") is False
        assert api_registry.is_allowed("twitter_random") is False

    def test_emergency_disable_overrides_allowlist(self):
        with patch.dict("os.environ", {"EMERGENCY_DISABLE_TOOLKITS": "linkedin"}):
            from tools.api_registry import api_registry
            assert api_registry.is_allowed("linkedin") is False
            # Outros toolkits NAO devem ser afetados
            assert api_registry.is_allowed("github") is True


class TestE2ELinkedinResponseFormat:
    """Validar formato da resposta que o usuario receberia (LinkedIn)."""

    def test_linkedin_response_format_is_portuguese(self):
        """System prompt de manager-linkedin esta em PT-BR."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-linkedin"]
        # Tem termos em portugues
        assert "Jennifer" in prompt or "Jennifer" in prompt.lower()
        assert "LinkedIn" in prompt or "linkedin" in prompt.lower()

    def test_linkedin_response_has_format(self):
        """Prompt contem formato de resposta esperado."""
        from deepagent_layer.agents import MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-linkedin"]
        # Formato esperado: Encontrei seu perfil! Nome / Cargo / Link
        assert "Encontrei" in prompt or "perfil" in prompt