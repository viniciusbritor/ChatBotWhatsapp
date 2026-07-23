"""Agentes LangGraph que orquestram o ecossistema Jennifer.

- ``jennifier``: agente principal que fala com o usuario no WhatsApp.
- ``access_guardian``: guardiao nao-deterministico que valida owner + OAuth
  + scopes antes de cada tool Google.
- ``graph``: grafo LangGraph que define o fluxo Jennifer -> Guardian -> Manager -> Reply.
"""
from agent_orchestration import access_guardian, graph, jennifier

JENNIFER_SYSTEM_PROMPT = jennifier.JENNIFER_SYSTEM_PROMPT
TurnContext = jennifier.TurnContext
get_jennifer_model_id = jennifier.get_jennifer_model_id
get_jennifer_fallback_model_id = jennifier.get_jennifer_fallback_model_id

GuardianDecision = access_guardian.GuardianDecision
decide_guardian = access_guardian.decide_guardian
normalize_capability = access_guardian.normalize_capability

build_graph = graph.build_graph
get_compiled_graph = graph.get_compiled_graph
run_turn = graph.run_turn
jennifier_node = graph.jennifier_node
classify_intent_node = graph.classify_intent_node
guard_node = graph.guard_node
manager_node = graph.manager_node
reply_node = graph.reply_node

__all__ = [
    "JENNIFER_SYSTEM_PROMPT",
    "TurnContext",
    "get_jennifer_model_id",
    "get_jennifer_fallback_model_id",
    "GuardianDecision",
    "decide_guardian",
    "normalize_capability",
    "build_graph",
    "get_compiled_graph",
    "run_turn",
    "jennifier_node",
    "classify_intent_node",
    "guard_node",
    "manager_node",
    "reply_node",
]
