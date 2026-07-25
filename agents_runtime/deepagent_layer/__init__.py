"""DeepAgents integration layer for ChatBotWhatsapp.

This module wraps the LangChain ``create_deep_agent`` factory for the four
managers (calendar, email, drive, web). It is consumed by the
``agent_orchestration.graph.manager_node`` in place of the manual tool
loop in ``orchestrator._execute_agent``.

Public surface:
- ``deepagent_layer.agents.get_deep_agent(manager_id)``: cached factory.
- ``deepagent_layer.agents.list_supported_managers()``: list of manager_ids.
- ``deepagent_layer.tools.get_tools_for_manager(manager_id)``: list of LangChain tools.
"""
from deepagent_layer.agents import get_deep_agent, list_supported_managers, reset_cache
from deepagent_layer.tools import get_tools_for_manager

__all__ = [
    "get_deep_agent",
    "get_tools_for_manager",
    "list_supported_managers",
    "reset_cache",
]
