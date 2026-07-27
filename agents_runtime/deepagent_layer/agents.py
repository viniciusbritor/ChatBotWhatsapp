"""DeepAgents factory.

Creates one ``CompiledStateGraph`` per manager (calendar, email, drive, web)
using LangChain's ``create_deep_agent``. Each agent:

- Uses DeepSeek v4-flash as the LLM (single-provider, Fase K).
- Wraps the existing ``tools/google_*.py`` functions as LangChain tools.
- Has a dedicated ``system_prompt`` derived from the Firestore agent record.
- Returns a tool-calling agent with built-in context offloading.

The DeepAgents harness handles:
- Tool calling loop (no manual loop in ``core/llm_provider``)
- Sub-agent spawning for parallel tool calls
- Automatic context summarization for long conversations
- ``interrupt_on`` support for destructive tools (Phase 2, not yet enabled)

The StateGraph (Fase H) continues to own the access_guardian flow. The
``manager_node`` in ``agent_orchestration/graph.py`` calls the appropriate
deep agent based on intent.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


AGENT_MODEL = os.getenv("JENNIFER_MODEL_ID", "deepseek-v4-flash")


MANAGER_PROMPTS: Dict[str, str] = {
    "manager-calendar": (
        "Voce e o assistente de agenda da Jennifer. Tom caloroso e direto, como colega prestativo. "
        "Use frases naturais em portugues brasileiro: 'Voce tem 3 compromissos hoje!', "
        "'Sua reuniao comeca as 10h.', 'Quer que eu te lembre 15min antes?' "
        "Emojis leves: 📅⏰✨. "
        "NUNCA invente compromissos, datas ou participantes. "
        "Se nao ha eventos, diga 'Sua agenda esta livre hoje — aproveita!'. "
        "Use a data atual do contexto da conversa para interpretar pedidos como 'hoje' ou 'amanha'."
    ),
    "manager-email": (
        "Voce e o assistente de email da Jennifer. Tom caloroso e direto, como colega prestativo. "
        "Use frases naturais em portugues brasileiro: 'Achei 3 emails importantes!', "
        "'A Clarissa te mandou isso ontem.', 'Quer que eu responda pra ela?' "
        "Emojis: 📧💌✉️. "
        "Ao listar emails, formate como tabela em bloco ``` com colunas: "
        "Remetente | Assunto | Data. Isso facilita a leitura no WhatsApp. "
        "NUNCA invente remetentes, assuntos ou conteudo. "
        "Se nao encontrou nada relevante, diga 'Sua caixa esta tranquila — nenhum email urgente!'. "
        "Para 'ultimos 3 emails', use a query: 'in:inbox newer_than:30d'."
    ),
    "manager-drive": (
        "Voce e o assistente de documentos da Jennifer. "
        "Voce tem acesso COMPLETO a todos os Google Drives do usuario. "
        "Tom caloroso e direto, como colega prestativo. "
        "Use frases naturais em portugues brasileiro: 'Encontrei! 📁', "
        "'Essa ata e de 15/07.', 'Achei 3 arquivos — quer ver algum?'. "
        "Ao listar arquivos ou drives, formate como tabela em bloco ``` com colunas: "
        "Nome | Tipo | Modificado. Isso facilita a leitura no WhatsApp. "
        "Emojis leves: 📁✨. "
        "NUNCA invente nomes, datas ou conteudo de arquivos. "
        "NUNCA diga 'estou sem acesso ao Drive' — voce SEMPRE tem acesso. "
        "Se nao encontrou, diga: 'Nao achei esse arquivo. Tenta outro nome?'"
    ),
    "manager-web": (
        "Voce e o componente de pesquisa da Jennifer. Use Serper.dev para buscar na web. "
        "Responda com as fontes (titulo + link) e um resumo breve. "
        "Cache 24h evita chamadas repetidas. "
        "NUNCA se identifique como 'Web Manager' — sempre na voz da Jennifer."
    ),
    "manager-group-rag": (
        "Voce gerencia o conhecimento de grupos do WhatsApp. "
        "Tom caloroso: 'Salvei o documento!', 'Achei isso no conhecimento do grupo:'.\n\n"
        "Ao indexar, SEMPRE pergunte a visibilidade: 'Apenas do grupo (so membros) "
        "ou publico (qualquer pessoa)?'. "
        "Mensagens de feedback intermediario: 'ok. pode deixar' no inicio, "
        "'estou memorizando o conteudo' durante, 'Feito! Feito, quer me perguntar "
        "alguma coisa sobre o arquivo para verificar?' ao final. "
        "Se o tool retornar {\"needs_overwrite\": true}, pergunte: 'Ja tem esse arquivo "
        "salvo. Sobrescrever?'. "
        "Se texto > 50.000 chars, pergunte: 'esse arquivo e grande (X caracteres). Confirma?'\n\n"
        "Tematicas reconhecidas: ata_reuniao, dados_financeiros, apresentacao, "
        "contrato, documentacao. "
        "Tematicas agrupam: ata|reuniao, planilha|custo|xlsx, pptx|slides, "
        "contrato|legal, manual|tutorial."
    ),
}


def _build_model():
    """Return the LangChain chat model for DeepSeek v4-flash.

    Delegates to ``langchain_adapter.build_default_chat_model`` so the
    endpoint, API key, and base URL are configured in one place.
    """
    from langchain_adapter import build_default_chat_model
    return build_default_chat_model()


def _build_agent(manager_id: str):
    """Build a single deep agent for the given manager.

    Returns ``None`` if the framework is unavailable or the manager is unknown.
    """
    from deepagents import create_deep_agent
    from deepagent_layer.tools import get_tools_for_manager

    if manager_id not in MANAGER_PROMPTS:
        logger.warning("unknown manager_id=%s", manager_id)
        return None

    system_prompt = MANAGER_PROMPTS[manager_id]
    tools = get_tools_for_manager(manager_id)
    if not tools:
        logger.warning("no tools for manager_id=%s", manager_id)
        return None

    try:
        model = _build_model()
        agent = create_deep_agent(
            model=model,
            system_prompt=system_prompt,
            tools=tools,
        )
        logger.info(
            "deep_agent_built manager_id=%s model=%s tools=%d",
            manager_id, AGENT_MODEL, len(tools),
        )
        return agent
    except Exception:
        logger.exception("deep_agent_build_failed manager_id=%s", manager_id)
        return None


_agents_cache: Dict[str, Any] = {}


def get_deep_agent(manager_id: str):
    """Return a cached deep agent for the given manager, building on first access.

    The cache avoids paying the DeepAgents build cost on every turn. Cache
    invalidation can be added later (e.g. on prompt change) if needed.
    """
    if manager_id in _agents_cache:
        return _agents_cache[manager_id]
    agent = _build_agent(manager_id)
    if agent is not None:
        _agents_cache[manager_id] = agent
    return agent


def reset_cache() -> None:
    """Clear the agent cache (useful for tests and for hot-reloading the agent)."""
    _agents_cache.clear()


def list_supported_managers() -> list[str]:
    """Return the list of manager_ids with deep agents available."""
    return list(MANAGER_PROMPTS.keys())
