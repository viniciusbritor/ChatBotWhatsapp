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
import copy
import logging
import time
import asyncio
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.commands import detect_command, apply_command
from tool_registry import get_tool, get_tool_schema, is_user_scoped_tool
from agent_loader import get_agent, get_skill, list_agents, get_user, get_config, has_nickname
from core.audit import log_action
from core.timezone import BRT, now_brt

logger = logging.getLogger(__name__)

_interaction_history: List[Dict[str, Any]] = []
MAX_HISTORY = 20
_response_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = int(os.getenv("RESPONSE_IDEMPOTENCY_TTL_SEC", "86400"))
_indexing_tasks: set = set()


def _finish_indexing_task(task: asyncio.Task) -> None:
    _indexing_tasks.discard(task)
    if task.cancelled():
        logger.warning("RAG indexing task cancelled")
        return
    exception = task.exception()
    if exception:
        logger.error("RAG indexing task failed: %s", exception)


def _schedule_indexing(coroutine: Any) -> asyncio.Task:
    task = asyncio.create_task(coroutine)
    _indexing_tasks.add(task)
    task.add_done_callback(_finish_indexing_task)
    return task


async def drain_indexing_tasks(timeout: float = 15.0) -> None:
    pending = list(_indexing_tasks)
    if not pending:
        return
    _, unfinished = await asyncio.wait(pending, timeout=timeout)
    if unfinished:
        logger.warning("RAG indexing drain timed out: pending=%s", len(unfinished))


def _message_id(payload: Dict[str, Any]) -> Optional[str]:
    extra = payload.get("extra", {})
    message_id = (
        payload.get("message_id")
        or extra.get("message_id")
        or extra.get("messageId")
        or (extra.get("key") or {}).get("id")
    )
    if not message_id:
        phone = re.sub(r"\D", "", str(payload.get("phone", "")))
        owner_hash = __import__("hashlib").sha256(phone.encode("utf-8")).hexdigest()[:12] if phone else "unknown"
        logger.warning(
            "message_id_missing owner_hash=%s instance=%s fallback=time_based_key retry_idempotent=false",
            owner_hash,
            payload.get("instance", "unknown"),
        )
    return message_id or None


def _conversation_id(payload: Dict[str, Any]) -> str:
    extra = payload.get("extra", {})
    return str(extra.get("remote_jid") or extra.get("conversation_id") or payload.get("phone", ""))


def _idempotency_key(payload: Dict[str, Any]) -> Optional[str]:
    message_id = _message_id(payload)
    if not message_id:
        return None
    raw = f"{payload.get('instance', 'jennifer')}:{_conversation_id(payload)}:{message_id}"
    return __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()


async def _finalize_orchestration(
    payload: Dict[str, Any],
    masked_text: str,
    sender_name: str,
    result: Dict[str, Any],
    path: List[Dict[str, Any]],
    cache_key: Optional[str],
) -> Dict[str, Any]:
    metadata = result.setdefault("metadata", {})
    metadata.setdefault("response_identity", "Jennifer")
    path.append({
        "step": 3,
        "phase": "result",
        "agent_id": metadata.get("agent_id"),
        "model": metadata.get("model_used"),
        "escalated": metadata.get("escalated"),
        "confidence": metadata.get("confidence_score"),
        "tool_rounds": metadata.get("tool_rounds", 0),
        "tool_calls": metadata.get("tool_calls", []),
        "response_identity": metadata.get("response_identity"),
    })
    phone = payload.get("phone", "")
    _interaction_history.append({
        "timestamp": now_brt().isoformat(),
        "phone": phone,
        "text_preview": masked_text[:80],
        "sender": mask_pii(sender_name),
        "path": path,
        "reply_preview": mask_pii(result.get("reply", ""))[:80],
    })
    if len(_interaction_history) > MAX_HISTORY:
        _interaction_history.pop(0)

    if cache_key and not metadata.get("error"):
        cached_result = copy.deepcopy(result)
        cached_result["ts"] = int(time.time())
        _response_cache[cache_key] = cached_result
        for key in list(_response_cache.keys()):
            if int(time.time()) - _response_cache.get(key, {}).get("ts", 0) > CACHE_TTL_SEC:
                del _response_cache[key]

    message_id = _message_id(payload)
    conversation_id = _conversation_id(payload)
    agent_id = metadata.get("agent_id", "jennifier")
    _schedule_indexing(_index_message(
        phone,
        masked_text,
        "in",
        message_id=message_id,
        conversation_id=conversation_id,
        turn_id=message_id,
        agent_id="user",
        response_identity="Usuario",
    ))
    reply_text = result.get("reply", "")
    if reply_text:
        _schedule_indexing(_index_message(
            phone,
            reply_text,
            "out",
            message_id=f"{message_id}:reply" if message_id else None,
            conversation_id=conversation_id,
            turn_id=message_id,
            agent_id=agent_id,
            response_identity="Jennifer",
        ))
    return result


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
    "agenda", "agend", "reuniao", "evento", "eventos", "compromisso",
    "compromissos", "lembrete", "calendario", "disponivel",
    "semana que vem", "proxima semana", "agenda de hoje",
]
DRIVE_KEYWORDS = [
    "drive", "gdrive", "documento", "documentos", "arquivo", "arquivos",
    "pasta", "upload", "omnichannel", "atividades", "baixar",
    "encontrar arquivo", "meus arquivos", "meus documentos",
    "buscar arquivo", "procurar documento", "lista de arquivos",
    "mostrar arquivos", "ata", "minuta", "relatorio",
    "apresentação", "apresentacao", "docx", "pdf", "xlsx", "planilha",
    "leia o arquivo", "leia a ata", "abra o arquivo",
]
EMAIL_KEYWORDS = [
    "email", "e-mail", "emails", "e-mails",
    "caixa de entrada", "caixa postal", "correio", "inbox",
    "gmail", "ler email", "enviar email", "ultimos emails",
    "ultima mensagem", "mensagens",
]
WEB_KEYWORDS = [
    "pesquisar", "buscar na internet", "busque na internet", "procure na web",
    "pesquise na web", "noticia atual", "noticias atuais", "pesquisa sobre",
]
RUNTIME_STATUS_KEYWORDS = [
    "quantos agentes", "quais agentes", "agentes funcionando", "agentes ativos",
    "agentes rodando", "status dos agentes", "o que esta rodando", "o que está rodando",
    "listar agentes", "liste os agentes",
]
AMBIGUOUS_WEB_KEYWORDS = {"o que e", "quem e", "significa"}
INTIMACY_KEYWORDS = [
    "me chame de", "pode me chamar de", "meu apelido",
    "meu nome e", "meu nome é", "como devo te chamar",
]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def _matches_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    if not normalized_keyword:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_keyword)}s?(?!\w)"
    return re.search(pattern, text) is not None


