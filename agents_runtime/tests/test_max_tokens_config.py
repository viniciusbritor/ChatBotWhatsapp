"""Tests para LLM_MAX_TOKENS_* no orchestrator."""


def test_default_max_tokens_constants():
    """Valores default dos max_tokens por tipo de agent."""
    from orchestrator import LLM_MAX_TOKENS_MANAGER, LLM_MAX_TOKENS_DEFAULT

    assert LLM_MAX_TOKENS_MANAGER == 1500
    assert LLM_MAX_TOKENS_DEFAULT == 500


def test_max_tokens_env_override(monkeypatch):
    """Env vars sobrescrevem defaults."""
    monkeypatch.setenv("LLM_MAX_TOKENS_MANAGER", "2000")
    monkeypatch.setenv("LLM_MAX_TOKENS_DEFAULT", "800")

    import importlib
    import orchestrator
    importlib.reload(orchestrator)

    assert orchestrator.LLM_MAX_TOKENS_MANAGER == 2000
    assert orchestrator.LLM_MAX_TOKENS_DEFAULT == 800

    importlib.reload(orchestrator)


def test_max_tokens_manager_used_for_tool_calls(monkeypatch):
    """LLM com tools (manager-*) usa LLM_MAX_TOKENS_MANAGER."""
    from unittest.mock import MagicMock

    from orchestrator import LLM_MAX_TOKENS_MANAGER

    captured = {}

    async def fake_chat_with_tools(**kwargs):
        captured.update(kwargs)
        return {"reply": "ok", "delay_ms": 0, "presence": "composing", "metadata": {}}

    async def fake_chat(**kwargs):
        captured.update(kwargs)
        return {"reply": "ok", "delay_ms": 0, "presence": "composing", "metadata": {}}

    fake_llm = MagicMock()
    fake_llm.chat_with_tools = fake_chat_with_tools
    fake_llm.chat = fake_chat

    tools_schema = [{"name": "x", "description": "y", "parameters": {}}]

    async def tool_executor(name, args):
        return "{}"

    async def run_with_tools():
        return await fake_chat_with_tools(
            system_prompt="", user_prompt="",
            tools=tools_schema, tool_executor=tool_executor,
            model="deepseek-v4-flash", temperature=0.7,
            max_tokens=LLM_MAX_TOKENS_MANAGER,
            thinking_disabled=True, max_tool_rounds=5,
        )

    import asyncio
    asyncio.run(run_with_tools())
    assert captured["max_tokens"] == LLM_MAX_TOKENS_MANAGER
