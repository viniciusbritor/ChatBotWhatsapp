"""Jennifer orchestrator agent definition.

Jennifer is the principal agent that talks to the user on WhatsApp. She
delegates Google requests to the manager specialists (calendar, drive,
gmail) after the ``access_guardian`` subagent validates that:

1. The inbound phone matches the owner phone of the Evolution instance.
2. The user has a valid Google OAuth token linked.
3. The requested capability is covered by the granted scopes.

The orchestration graph itself lives in :mod:`agent_orchestration.graph`.
This module just exposes Jennifer's system prompt and a thin wrapper used
by the graph node.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


JENNIFER_SYSTEM_PROMPT = (
    "Voce e a Jennifer. Colabora com equipes e pessoas no WhatsApp. "
    "Conhece quem conversa com voce pelo historico no contexto. "
    "Tom: calorosa, direta, profissional, proxima - como colega de equipe confiavel. "
    "NUNCA diga 'assistente corporativa', 'startup', 'OmniChannel' ou 'Brasil-AI'. "
    "NUNCA aja como primeira conversa.\n\n"
    "REGRAS: use so primeiro nome. Apelido so com consentimento explicito. "
    "NUNCA improvise nada depreciativo. Anti-alucinacao: jamais invente dados, datas, nomes. "
    "Mensagens: max 4 linhas, pt-BR, 1-2 emojis. Fuso America/Sao_Paulo. LGPD: nao exponha PII.\n\n"
    "Delega para managers: calendar, drive, email, web. "
    "SEMPRE passe o telefone (phone) e a instancia (instance) ao chamar tools Google. "
    "Antes de chamar qualquer tool Google, o agente 'access_guardian' valida autorizacao.\n\n"
    "[CHAT HISTORY]\n"
    "Voce tem acesso ao historico completo de conversas com cada usuario. "
    "Use 'chat_history.search' para buscar por topicos ou referencias passadas. "
    "Use 'chat_history.context' para recuperar o fio da conversa recente. "
    "Consulte o historico quando o usuario fizer referencia a algo ja discutido, "
    "como 'voce lembra', 'falamos sobre', 'semana passada', ou 'aquela vez'. "
    "NAO use para saudacoes simples ou conversas triviais."
)


@dataclass
class TurnContext:
    """Contexto carregado pelo agente Jennifer antes de cada turno."""

    instance: str = "jennifer"
    phone: str = ""
    sender_name: str = "user"
    text: str = ""
    first_name: str = ""
    masked_text: str = ""
    remote_jid: str = ""
    intent: Dict[str, bool] = field(default_factory=dict)
    prefetch: Optional[str] = None
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    reply: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    pending_action: Optional[str] = None
    guardian_decision: Optional[Dict[str, Any]] = None
    next_agent: Optional[str] = None

    def as_graph_state(self) -> Dict[str, Any]:
        return {
            "instance": self.instance,
            "phone": self.phone,
            "sender_name": self.sender_name,
            "text": self.text,
            "first_name": self.first_name,
            "masked_text": self.masked_text,
            "remote_jid": self.remote_jid,
            "intent": dict(self.intent),
            "prefetch": self.prefetch,
            "tools_called": list(self.tools_called),
            "reply": self.reply,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "pending_action": self.pending_action,
            "guardian_decision": dict(self.guardian_decision) if self.guardian_decision else None,
            "next_agent": self.next_agent,
        }


def get_jennifer_model_id() -> str:
    return os.getenv("JENNIFER_MODEL_ID", "deepseek-v4-flash")


def get_jennifer_fallback_model_id() -> str:
    return os.getenv("JENNIFER_FALLBACK_MODEL_ID", "gemini-2.5-flash")
