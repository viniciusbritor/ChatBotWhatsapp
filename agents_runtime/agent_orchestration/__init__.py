"""Agentes LangGraph que orquestram o ecossistema Jennifer.

- ``jennifier``: agente principal que fala com o usuario no WhatsApp.
- ``access_guardian``: guardiao nao-deterministico que valida owner + OAuth
  + scopes antes de cada tool Google.
"""
from agent_orchestration import access_guardian, jennifier

JENNIFER_SYSTEM_PROMPT = jennifier.JENNIFER_SYSTEM_PROMPT
TurnContext = jennifier.TurnContext
get_jennifer_model_id = jennifier.get_jennifer_model_id
get_jennifer_fallback_model_id = jennifier.get_jennifer_fallback_model_id

GuardianDecision = access_guardian.GuardianDecision
decide_guardian = access_guardian.decide_guardian
normalize_capability = access_guardian.normalize_capability

__all__ = [
    "JENNIFER_SYSTEM_PROMPT",
    "TurnContext",
    "get_jennifer_model_id",
    "get_jennifer_fallback_model_id",
    "GuardianDecision",
    "decide_guardian",
    "normalize_capability",
]
