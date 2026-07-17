"""Orchestrator - routes incoming messages to appropriate agent.

Flow:
1. Receive message from /chat endpoint
2. Detect special cases (audio, groups, morality, learning)
3. Determine orchestrator agent (jennifier)
4. Check if message has keywords/intent for direct delegation
5. Call LLM with orchestrator system_prompt + tools
6. If LLM emits function_call, delegate to manager/specialist
7. Return final response with delay_ms

This is a simplified orchestrator (not full Agno Team) for clarity and testability.
"""
import os
import re
import json
import logging
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.escalation import compute_confidence_score, should_escalate
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.commands import detect_command, apply_command
from tool_registry import TOOL_REGISTRY, get_tool, get_tool_schema
from agent_loader import get_agent, get_skill, list_skills, get_user, get_config, has_nickname
from core.audit import log_action

logger = logging.getLogger(__name__)

_interaction_history: List[Dict[str, Any]] = []
MAX_HISTORY = 20


def get_recent_interactions(limit: int = 5) -> List[Dict[str, Any]]:
    """Return the most recent orchestration interactions."""
    return _interaction_history[-limit:]

GROSS_KEYWORDS = [
    "puta", "merda", "caralho", "fdp", "porra",
    "buceta", "viado", "bicha", "desgraça",
    "foder", "fode", "piranha", "vagabunda", "puto",
    "bosta", "porcaria", "desgraçado",
]
ASSAULT_KEYWORDS = [
    "assedio", "abuso", "estupro", "violencia", "agressao",
    "ameaça", "ameaca", "chantagem",
]
CORRECTION_KEYWORDS = [
    "na verdade", "não é assim", "nao e assim", "errado", "errada",
]
CALENDAR_KEYWORDS = [
    "agenda", "reuniao", "evento", "compromisso", "lembrete",
    "calendario", "disponivel", "semana que vem", "proxima semana",
]
DRIVE_KEYWORDS = [
    "drive", "documento", "arquivo", "pasta", "upload",
    "omnichannel", "atividades", "baixar", "encontrar arquivo",
    "meus arquivos", "meus documentos", "buscar arquivo",
    "procurar documento", "lista de arquivos", "mostrar arquivos",
    "ata", "minuta", "relatorio", "apresentação", "apresentacao",
]
EMAIL_KEYWORDS = [
    "email", "e-mail", "caixa de entrada", "gmail",
    "ler email", "enviar email", "ultimos emails",
]
WEB_KEYWORDS = [
    "pesquisar", "buscar na internet", "procure por",
    "o que e", "quem e", "noticia", "significa",
    "busca pra mim", "pesquisa sobre",
]
INTIMACY_KEYWORDS = [
    "me chame de", "pode me chamar de", "meu apelido",
    "meu nome e", "meu nome é", "como devo te chamar",
]


def _get_routing_rules() -> List[Dict[str, Any]]:
    """Load routing rules from Firestore config/routing."""
    config = get_config("routing")
    if config and config.get("rules"):
        return [r for r in config["rules"] if r.get("enabled", True)]
    return []


def _detect_intent(text: str) -> Dict[str, Any]:
    """Detect special intents using hardcoded + Firestore keywords."""
    text_lower = text.lower()
    intent = {
        "is_gross": any(kw in text_lower for kw in GROSS_KEYWORDS),
        "is_assault_related": any(kw in text_lower for kw in ASSAULT_KEYWORDS),
        "is_correction": any(kw in text_lower for kw in CORRECTION_KEYWORDS),
        "is_calendar": any(kw in text_lower for kw in CALENDAR_KEYWORDS),
        "is_drive": any(kw in text_lower for kw in DRIVE_KEYWORDS),
        "is_email": any(kw in text_lower for kw in EMAIL_KEYWORDS),
        "is_web_search": any(kw in text_lower for kw in WEB_KEYWORDS),
        "is_intimacy": any(kw in text_lower for kw in INTIMACY_KEYWORDS),
    }
    rules = _get_routing_rules()
    for rule in rules:
        agent_id = rule.get("agent_id", "")
        keywords = rule.get("keywords", [])
        if any(kw in text_lower for kw in keywords):
            intent[f"matched_{agent_id}"] = True
    return intent