def _get_routing_rules() -> List[Dict[str, Any]]:
    config = get_config("routing")
    rules = []
    for source in (config or {}).get("rules", []):
        if not source.get("enabled", True):
            continue
        rule = dict(source)
        if rule.get("agent_id") == "manager-web":
            rule["keywords"] = [
                keyword for keyword in rule.get("keywords", [])
                if _normalize_text(keyword) not in AMBIGUOUS_WEB_KEYWORDS
            ]
        rules.append(rule)
    return rules


def _detect_intent(text: str) -> Dict[str, Any]:
    normalized = _normalize_text(text)
    explicit_url = re.search(r"https?://\S+", str(text or ""), flags=re.IGNORECASE) is not None
    intent = {
        "is_runtime_status": any(_matches_keyword(normalized, keyword) for keyword in RUNTIME_STATUS_KEYWORDS),
        "is_gross": any(_matches_keyword(normalized, keyword) for keyword in GROSS_KEYWORDS),
        "is_assault_related": any(_matches_keyword(normalized, keyword) for keyword in ASSAULT_KEYWORDS),
        "is_correction": any(_matches_keyword(normalized, keyword) for keyword in CORRECTION_KEYWORDS),
        "is_calendar": any(_matches_keyword(normalized, keyword) for keyword in CALENDAR_KEYWORDS),
        "is_drive": any(_matches_keyword(normalized, keyword) for keyword in DRIVE_KEYWORDS),
        "is_email": any(_matches_keyword(normalized, keyword) for keyword in EMAIL_KEYWORDS),
        "is_web_search": explicit_url or any(_matches_keyword(normalized, keyword) for keyword in WEB_KEYWORDS),
        "is_intimacy": any(_matches_keyword(normalized, keyword) for keyword in INTIMACY_KEYWORDS),
    }
    for rule in _get_routing_rules():
        agent_id = rule.get("agent_id", "")
        keywords = rule.get("keywords", [])
        if any(_matches_keyword(normalized, keyword) for keyword in keywords):
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
    for agent in list_agents():
        yield agent.get("id", ""), agent


def _resolve_agent_for_intent(intent: Dict[str, Any], instance: str) -> Optional[str]:
    """Resolve which agent should handle this intent (hardcoded + dynamic from Firestore)."""
    if intent.get("is_runtime_status"):
        return "runtime-status"
    if intent["is_gross"] or intent["is_assault_related"]:
        return "agent-morality"
    if intent["is_correction"]:
        return "agent-learning"
    if intent["is_intimacy"]:
        return "agent-intimacy"
    if intent["is_drive"]:
        return "manager-drive"
    if intent["is_email"]:
        return "manager-email"
    if intent["is_calendar"]:
        return "manager-calendar"
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


