"""Testes do FIX bug pre-existente (15/08/2026): MANAGER_PROMPTS precisa ter
uma entry para manager-jennifier e jennifer_pipeline precisa chama-la.

Bug original: o pipeline jennifer_pipeline.py chamava run_agent("jennifier", ...),
mas MANAGER_PROMPTS em deepagent_layer/agents.py nao tinha entry para
"jennifier". _build_agent retornava None, o orchestrator caia em fallback
sem tools e os requests do user (incluindo "busque meu curriculo no gdrive")
nao invocavam tool alguma - gerando loop de drive.search sem
tool_result.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_manager_jennifier_in_manager_prompts():
    """MANAGER_PROMPTS deve ter entry para manager-jennifier."""
    from deepagent_layer.agents import MANAGER_PROMPTS

    assert "manager-jennifier" in MANAGER_PROMPTS, (
        "manager-jennifier nao esta em MANAGER_PROMPTS — _build_agent vai "
        "retornar None e gerar o loop de fallback."
    )
    prompt = MANAGER_PROMPTS["manager-jennifier"]
    assert isinstance(prompt, str)
    assert len(prompt) > 50, "Prompt do manager-jennifier parece vazio"
    # Deve mencionar que e a Jennifer
    assert "Jennifer" in prompt or "jennifer" in prompt.lower()


def test_jennifier_pipeline_calls_manager_jennifier():
    """jennifer_pipeline.run deve chamar run_agent com manager-jennifier,
    nao com jennifier (que nao existe em MANAGER_PROMPTS)."""
    import inspect

    from pipelines import jennifer_pipeline

    source = inspect.getsource(jennifer_pipeline.run)
    assert 'run_agent(\n        "manager-jennifier"' in source, (
        "jennifer_pipeline.run ainda chama 'jennifier' (que nao tem prompt). "
        "Deve chamar 'manager-jennifier'."
    )
    assert '"jennifier"' not in source or '"manager-jennifier"' in source, (
        "jennifer_pipeline.run NAO deve chamar 'jennifier' puro."
    )


def test_build_agent_succeeds_for_manager_jennifier():
    """_build_agent('manager-jennifier') deve retornar um agent (nao None).

    Mocka deepagents + langchain_openai via sys.modules para evitar
    dependencia em CI (estes modulos nao estao instalados).
    """
    import sys
    import types
    from unittest.mock import MagicMock

    # Mock do modulo deepagents.create_deep_agent
    deepagents_module = types.ModuleType("deepagents")
    mock_create = MagicMock(return_value=MagicMock())
    deepagents_module.create_deep_agent = mock_create
    original_deepagents = sys.modules.get("deepagents")
    sys.modules["deepagents"] = deepagents_module

    # Mock do modulo langchain_openai (nao instalado em CI)
    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = MagicMock()
    original_lc_openai = sys.modules.get("langchain_openai")
    sys.modules["langchain_openai"] = langchain_openai

    try:
        from deepagent_layer.agents import _build_agent

        agent = _build_agent("manager-jennifier")

        assert agent is not None, (
            "_build_agent('manager-jennifier') retornou None - o orchestrator "
            "vai cair em fallback sem tools."
        )
        assert mock_create.called, "create_deep_agent deveria ter sido chamado"
    finally:
        if original_deepagents is not None:
            sys.modules["deepagents"] = original_deepagents
        else:
            sys.modules.pop("deepagents", None)
        if original_lc_openai is not None:
            sys.modules["langchain_openai"] = original_lc_openai
        else:
            sys.modules.pop("langchain_openai", None)


def test_get_tools_for_manager_jennifier_returns_list():
    """get_tools_for_manager('manager-jennifier') deve retornar uma lista
    (mesmo que vazia) para nao acionar o warning 'no tools'."""
    from deepagent_layer.tools import get_tools_for_manager

    tools = get_tools_for_manager("manager-jennifier")
    assert isinstance(tools, list), (
        f"get_tools_for_manager deve retornar list, retornou {type(tools).__name__}"
    )


def test_build_agent_logs_warning_for_unknown_manager():
    """_build_agent deve logar warning para managers desconhecidos
    (validacao do caso onde jennifier puro e chamado)."""
    import sys
    import types
    from unittest.mock import MagicMock

    # Mock do modulo deepagents
    deepagents_module = types.ModuleType("deepagents")
    mock_create = MagicMock(return_value=MagicMock())
    deepagents_module.create_deep_agent = mock_create
    original_deepagents = sys.modules.get("deepagents")
    sys.modules["deepagents"] = deepagents_module

    # Mock langchain_openai
    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = MagicMock()
    original_lc_openai = sys.modules.get("langchain_openai")
    sys.modules["langchain_openai"] = langchain_openai

    try:
        from deepagent_layer.agents import _build_agent
        from unittest.mock import patch

        with patch("deepagent_layer.agents.logger") as mock_logger:
            result = _build_agent("manager-completamente-fake")
            assert result is None
            warning_calls = [
                call.args[0]
                for call in mock_logger.warning.call_args_list
                if call.args and "unknown manager_id" in str(call.args[0])
            ]
            assert warning_calls, "Deveria logar warning 'unknown manager_id'"
    finally:
        if original_deepagents is not None:
            sys.modules["deepagents"] = original_deepagents
        else:
            sys.modules.pop("deepagents", None)
        if original_lc_openai is not None:
            sys.modules["langchain_openai"] = original_lc_openai
        else:
            sys.modules.pop("langchain_openai", None)