def _build_skills_section(skill_ids: List[str]) -> str:
    """Build skills content section for system prompt."""
    if not skill_ids:
        return ""
    parts = ["\n\n# Skills ativas:"]
    for sid in skill_ids:
        skill = get_skill(sid)
        if skill and skill.get("enabled", True):
            parts.append(f"\n## {skill['name']}\n{skill.get('content', '')}")
    return "\n".join(parts)


async def _get_orchestrator(instance: str) -> Optional[str]:
    """Get orchestrator with cold-start retry."""
    orchestrator_id = _select_orchestrator_agent(instance)
    if not orchestrator_id:
        await asyncio.sleep(3)
        orchestrator_id = _select_orchestrator_agent(instance)
    return orchestrator_id


def _extract_first_name(sender_name: str) -> str:
    """Extrai o primeiro nome do sender_name."""
    if not sender_name or sender_name == "user":
        return ""
    parts = sender_name.strip().split()
    return parts[0] if parts else sender_name


def _select_orchestrator_agent(instance: str) -> Optional[str]:
    """Select which orchestrator agent to use for this instance."""
    for agent_id, agent in _iter_agents():
        if agent.get("role") == "orchestrator" and agent.get("enabled", True):
            if instance.lower() in [i.lower() for i in agent.get("instances", [])] or not agent.get("instances"):
                return agent_id
    return None


def _iter_agents():
    """Helper to iterate over agents cache (avoids circular import)."""
    from agent_loader import _agents_cache
    for agent_id, agent in _agents_cache.items():
        yield agent_id, agent


def _resolve_agent_for_intent(intent: Dict[str, Any], instance: str) -> Optional[str]:
    """Resolve which agent should handle this intent (hardcoded + dynamic from Firestore)."""
    if intent["is_gross"] or intent["is_assault_related"]:
        return "agent-morality"
    if intent["is_correction"]:
        return "agent-learning"
    if intent["is_intimacy"]:
        return "agent-intimacy"
    if intent["is_calendar"]:
        return "manager-calendar"
    if intent["is_drive"]:
        return "manager-drive"
    if intent["is_email"]:
        return "manager-email"
    if intent["is_web_search"]:
        return "manager-web"

    rules = _get_routing_rules()
    for rule in sorted(rules, key=lambda r: r.get("priority", 99)):
        agent_id = rule.get("agent_id", "")
        if intent.get(f"matched_{agent_id}"):
            return agent_id

    return None


PERSONAL_INTENTS = {"is_calendar", "is_drive", "is_email"}


def _is_personal_intent(intent: Dict[str, Any]) -> bool:
    """Check if intent involves personal data (calendar, email, drive)."""
    return any(intent.get(k) for k in PERSONAL_INTENTS)


def _is_group_message(payload: Dict[str, Any]) -> bool:
    """Check if message is from a WhatsApp group."""
    extra = payload.get("extra", {})
    remote_jid = extra.get("remote_jid", payload.get("phone", ""))
    return "@g.us" in str(remote_jid)


def _extract_group_jid(payload: Dict[str, Any]) -> str:
    """Extract group JID from payload."""
    extra = payload.get("extra", {})
    remote_jid = extra.get("remote_jid", "")
    if "@g.us" in str(remote_jid):
        return remote_jid.split("@")[0] + "@g.us"
    return ""