async def _prefetch_calendar(phone: str, instance: str = "") -> Optional[str]:
    """Fase B: pre-busca eventos do dia sem LLM."""
    try:
        from tools.google_calendar import list_events
        from datetime import datetime, timezone, timedelta
        brt = timezone(timedelta(hours=-3))
        hoje = datetime.now(brt)
        result = await list_events(
            phone,
            time_min=hoje.strftime("%Y-%m-%dT00:00:00-03:00"),
            time_max=hoje.strftime("%Y-%m-%dT23:59:59-03:00"),
            max_results=50,
            instance=instance,
        )
        events = result.get("events", [])
        if not events:
            return None
        return json.dumps(events, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch calendar failed: {e}")
        return None


async def _prefetch_email(phone: str, instance: str = "") -> Optional[str]:
    """Fase B: pre-busca ultimos emails sem LLM."""
    try:
        from tools.google_gmail import search_messages
        result = await search_messages(
            phone,
            "in:inbox newer_than:30d",
            max_results=10,
            instance=instance,
        )
        messages = result.get("messages", [])
        if not messages:
            return None
        return json.dumps(messages, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch email failed: {e}")
        return None


async def _prefetch_drive(phone: str, query_text: str = "", instance: str = "") -> Optional[str]:
    """Fase B: pre-busca arquivos no Drive sem LLM."""
    try:
        from tools.google_drive import search_files
        result = await search_files(phone, query_text or "", max_results=20, instance=instance)
        files = result.get("files", [])
        if not files:
            return None
        return json.dumps(files, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Prefetch drive failed: {e}")
        return None


async def _prefetch_drive_multi(phone: str, text: str, instance: str = "") -> Optional[str]:
    """D1: 3 queries paralelas no Drive, usa a com mais resultados."""
    query1 = _extract_search_terms(text)
    query2 = " ".join(w for w in text.lower().split()
                      if len(w.strip(",.!?;:")) > 3)[:5]
    results = await asyncio.gather(
        _prefetch_drive(phone, query1, instance),
        _prefetch_drive(phone, query2, instance),
        _prefetch_drive_docs(phone, query1, instance),
        _prefetch_drive_docs(phone, query2, instance),
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


async def _prefetch_drive_docs(phone: str, query_text: str = "", instance: str = "") -> Optional[str]:
    """Prefetch so documentos e apresentacoes do Drive (atas, slides)."""
    try:
        from tools.google_drive import search_files
        query_parts = []
        if query_text:
            query_parts.append(f"name contains '{query_text}'")
        query_parts.append("mimeType contains 'document' or mimeType contains 'presentation'")
        result = await search_files(
            phone,
            query_text or "",
            mime_type="application/vnd.google-apps.document",
            max_results=20,
            instance=instance,
        )
        alt = await search_files(
            phone,
            query_text or "",
            mime_type="application/vnd.google-apps.presentation",
            max_results=20,
            instance=instance,
        )
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
REJECTION_KEYWORDS = {"nao", "não", "prefiro nao", "prefiro não", "recuso", "deixa"}


def _short_confirmation(text: str) -> Optional[bool]:
    normalized = _normalize_text(text).strip(" .,!?:;")
    if normalized in {_normalize_text(value) for value in ACCEPTANCE_KEYWORDS}:
        return True
    if normalized in {_normalize_text(value) for value in REJECTION_KEYWORDS}:
        return False
    return None


def _get_db():
    """Get Firestore client (fallback robusto)."""
    try:
        from google.cloud import firestore
        import os
        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project:
            return None
        return firestore.Client(project=project)
    except Exception:
        return None


def _get_conversation_history(phone: str, limit: int = 10) -> str:
    """A2: Busca historico de conversas do Firestore para injetar no prompt."""
    db = _get_db()
    if not db:
        return ""
    try:
        import hashlib
        ph = hashlib.sha256(phone.encode()).hexdigest()[:16]
        docs = (
            db.collection("contatos").document(ph)
            .collection("historico")
            .order_by("ts", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        msgs = []
        for d in docs:
            data = d.to_dict()
            direction = data.get("direction", "in")
            text = data.get("text", "")[:80]
            prefix = "Usuario" if direction == "in" else "Jennifer"
            msgs.append(f"{prefix}: {text}")
        return "\n".join(reversed(msgs)) if msgs else ""
    except Exception as e:
        logger.warning(f"Conversation history failed: {e}")
        return ""


async def _search_memory(phone: str, query: str, limit: int = 5) -> str:
    try:
        from core.rag import search_conversation_memory

        results = await search_conversation_memory(phone, query, limit)
        memories = []
        for result in results:
            text = result.get("text", "")[:300]
            direction = result.get("direction", "in")
            identity = "Usuario" if direction == "in" else result.get("response_identity", "Jennifer")
            memories.append(f"- {identity}: {text}")
        return "\n".join(memories)
    except Exception as exc:
        logger.warning("RAG search failed: %s", exc)
        return ""


async def _index_message(phone: str, text: str, direction: str, **metadata: Any) -> Dict[str, Any]:
    try:
        from core.rag import index_conversation_message

        result = await index_conversation_message(
            phone=phone,
            text=text,
            direction=direction,
            message_id=metadata.get("message_id"),
            conversation_id=metadata.get("conversation_id"),
            turn_id=metadata.get("turn_id"),
            agent_id=metadata.get("agent_id"),
            response_identity=metadata.get("response_identity", "Jennifer"),
        )
        if result.get("status") == "indexed":
            logger.info("RAG message indexed: direction=%s doc_id=%s", direction, result.get("doc_id"))
        else:
            logger.warning("RAG message not indexed: direction=%s reason=%s", direction, result.get("reason"))
        return result
    except Exception as exc:
        logger.error("RAG message indexing failed: %s", exc)
        return {"status": "error", "reason": str(exc)}


async def index_audio_failure_for_audit(body: Dict[str, Any], error_code: str) -> Dict[str, Any]:
    try:
        phone = body.get("phone", "")
        message_id = body.get("message_id") or (body.get("extra") or {}).get("message_id") or ""
        if not phone:
            return {"status": "skipped", "reason": "missing_phone"}
        timestamp_brt = now_brt().isoformat(timespec="minutes")
        marker_text = mask_pii(
            f"[audio transcription failed at {timestamp_brt} reason={error_code}]"
        )
        return await _index_message(
            phone,
            marker_text,
            "in",
            message_id=f"audio-fail:{message_id}" if message_id else None,
            conversation_id=(body.get("extra") or {}).get("remote_jid") or phone,
            turn_id=message_id,
            agent_id="audio-transcriber",
            response_identity="AudioAudit",
        )
    except Exception as exc:
        logger.warning("audio failure audit indexing failed: %s", type(exc).__name__)
        return {"status": "error", "reason": type(exc).__name__}


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

    cache_key = _idempotency_key(payload)
    if cache_key and cache_key in _response_cache:
        cached = _response_cache[cache_key]
        if int(time.time()) - cached.get("ts", 0) < CACHE_TTL_SEC:
            response = copy.deepcopy(cached)
            response.pop("ts", None)
            response.setdefault("metadata", {})["cached"] = True
            logger.info("Idempotent response cache hit")
            return response

    first_name = _extract_first_name(sender_name)
    payload["first_name"] = first_name
    masked_text = mask_pii(text)
    confirmation = _short_confirmation(masked_text)

    if confirmation is not None:
        from core.pending_actions import consume_pending_action, get_pending_action

        pending_action = await get_pending_action(phone)
        if pending_action and pending_action.get("action_type") == "nickname_consent":
            await consume_pending_action(phone, "nickname_consent")
            action_payload = pending_action.get("payload", {})
            name = action_payload.get("first_name") or first_name
            nickname = action_payload.get("nickname", "")
            from tools.nickname import set_consent

            consent = await set_consent(phone, name, nickname, confirmation)
            reply = (
                f"Combinado, {nickname}! Vou usar esse apelido daqui pra frente."
                if confirmation
                else f"Tudo certo, {name}. Vou continuar usando seu primeiro nome."
            )
            result = {
                "reply": reply,
                "delay_ms": calculate_delay_ms(reply),
                "presence": calculate_presence(),
                "metadata": {
                    "agent_id": "agent-intimacy",
                    "response_identity": "Jennifer",
                    "pending_action": "nickname_consent",
                    "accepted": confirmation,
                    "consent_recorded": "error" not in consent,
                },
            }
            path = [{"step": 1, "phase": "pending_action", "action": "nickname_consent"}]
            return await _finalize_orchestration(
                payload, masked_text, sender_name, result, path, cache_key
            )
        if pending_action and pending_action.get("action_type") == "group_consent":
            await consume_pending_action(phone, "group_consent")
            action_payload = pending_action.get("payload", {})
            group_jid = action_payload.get("group_jid", "")
            requested_intent = action_payload.get("intent", "calendar")
            try:
                from tools.group import set_member_confirmation

                await set_member_confirmation(group_jid, phone, True)
            except Exception as exc:
                logger.warning("set_member_confirmation failed: %s", exc)
            intent_token = f"is_{requested_intent}"
            intent = {intent_token: True}
            specialist_id = _resolve_agent_for_intent(intent, instance)
            if specialist_id:
                agent = get_agent(specialist_id)
                if agent:
                    agent_copy = dict(agent)
                    payload["_group_consent_granted"] = True
                    agent_result = await _execute_agent(
                        agent_copy, masked_text, payload, extra
                    )
                    reply = agent_result.get("reply", "Ok, liberei o acesso.")
                else:
                    reply = "Ok, liberei o acesso."
            else:
                reply = "Ok, liberei o acesso."
            result = {
                "reply": reply,
                "delay_ms": calculate_delay_ms(reply),
                "presence": calculate_presence(),
                "metadata": {
                    "agent_id": "agent-privacy-guard",
                    "response_identity": "Jennifer",
                    "pending_action": "group_consent",
                    "accepted": confirmation,
                    "group_jid": group_jid,
                },
            }
            path = [{"step": 1, "phase": "pending_action", "action": "group_consent"}]
            return await _finalize_orchestration(
                payload, masked_text, sender_name, result, path, cache_key
            )

    intent = _detect_intent(masked_text)
    path = [{"step": 1, "phase": "intent_detect", "details": {key: value for key, value in intent.items() if value}}]

    if intent.get("is_runtime_status"):
        from core.agent_status import build_agent_inventory, format_inventory_reply

        inventory = build_agent_inventory(instance=instance, phone=phone)
        reply = format_inventory_reply(inventory)
        result = {
            "reply": reply,
            "delay_ms": calculate_delay_ms(reply),
            "presence": calculate_presence(),
            "metadata": {
                "agent_id": "runtime-status",
                "route": "deterministic",
                "response_identity": "Jennifer",
                "counts": inventory["counts"],
                "generated_at": inventory["generated_at"],
            },
        }
        path.append({"step": 2, "phase": "runtime_status", "agent": "runtime-status"})
        return await _finalize_orchestration(
            payload, masked_text, sender_name, result, path, cache_key
        )

    specialist_id = _resolve_agent_for_intent(intent, instance)

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
            from core.pending_actions import set_pending_action

            await set_pending_action(
                phone,
                "group_consent",
                {
                    "group_jid": group_jid,
                    "requested_by": phone,
                    "intent": "calendar" if intent.get("is_calendar") else (
                        "email" if intent.get("is_email") else "drive"
                    ),
                    "agent": "agent-privacy-guard",
                },
                ttl_sec=300,
            )
            return {
                "reply": (
                    f"Oi {sender_name}! Voce pediu para acessar informacoes pessoais no grupo. "
                    "Para sua seguranca, preciso que me confirme no privado primeiro. "
                    "Me manda uma mensagem no privado dizendo 'sim' e eu libero o acesso para voce neste grupo. "
                    "Tambem pode confirmar no Portal: https://coherence-portal-test-c5nbfc5meq-uc.a.run.app 🔒"
                ),
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {
                    "agent_id": "privacy-guard",
                    "blocked": "group_unconfirmed_member",
                    "pending_action": "group_consent",
                },
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

            guard_result = await _run_guard_graph(payload, masked_text, intent)
            guard_verdict = (guard_result or {}).get("verdict", "noop")
            if guard_verdict in {"deny", "request_oauth"}:
                decision = (guard_result or {}).get("decision") or {}
                link = decision.get("oauth_link", "")
                if guard_verdict == "request_oauth" and link:
                    reply = (
                        "Oi! Para acessar " + decision.get("capability", "essa ferramenta") +
                        ", preciso que voce autorize sua conta Google. "
                        f"Acesse este link e faca o login: {link}"
                    )
                else:
                    reply = (
                        "Oi! Essa acao so pode ser executada pelo proprietario "
                        "da conta WhatsApp."
                    )
                return {
                    "reply": reply,
                    "delay_ms": 0,
                    "presence": "composing",
                    "metadata": {
                        "agent_id": "access_guardian",
                        "guardian_verdict": guard_verdict,
                        "guardian_reason": decision.get("reason", ""),
                        "guardian_capability": decision.get("capability", ""),
                        "response_identity": "Jennifer",
                        "blocked": True,
                    },
                }

            if guard_result.get("prefetch"):
                prefetch_data = guard_result["prefetch"]

            if prefetch_data is None and _is_read_query(masked_text):
                try:
                    if intent["is_calendar"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_calendar(phone, instance), timeout=8)
                    elif intent["is_email"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_email(phone, instance), timeout=8)
                    elif intent["is_drive"]:
                        prefetch_data = await asyncio.wait_for(
                            _prefetch_drive_multi(phone, masked_text, instance), timeout=8)
                except asyncio.TimeoutError:
                    logger.warning(f"Prefetch timeout for {specialist_id}")
                    prefetch_data = None
                except Exception as e:
                    logger.warning(f"Prefetch failed for {specialist_id}: {e}")
                    prefetch_data = None

            if prefetch_data and _has_real_data(prefetch_data):
                prefetch_data = mask_pii(prefetch_data)
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

        orchestrator = copy.deepcopy(orchestrator)
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
                f"4. Nao interprete a resposta futura sem consultar pending_action.\n"
                f"5. Se ele rejeitar, nao insista."
            )
            orchestrator["system_prompt"] = orchestrator.get("system_prompt", "") + intimacy_context
            if "nickname.get_preferred_name" not in orchestrator.get("tools", []):
                orchestrator["tools"] = list(orchestrator.get("tools", [])) + [
                    "nickname.get_preferred_name",
                ]
            from core.pending_actions import set_pending_action

            await set_pending_action(
                phone,
                "nickname_consent",
                {"first_name": first_name, "nickname": suggested},
            )

        result = await _execute_agent(orchestrator, masked_text, payload, extra)

    return await _finalize_orchestration(
        payload, masked_text, sender_name, result, path, cache_key
    )


_MINIMAX_TOOL_CALL_RE = re.compile(r"<\s*tool_call\s*>.*?</\s*tool_call\s*>", re.DOTALL)
_MINIMAX_TOOL_CALL_SELF_RE = re.compile(r"<\s*tool_call\s*/?\s*>")
_MINIMAX_INVOKE_RE = re.compile(r"<\s*invoke\b[^>]*>.*?</\s*invoke\s*>", re.DOTALL)
_MINIMAX_INVOKE_SELF_RE = re.compile(r"<\s*invoke\b[^>]*/?>")
_MINIMAX_TAG_RE = re.compile(r"\[\s*<\s*minimax\s*>\s*\[|\]\s*<\s*/?\s*minimax\s*>\s*\]")


def _strip_provider_artifacts(text: str) -> str:
    """Safety net: remove MiniMax-style tags that may leak into `content`.

    `chat_with_tools` strips these when it parses inline tool calls, but if
    the parser is bypassed (e.g. provider returns clean `tool_calls`), a few
    fragments can still survive. We collapse them here as defense in depth.
    """
    cleaned = _MINIMAX_TOOL_CALL_RE.sub("", text)
    cleaned = _MINIMAX_TOOL_CALL_SELF_RE.sub("", cleaned)
    cleaned = _MINIMAX_INVOKE_RE.sub("", cleaned)
    cleaned = _MINIMAX_INVOKE_SELF_RE.sub("", cleaned)
    cleaned = _MINIMAX_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_response_identity(text: str) -> str:
    normalized = _strip_provider_artifacts(str(text or ""))
    replacements = [
        (r"(?i)\bsou\s+(?:o|a)\s+(?:web|calendar|drive|email)\s+manager\b", "sou a Jennifer"),
        (r"(?i)\baqui\s+e\s+(?:o|a)\s+(?:web|calendar|drive|email)\s+manager\b", "aqui e a Jennifer"),
        (r"(?i)\b(?:sua|seu)\s+(?:web|calendar|drive|email)\s+manager\b", "Jennifer"),
        (r"(?i)\b(?:web|calendar|drive|email)\s+manager\b", "Jennifer"),
        (r"(?i)\bmanager-(?:web|calendar|drive|email)\b", "Jennifer"),
        (r"(?i)\bagent-(?:intimacy|learning|morality|rag)\b", "Jennifer"),
    ]
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def _bind_tool_args(tool_name: str, tool_args: Dict[str, Any], phone: str, instance: str = "") -> Dict[str, Any]:
    effective_args = dict(tool_args)
    if is_user_scoped_tool(tool_name):
        effective_args["phone"] = phone
        effective_args["instance"] = instance
    return effective_args


def _is_ai_message(message: Any) -> bool:
    """Return True if the message is an AI assistant message.

    Compatible with LangChain 1.x ``AIMessage`` (BaseMessage subclass)
    and the legacy dict format used by early DeepAgents.
    """
    if isinstance(message, dict):
        return message.get("role") == "assistant"
    cls_name = type(message).__name__
    if cls_name == "AIMessage":
        return True
    msg_type = getattr(message, "type", "")
    return msg_type in {"ai", "AIMessage"}


def _is_tool_message(message: Any) -> bool:
    """Return True if the message is a tool result message."""
    if isinstance(message, dict):
        return message.get("role") == "tool"
    cls_name = type(message).__name__
    if cls_name == "ToolMessage":
        return True
    msg_type = getattr(message, "type", "")
    return msg_type in {"tool", "ToolMessage"}


def _extract_message_content(message: Any) -> str:
    """Extract the text content from an AI message in any supported format.

    LangChain 1.x ``AIMessage`` may carry content as a string OR as a list
    of blocks (e.g. ``[{"type": "text", "text": "..."}]``). We normalise to
    a plain string.
    """
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")
                if text:
                    parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content or "")


async def _execute_deep_agent(
    agent: Dict[str, Any],
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Execute the agent using DeepAgents harness.

    Returns ``None`` if DeepAgents is not available for this agent id
    (e.g. ``manager-calendar`` is supported, but a custom agent id is not).
    Returns the standard reply dict on success, or a fallback error dict
    on failure.
    """
    agent_id = agent.get("id", "unknown-agent")
    try:
        from deepagent_layer import get_deep_agent
    except Exception as exc:
        logger.warning("deepagent_layer unavailable: %s", exc)
        return None

    deep_agent = get_deep_agent(agent_id)
    if deep_agent is None:
        return None

    from core.agent_status import record_agent_failure, record_agent_success, start_agent_execution
    execution_started = start_agent_execution(agent_id)

    phone = payload.get("phone", "")
    first_name = payload.get("first_name", "")
    brt = timezone(timedelta(hours=-3))
    hoje = datetime.now(brt)

    user_prompt = (
        f"User: {payload.get('sender_name', 'user')} (tel: {phone}"
        + (f", primeiro nome: {first_name}" if first_name else "")
        + ")\n"
        f"Mensagem: {text}\n\n"
        f"DATA ATUAL: {hoje.strftime('%Y-%m-%d')} (horario de Brasilia, BRT, UTC-3). "
        f"Hora atual: {hoje.strftime('%H:%M')}. "
        f"Responda em portugues brasileiro, tom caloroso, 1-2 frases, max 4 linhas."
    )

    config: Dict[str, Any] = {
        "configurable": {
            "thread_id": phone or "default",
        }
    }
    if phone:
        config["configurable"]["phone"] = phone

    try:
        result = await asyncio.wait_for(
            deep_agent.ainvoke(
                {"messages": [{"role": "user", "content": user_prompt}]},
                config=config,
            ),
            timeout=120,
        )
    except asyncio.TimeoutError:
        record_agent_failure(agent_id, execution_started, "deepagent_timeout")
        return _error_response(504, "deepagent_timeout", "Jennifer demorou demais. Tenta de novo?")
    except Exception as exc:
        record_agent_failure(agent_id, execution_started, f"deepagent_error:{type(exc).__name__}")
        logger.exception("deepagent_failed manager=%s", agent_id)
        return None

    messages = (result or {}).get("messages", [])
    reply_text = ""
    for m in reversed(messages):
        if _is_ai_message(m):
            content = _extract_message_content(m)
            reply_text = str(content or "").strip()
            break

    if not reply_text:
        record_agent_failure(agent_id, execution_started, "deepagent_empty")
        return _error_response(500, "deepagent_empty", "Nao consegui gerar uma resposta.")

    reply_text = re.sub(r'\s*<think>.*?</think>\s*', '', reply_text, flags=re.DOTALL).strip()
    reply_text = _normalize_response_identity(reply_text)
    delay_ms = calculate_delay_ms(reply_text)
    presence = calculate_presence()

    from core import metrics
    model_used = "deepseek-v4-flash"
    provider = "deepseek"
    metrics.record_provider_latency(provider, True, execution_started)
    record_agent_success(agent_id, execution_started, model_used, provider)

    return {
        "reply": reply_text,
        "delay_ms": delay_ms,
        "presence": presence,
        "metadata": {
            "agent_id": agent_id,
            "executed_agent_id": agent_id,
            "response_identity": "Jennifer",
            "model_used": model_used,
            "provider": provider,
            "tool_rounds": len([m for m in messages if _is_tool_message(m)]),
            "tool_calls": [],
            "has_audio": extra.get("has_audio", False),
            "runtime": "deepagents",
        },
    }


async def _execute_agent(
    agent: Dict[str, Any],
    text: str,
    payload: Dict[str, Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a specific agent with tool calling loop.

    Tries the DeepAgents harness first; falls back to the legacy
    LLMProvider path if DeepAgents is unavailable for this agent id.
    """
    agent_id = agent.get("id", "unknown-agent")
    from core.agent_status import record_agent_failure, record_agent_success, start_agent_execution

    execution_started = start_agent_execution(agent_id)
    skills_section = _build_skills_section(agent.get("skills", []))
    system_prompt = agent.get("system_prompt", "") + skills_section
    if agent.get("role") != "orchestrator":
        system_prompt += (
            "\n\n[IDENTIDADE EXTERNA OBRIGATORIA]\n"
            "Voce e um componente interno da Jennifer. Nunca revele nome, ID, role ou arquitetura interna. "
            "Responda ao usuario sempre na voz da Jennifer e nunca se apresente como Manager ou Specialist."
        )

    phone = payload.get("phone", "")

    if phone:
        try:
            from tools.correction import summarize_past_corrections
            corr = await summarize_past_corrections(phone, limit=3)
            if corr.get("has_corrections"):
                items = corr["corrections"]
                system_prompt += "\n\n[APRENDIZADOS DO USUARIO]\n"
                for c in items:
                    system_prompt += f"- Correcao anterior ({c['target']}): '{c['user_quote'][:100]}' → '{c['after'][:100]}'\n"
                system_prompt += "Respeite essas preferencias ao responder."
        except Exception:
            pass

    try:
        deep_result = await _execute_deep_agent(agent, text, payload, extra)
        if deep_result is not None:
            return deep_result
    except Exception as exc:
        logger.warning("deepagent_attempt_failed agent_id=%s exc=%s", agent_id, type(exc).__name__)

    history = _get_conversation_history(phone, limit=10)
    mem_rag = await _search_memory(phone, text, limit=5)
    recent = [i for i in _interaction_history[-4:] if i.get("phone") == phone]
    ctx_parts = []
    if mem_rag:
        ctx_parts.append(f"[MEMORIA RAG - CONVERSAS RELEVANTES]\n{mem_rag}")
    if recent:
        ctx_parts.append("\n".join(f"- User: {r['text_preview'][:60]}\n- Jennifer: {r['reply_preview'][:60]}"
                                    for r in recent[-2:]))
    if history:
        ctx_parts.insert(0, f"[HISTORICO RECENTE]\n{history}")
    ctx = "\n\n".join(p for p in ctx_parts if p)
    if ctx:
        system_prompt += f"\n\n[CONTEXTO DA CONVERSA]\n{ctx}\nVoce JA conhece este usuario. Use a memoria para personalizar a resposta."

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
        record_agent_failure(agent_id, execution_started, "llm_unavailable")
        return _error_response(503, "llm_unavailable", "Nenhum provedor LLM configurado")

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
            logger.warning("tool_unknown tool=%s", tool_name)
            return json.dumps({"error": f"Tool '{tool_name}' not found"})
        effective_args = _bind_tool_args(tool_name, tool_args, phone, payload.get("instance", ""))
        logger.info("tool_invoking tool=%s args=%s", tool_name, list(effective_args.keys()))
        try:
            coro = tool_fn(**effective_args)
            if asyncio.iscoroutine(coro) or asyncio.iscoroutinefunction(tool_fn):
                result = await asyncio.wait_for(coro, timeout=30)
            else:
                result = coro
            truncated = mask_pii(json.dumps(result, ensure_ascii=False, default=str))
            if len(truncated) > 2000:
                truncated = truncated[:2000] + "...(truncated)"
            logger.info("tool_result tool=%s length=%d", tool_name, len(truncated))
            return truncated
        except asyncio.TimeoutError:
            logger.error("tool_timeout tool=%s timeout=30s", tool_name)
            return json.dumps({"error": f"Tool '{tool_name}' timed out after 30s"})
        except Exception as e:
            logger.exception("tool_error tool=%s", tool_name)
            return json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"})

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
            result = await llm.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=fast_model,
                temperature=0.7,
                max_tokens=500,
                thinking_disabled=not thinking,
            )

        reply_text = result["content"]
        reply_text = re.sub(r'\s*<think>.*?</think>\s*', '', reply_text, flags=re.DOTALL).strip()
        reply_text = _normalize_response_identity(reply_text)
        delay_ms = calculate_delay_ms(reply_text)
        presence = calculate_presence()

        tool_calls_made = _extract_tool_calls(reply_text, available_tools)
        model_used = result.get("model_used", fast_model)
        provider = result.get("provider") or "unknown"
        if provider == "unknown":
            lowered = model_used.lower()
            if "deepseek" in lowered:
                provider = "deepseek"
            elif "minimax" in lowered or "minim" in lowered:
                provider = "minimax"
            elif "gemini" in lowered:
                provider = "gemini"
        from core import metrics

        metrics.record_provider_latency(provider, True, execution_started)
        record_agent_success(agent_id, execution_started, model_used, provider)

        return {
            "reply": reply_text,
            "delay_ms": delay_ms,
            "presence": presence,
            "metadata": {
                "agent_id": agent_id,
                "executed_agent_id": agent_id,
                "response_identity": "Jennifer",
                "model_used": model_used,
                "provider": provider,
                "tool_rounds": result.get("tool_rounds", 0),
                "tool_calls": tool_calls_made,
                "has_audio": extra.get("has_audio", False),
            },
        }
    except LLMError as e:
        record_agent_failure(agent_id, execution_started, str(e))
        logger.error(f"LLM cascade failed for agent {agent_id}: {e}")
        return _error_response(503, "llm_unavailable", "Todos provedores LLM falharam.")
    except Exception as e:
        record_agent_failure(agent_id, execution_started, str(e))
        logger.exception("Unexpected error in _execute_agent")
        return _error_response(500, "internal_error", str(e))


def _extract_tool_calls(reply_text: str, available_tools: List[str]) -> List[Dict[str, Any]]:
    """Best-effort detection of tool calls mentioned in reply.

    Checks both resource name (calendar) and method (list_events).
    """
    tool_calls: List[Dict[str, Any]] = []
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
            "response_identity": "Jennifer",
        },
    }


async def _run_guard_graph(payload: Dict[str, Any], masked_text: str, intent: Dict[str, bool]) -> Dict[str, Any]:
    """Run the LangGraph guard pipeline for a single turn.

    Returns a normalized decision dict with ``verdict`` (``allow`` /
    ``request_oauth`` / ``deny`` / ``noop``) and an optional ``reply``
    the orchestrator should use when the verdict blocks the user.
    """
    try:
        from agent_orchestration.access_guardian import decide_guardian
        from agent_orchestration.graph import build_graph
    except Exception as exc:
        logger.warning("agent_orchestration unavailable, skipping guard: %s", exc)
        return {"verdict": "noop", "trace": [], "reason": f"graph_unavailable:{exc}"}

    capability = _intent_to_capability(intent)
    initial_state = {
        "instance": payload.get("instance", ""),
        "phone": payload.get("phone", ""),
        "sender_name": payload.get("sender_name", ""),
        "text": payload.get("text", ""),
        "masked_text": masked_text,
        "remote_jid": payload.get("extra", {}).get("remote_jid", ""),
        "intent": dict(intent),
        "capability": capability,
    }

    try:
        graph = build_graph()
        final = await graph.ainvoke(initial_state) if hasattr(graph, "ainvoke") else graph.invoke(initial_state)
    except Exception as exc:
        logger.warning("guard graph execution failed: %s", exc)
        decision = decide_guardian(
            instance=payload.get("instance", ""),
            phone=payload.get("phone", ""),
            capability=capability or "noop",
        )
        return {"verdict": decision.verdict, "decision": decision.to_dict(), "reason": exc.__class__.__name__}

    decision = (final or {}).get("guardian_decision") or {}
    verdict = decision.get("verdict", "allow")
    prefetch = (final or {}).get("prefetch")
    return {
        "verdict": verdict,
        "decision": decision,
        "prefetch": prefetch,
        "trace": (final or {}).get("trace", []),
    }


def _intent_to_capability(intent: Dict[str, bool]) -> str:
    if intent.get("is_calendar"):
        return "calendar.list_events"
    if intent.get("is_email"):
        return "gmail.search_messages"
    if intent.get("is_drive"):
        return "drive.search_files"
    return ""