def _prefetch_nickname(first_name: str) -> Optional[str]:
    """G7: Pre-resolve apelido do JSON estatico, sem LLM tool loop."""
    try:
        import json as _json
        data_file = os.path.join(
            os.path.dirname(__file__), "data", "nicknames.json"
        )
        with open(data_file, "r", encoding="utf-8") as f:
            data = _json.load(f)
        normalized = first_name.strip().title()
        nicknames = data.get(normalized, [])
        if nicknames:
            return nicknames[0]
        if not data.get("_comment"):
            # fallback: gera diminutivo
            if len(normalized) >= 8:
                return normalized[:4]
            elif len(normalized) >= 6:
                return normalized[:3]
            elif len(normalized) >= 3:
                return normalized[:2]
            else:
                return normalized
    except Exception:
        pass
    return None


def _generate_diminutive(name: str) -> str:
    """Fallback: gera diminutivo carinhoso do primeiro nome."""
    if len(name) <= 3:
        return name + name[-1]
    elif len(name) <= 6:
        return name[:2]
    else:
        return name[:4]


def _is_read_query(text: str) -> bool:
    """Fase B: detecta se query eh de leitura (pre-fetch) ou escrita (tool loop)."""
    text_lower = text.lower()
    write_kw = {"cria", "criar", "envia", "enviar", "manda", "mandar", "agenda", "agendar",
                "marca", "marcar", "deleta", "deletar", "apaga", "apagar", "atualiza", "atualizar",
                "remove", "remover", "sobe", "upload"}
    if any(kw in text_lower for kw in write_kw):
        return False
    return True


def _extract_search_terms(text: str) -> str:
    """Extrai termos relevantes da query do usuario para busca no Drive."""
    stopwords = {"jen", "jennifer", "voce", "pode", "me", "meu", "minha", "meus",
                 "minhas", "um", "uma", "para", "com", "que", "nao", "sim", "por",
                 "favor", "obrigado", "acessar", "consegue", "veja", "traga", "acesse",
                 "busca", "buscar", "encontra", "encontrar", "ache", "achar",
                 "listar", "lista", "mostre", "mostrar", "quero", "preciso",
                 "de", "da", "do", "no", "na", "mais", "a", "o", "e", "se", "ja"}
    words = text.lower().split()
    terms = [w.strip(",.!?;:") for w in words if w.strip(",.!?;:") not in stopwords and len(w.strip(",.!?;:")) > 2]
    return " ".join(terms[:10])


async def _prefetch_calendar(phone: str) -> Optional[str]:
    """Fase B: pre-busca eventos do dia sem LLM."""
    try:
        from tools.google_calendar import list_events
        from datetime import datetime, timezone, timedelta
        brt = timezone(timedelta(hours=-3))
        hoje = datetime.now(brt)
        result = await list_events(
            time_min=hoje.strftime("%Y-%m-%dT00:00:00-03:00"),
            time_max=hoje.strftime("%Y-%m-%dT23:59:59-03:00"),
            max_results=50, phone=phone)
        events = result.get("events", [])
        if not events:
            return None
        return json.dumps(events, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch calendar failed: {e}")
        return None


async def _prefetch_email(phone: str) -> Optional[str]:
    """Fase B: pre-busca ultimos emails sem LLM."""
    try:
        from tools.google_gmail import search_messages
        result = await search_messages("in:inbox newer_than:30d", max_results=10, phone=phone)
        messages = result.get("messages", [])
        if not messages:
            return None
        return json.dumps(messages, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch email failed: {e}")
        return None


async def _prefetch_drive(phone: str, query_text: str = "") -> Optional[str]:
    """Fase B: pre-busca arquivos no Drive sem LLM."""
    try:
        from tools.google_drive import search_files
        result = await search_files(query_text or "", max_results=20, phone=phone)
        files = result.get("files", [])
        if not files:
            return None
        return json.dumps(files, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch drive failed: {e}")
        return None


async def _prefetch_drive_multi(phone: str, text: str) -> Optional[str]:
    """D1: 3 queries paralelas no Drive, usa a com mais resultados."""
    query1 = _extract_search_terms(text)
    query2 = " ".join(w for w in text.lower().split()
                      if len(w.strip(",.!?;:")) > 3)[:5]
    results = await asyncio.gather(
        _prefetch_drive(phone, query1),
        _prefetch_drive(phone, query2),
        _prefetch_drive_docs(phone, query1),
        _prefetch_drive_docs(phone, query2),
        return_exceptions=True,
    )
    best, best_count = None, 0
    for r in results:
        if isinstance(r, str):
            try:
                data = json.loads(r)
                if isinstance(data, list) and len(data) > best_count:
                    best, best_count = r, len(data)
            except Exception:
                pass
    return best


async def _prefetch_drive_docs(phone: str, query_text: str = "") -> Optional[str]:
    """Prefetch so documentos e apresentacoes do Drive (atas, slides)."""
    try:
        from tools.google_drive import search_files
        query_parts = []
        if query_text:
            query_parts.append(f"name contains '{query_text}'")
        query_parts.append("mimeType contains 'document' or mimeType contains 'presentation'")
        result = await search_files(query_text or "", mime_type="application/vnd.google-apps.document", max_results=20, phone=phone)
        alt = await search_files(query_text or "", mime_type="application/vnd.google-apps.presentation", max_results=20, phone=phone)
        all_files = result.get("files", []) + alt.get("files", [])
        if not all_files:
            return None
        seen = set()
        unique = []
        for f in all_files:
            if f["id"] not in seen:
                seen.add(f["id"])
                unique.append(f)
        return json.dumps(unique[:20], ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch drive docs failed: {e}")
        return None


def _has_real_data(prefetch_text: str) -> bool:
    """A1: Retorna True so se prefetch trouxe dados reais (nao mensagens de vazio)."""
    empty_signals = {"nenhum", "não encontrou", "nao encontrou", "sem resultados",
                     "0 resultados", "error", "failed"}
    text_lower = prefetch_text.lower()
    return not any(m in text_lower for m in empty_signals)

ACCEPTANCE_KEYWORDS = {"sim", "pode", "ok", "claro", "aceito", "perfeito", "otimo", "pode sim"}


async def orchestrate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Main orchestration entry point.

    Args:
        payload: {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": "oi",
            "sender_name": "Vinicius",
            "extra": {...}
        }

    Returns:
        {
            "reply": str,
            "delay_ms": int,
            "presence": str,
            "metadata": {
                "agent_id": str,
                "model_used": str,
                "escalated": bool,
                "tool_calls": [...]
            }
        }
    """
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    sender_name = payload.get("sender_name", "user")
    extra = payload.get("extra", {})

    first_name = _extract_first_name(sender_name)
    payload["first_name"] = first_name

    masked_text = mask_pii(text)

    if first_name:
        text_lower = masked_text.lower().strip()
        if any(term in text_lower[:20] for term in ACCEPTANCE_KEYWORDS):
            suggested = _prefetch_nickname(first_name) or _generate_diminutive(first_name)
            try:
                from tools.nickname import set_consent
                await set_consent(phone, first_name, suggested, True)
                logger.info(f"Nickname auto-saved: {phone} -> {suggested}")
                has_nickname.cache = getattr(has_nickname, "cache", {})
                has_nickname.cache[phone] = True
            except Exception as e:
                logger.warning(f"Nickname auto-save failed: {e}")

    intent = _detect_intent(masked_text)
    specialist_id = _resolve_agent_for_intent(intent, instance)

    path = []
    path.append({"step": 1, "phase": "intent_detect", "details": {k: v for k, v in intent.items() if v}})

    if _is_personal_intent(intent) and _is_group_message(payload):
        group_jid = extra.get("remote_jid", "") or _extract_group_jid(payload)
        is_confirmed = False
        if group_jid:
            try:
                from tools.group import get_member_confirmation
                is_confirmed = await get_member_confirmation(group_jid, phone)
            except Exception:
                pass

        if not is_confirmed:
            logger.info(f"Privacy guard: unconfirmed member {phone} in group {group_jid}")
            return {
                "reply": (
                    f"Oi {sender_name}! Voce pediu para acessar informacoes pessoais no grupo. "
                    "Para sua seguranca, preciso que me confirme no privado primeiro. "
                    "Me manda uma mensagem no privado dizendo 'sim' e eu libero o acesso para voce neste grupo. "
                    "Tambem pode confirmar no Portal: https://coherence-portal-test-c5nbfc5meq-uc.a.run.app 🔒"
                ),
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "privacy-guard", "blocked": "group_unconfirmed_member"},
            }

        logger.info(f"Privacy guard: confirmed member {phone} in group {group_jid}, executing")

    if _is_personal_intent(intent) and not get_user(phone):
        logger.info(f"Privacy guard: unregistered user {phone} requesting personal data")
        portal_url = "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app"
        return {
            "reply": f"Oi {sender_name}! Para acessar agenda, emails ou documentos, "
                     f"vincule sua conta no Portal Coherence: {portal_url}\n\n"
                     "Depois, no módulo 'Agentes Omnichannel', vá até a aba 'Usuários' e clique em 'Vincular Agenda'. "
                     "É rapidinho! 🔑",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "privacy-guard", "blocked": "unregistered_user"},
        }

    cmd = detect_command(masked_text)
    if cmd:
        path.append({"step": 2, "phase": "command", "agent": "command-handler", "command": cmd})
        logger.info(f"Proactive command detected from {phone}: {cmd}")
        cmd_result = await apply_command(phone, cmd)
        log_action(
            actor="user",
            action="PROACTIVE_COMMAND",
            target=phone,
            details={"command": cmd, "result": cmd_result},
        )
        result = {
            "reply": cmd_result.get("message", "Comando aplicado."),
            "delay_ms": 0,
            "presence": "paused",
            "metadata": {
                "agent_id": "command-handler",
                "command": cmd,
                "applied": True,
            },
        }
    elif specialist_id:
        agent = get_agent(specialist_id)
        if agent and agent.get("enabled", True):
            agent_copy = dict(agent)
            prefetch_data = None

            if _is_read_query(masked_text):
                try:
                    if intent["is_calendar"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_calendar(phone), timeout=8)
                    elif intent["is_email"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_email(phone), timeout=8)
                    elif intent["is_drive"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_drive_multi(phone, masked_text), timeout=8)
                except asyncio.TimeoutError:
                    logger.warning(f"Prefetch timeout for {specialist_id}")
                    prefetch_data = None
                except Exception as e:
                    logger.warning(f"Prefetch failed for {specialist_id}: {e}")
                    prefetch_data = None

            if prefetch_data and _has_real_data(prefetch_data):
                data_label = "CALENDARIO" if intent["is_calendar"] else \
                             "EMAILS" if intent["is_email"] else "DRIVE"
                agent_copy["system_prompt"] += (
                    f"\n\n[DADOS PRE-CARREGADOS DO {data_label}]\n{prefetch_data}\n\n"
                    "Formate estes dados em portugues brasileiro de forma amigavel e direta. "
                    "NAO chame ferramentas — os dados ja estao prontos."
                )
                agent_copy["tools"] = []

            path.append({"step": 2, "phase": "specialist", "agent": specialist_id,
                         "prefetch": bool(prefetch_data),
                         "reason": {k: v for k, v in intent.items() if v}})
            result = await _execute_agent(agent_copy, masked_text, payload, extra)
        else:
            path.append({"step": 2, "phase": "fallback_to_orchestrator", "reason": "specialist_disabled"})
            orchestrator_id = await _get_orchestrator(instance)
            if not orchestrator_id:
                return _error_response(503, "no_orchestrator", "Nenhum orchestrator disponivel")
            orchestrator = get_agent(orchestrator_id)
            if not orchestrator:
                return _error_response(503, "agent_not_found", f"Orchestrator {orchestrator_id} nao encontrado")
            result = await _execute_agent(orchestrator, masked_text, payload, extra)
    else:
        orchestrator_id = await _get_orchestrator(instance)
        if not orchestrator_id:
            return _error_response(503, "no_orchestrator", "Nenhum orchestrator disponivel")
        orchestrator = get_agent(orchestrator_id)
        if not orchestrator:
            return _error_response(503, "agent_not_found", f"Orchestrator {orchestrator_id} nao encontrado")
        path.append({"step": 2, "phase": "orchestrator", "agent": orchestrator_id, "reason": "default_route"})

        if first_name and not has_nickname(phone):
            suggested = _prefetch_nickname(first_name)
            if not suggested:
                suggested = _generate_diminutive(first_name)
            intimacy_context = (
                f"\n\n[CONTEXTO DE INTIMIDADE - PRIMEIRO CONTATO]\n"
                f"Primeiro nome: {first_name}. Apelido sugerido: {suggested}\n"
                f"1. Cumprimente usando APENAS o primeiro nome '{first_name}'.\n"
                f"2. Pergunte: 'Posso te chamar de {suggested}?' e aguarde confirmacao.\n"
                f"3. JAMAIS use apelidos depreciativos, ofensivos ou ironicos.\n"
                f"4. Se o usuario aceitar ('sim', 'pode'), chame nickname.set_consent(phone, nome, apelido, True).\n"
                f"5. Se ele rejeitar, nao insista."
            )
            orchestrator["system_prompt"] = orchestrator.get("system_prompt", "") + intimacy_context
            if "nickname.set_consent" not in orchestrator.get("tools", []):
                orchestrator["tools"] = list(orchestrator.get("tools", [])) + [
                    "nickname.set_consent",
                    "nickname.get_preferred_name",
                ]

        result = await _execute_agent(orchestrator, masked_text, payload, extra)

    path.append({"step": 3, "phase": "result", "agent_id": result.get("metadata", {}).get("agent_id"),
                 "model": result.get("metadata", {}).get("model_used"),
                 "escalated": result.get("metadata", {}).get("escalated"),
                 "confidence": result.get("metadata", {}).get("confidence_score"),
                 "tool_rounds": result.get("metadata", {}).get("tool_rounds", 0),
                 "tool_calls": result.get("metadata", {}).get("tool_calls", [])})

    _interaction_history.append({
        "timestamp": int(time.time()),
        "phone": phone,
        "text_preview": masked_text[:80],
        "sender": sender_name,
        "path": path,
        "reply_preview": result.get("reply", "")[:80],
    })
    if len(_interaction_history) > MAX_HISTORY:
        _interaction_history.pop(0)

    return result


async def _execute_agent(
    agent: Dict[str, Any],
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a specific agent with tool calling loop."""
    skills_section = _build_skills_section(agent.get("skills", []))
    system_prompt = agent.get("system_prompt", "") + skills_section

    brt = timezone(timedelta(hours=-3))
    hoje = datetime.now(brt)
    system_prompt += (
        f"\n\n[DATA ATUAL: {hoje.strftime('%Y-%m-%d')} (horario de Brasilia, BRT, UTC-3). "
        f"Hora atual: {hoje.strftime('%H:%M')}. "
        "Use esta data para todas as consultas de calendario e referencias temporais. "
        "IDIOMA: SEMPRE responda em portugues brasileiro (pt-BR). NAO use ingles. "
        "NAO inclua tags XML como <think> nas suas respostas.]"
    )

    first_name = payload.get("first_name", "")
    static_user_prefix = (
        f"User: {payload.get('sender_name', 'user')} (tel: {payload.get('phone', '')}"
        + (f", primeiro nome: {first_name}" if first_name else "")
        + ")\n"
    )
    dynamic_user_message = f"Mensagem: {text}"
    user_prompt = static_user_prefix + dynamic_user_message

    available_tools = agent.get("tools", [])

    llm = LLMProvider()
    if not llm.is_available():
        return _error_response(503, "llm_unavailable", "Nenhum provedor LLM configurado")

    threshold = agent.get("escalation_threshold", -2)
    no_escalation = agent.get("no_escalation", False)
    thinking = agent.get("thinking", "disabled") == "enabled"
    fast_model = agent.get("model", "deepseek-v4-flash")

    tool_schemas = []
    for tid in available_tools:
        schema = get_tool_schema(tid)
        if schema:
            tool_schemas.append({"type": "function", "function": schema})

    async def tool_executor(tool_name: str, tool_args: dict) -> str:
        tool_fn = get_tool(tool_name)
        if not tool_fn:
            return json.dumps({"error": f"Tool '{tool_name}' not found"})
        try:
            if asyncio.iscoroutinefunction(tool_fn):
                result = await tool_fn(**tool_args)
            else:
                result = tool_fn(**tool_args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    try:
        if tool_schemas:
            result = await llm.chat_with_tools(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=tool_schemas,
                tool_executor=tool_executor,
                model=fast_model,
                temperature=0.7,
                max_tokens=1000,
                thinking_disabled=not thinking,
                max_tool_rounds=5,
            )
        else:
            result = await llm.chat_escalating(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                fast_model=fast_model,
                pro_model=agent.get("model_escalation") or "deepseek-v4-pro",
                threshold=threshold,
                no_escalation=no_escalation,
                temperature=0.7,
                max_tokens=500,
                thinking_disabled=not thinking,
                scoring_fn=lambda t: compute_confidence_score(t),
            )

        reply_text = result["content"]
        reply_text = re.sub(r'\s*<think>.*?</think>\s*', '', reply_text, flags=re.DOTALL).strip()
        delay_ms = calculate_delay_ms(reply_text)
        presence = calculate_presence()

        tool_calls_made = _extract_tool_calls(reply_text, available_tools)

        return {
            "reply": reply_text,
            "delay_ms": delay_ms,
            "presence": presence,
            "metadata": {
                "agent_id": agent.get("id"),
                "model_used": result.get("model_used", fast_model),
                "provider": result.get("provider", ""),
                "tool_rounds": result.get("tool_rounds", 0),
                "tool_calls": tool_calls_made,
                "has_audio": extra.get("has_audio", False),
            },
        }
    except LLMError as e:
        logger.error(f"LLM cascade failed for agent {agent.get('id')}: {e}")
        return _error_response(503, "llm_unavailable", "Todos provedores LLM falharam.")
    except Exception as e:
        logger.exception(f"Unexpected error in _execute_agent")
        return _error_response(500, "internal_error", str(e))


def _extract_tool_calls(reply_text: str, available_tools: List[str]) -> List[Dict[str, Any]]:
    """Best-effort detection of tool calls mentioned in reply.

    Checks both resource name (calendar) and method (list_events).
    For MVP, we detect by name pattern. Real Agno tool-calling would be JSON.
    """
    tool_calls = []
    if not reply_text or not available_tools:
        return tool_calls

    reply_lower = reply_text.lower()
    for tool_id in available_tools:
        parts = tool_id.split(".")
        resource = parts[0].replace("_", " ") if len(parts) > 0 else ""
        method = parts[-1].replace("_", " ") if len(parts) > 1 else ""

        matched = False
        match_type = None
        if resource and resource in reply_lower:
            matched = True
            match_type = "resource"
        elif method and method in reply_lower:
            matched = True
            match_type = "method"

        if matched:
            tool_calls.append({
                "tool_id": tool_id,
                "source": "text_match",
                "match_type": match_type,
            })
    return tool_calls


def _error_response(status_code: int, error: str, message: str) -> Dict[str, Any]:
    return {
        "reply": message,
        "delay_ms": 0,
        "presence": "paused",
        "metadata": {
            "error": error,
            "status_code": status_code,
        },
    }