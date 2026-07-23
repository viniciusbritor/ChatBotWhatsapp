import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.llm_provider import LLMProvider as _LLMProvider

BRT = timezone(timedelta(hours=-3))
HEALTH_WINDOW_SEC = int(os.getenv("AGENT_HEALTH_WINDOW_SEC", "86400"))

_HARDCODED_ROUTES = {
    "jennifier",
    "manager-calendar",
    "manager-drive",
    "manager-email",
    "manager-web",
    "agent-intimacy",
    "agent-learning",
    "agent-morality",
    "agent-locomocao",
    "agent-youtube",
}
_WORKER_AGENTS = {"ata-generator", "agent-proatividade"}
_INTERNAL_AGENTS = {"agent-privacy-guard", "agent-rag", "group-resolver"}
_GOOGLE_PREFIXES = ("calendar.", "drive.", "gmail.")
_telemetry: Dict[str, Dict[str, Any]] = {}
_telemetry_lock = threading.RLock()
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(BRT).isoformat()


def _model_provider_ready(model: str) -> bool:
    normalized = str(model or "").lower()
    if "gemini" in normalized:
        return False
    if not normalized:
        return False
    try:
        provider = _LLMProvider()
    except Exception as exc:
        logger.warning("_LLMProvider init failed: %s", exc)
        return False
    has_minimax = bool(provider.minimax_key)
    has_gemini = bool(provider.gemini_key)
    cascade_avail = (
        has_minimax
        or has_gemini
        or provider.is_available()
    )
    if any(
        token in normalized
        for token in ("minimax", "gemini", "claude", "gpt-")
    ):
        return cascade_avail
    return cascade_avail


def _execution_mode(agent: Dict[str, Any]) -> str:
    configured = agent.get("execution_mode")
    if configured:
        return configured
    agent_id = agent.get("id", "")
    if agent_id in _WORKER_AGENTS:
        return "worker"
    if agent_id in _INTERNAL_AGENTS:
        return "internal"
    return "reactive"


def _routable_agent_ids() -> set:
    from agent_loader import get_config

    agent_ids = set(_HARDCODED_ROUTES)
    config = get_config("routing") or {}
    for rule in config.get("rules", []):
        if rule.get("enabled", True) and rule.get("agent_id"):
            agent_ids.add(rule["agent_id"])
    return agent_ids


def start_agent_execution(agent_id: str) -> float:
    started_at = time.monotonic()
    with _telemetry_lock:
        telemetry = _telemetry.setdefault(agent_id, {})
        telemetry["in_flight"] = int(telemetry.get("in_flight", 0)) + 1
        telemetry["last_started_at"] = _now_iso()
    return started_at


def record_agent_success(agent_id: str, started_at: float, model: str = "", provider: str = "") -> None:
    with _telemetry_lock:
        telemetry = _telemetry.setdefault(agent_id, {})
        telemetry["in_flight"] = max(0, int(telemetry.get("in_flight", 1)) - 1)
        telemetry["last_success_at"] = _now_iso()
        telemetry["last_latency_ms"] = round((time.monotonic() - started_at) * 1000, 2)
        telemetry["last_model"] = model
        telemetry["last_provider"] = provider
        telemetry["success_count"] = int(telemetry.get("success_count", 0)) + 1


def record_agent_failure(agent_id: str, started_at: float, error: str) -> None:
    with _telemetry_lock:
        telemetry = _telemetry.setdefault(agent_id, {})
        telemetry["in_flight"] = max(0, int(telemetry.get("in_flight", 1)) - 1)
        telemetry["last_failure_at"] = _now_iso()
        telemetry["last_latency_ms"] = round((time.monotonic() - started_at) * 1000, 2)
        telemetry["last_error"] = str(error)[:200]
        telemetry["failure_count"] = int(telemetry.get("failure_count", 0)) + 1


def get_agent_telemetry(agent_id: str) -> Dict[str, Any]:
    with _telemetry_lock:
        return dict(_telemetry.get(agent_id, {}))


def _recent_success(telemetry: Dict[str, Any]) -> bool:
    value = telemetry.get("last_success_at")
    if not value:
        return False
    try:
        timestamp = datetime.fromisoformat(value)
        return (datetime.now(BRT) - timestamp.astimezone(BRT)).total_seconds() <= HEALTH_WINDOW_SEC
    except Exception:
        return False


def _recent_failure_after_success(telemetry: Dict[str, Any]) -> bool:
    failure = telemetry.get("last_failure_at")
    if not failure:
        return False
    success = telemetry.get("last_success_at")
    if not success:
        return True
    try:
        return datetime.fromisoformat(failure) > datetime.fromisoformat(success)
    except Exception:
        return True


def build_agent_inventory(instance: str = "jennifer", phone: Optional[str] = None) -> Dict[str, Any]:
    from agent_loader import get_cache_stats, get_user, list_agents
    from tool_registry import list_tool_ids

    agents = list_agents()
    executable_tools = set(list_tool_ids())
    routable_ids = _routable_agent_ids()
    user = get_user(phone) if phone else None
    user_has_oauth = bool((user or {}).get("google_oauth") or (user or {}).get("oauth"))
    items = []

    for source in sorted(agents, key=lambda item: (item.get("role", ""), item.get("id", ""))):
        agent = dict(source)
        agent_id = agent.get("id", "")
        enabled = bool(agent.get("enabled", True))
        instances = [str(value).lower() for value in agent.get("instances", [])]
        instance_match = not instances or instance.lower() in instances
        mode = _execution_mode(agent)
        routable = mode == "reactive" and agent_id in routable_ids
        declared_tools = list(agent.get("tools", []))
        missing_tools = sorted(tool for tool in declared_tools if tool not in executable_tools)
        tools_ready = not missing_tools
        provider_ready = _model_provider_ready(agent.get("model", ""))
        requires_user_oauth = any(tool.startswith(_GOOGLE_PREFIXES) for tool in declared_tools)
        user_ready = None if not phone or not requires_user_oauth else user_has_oauth
        platform_ready = enabled and instance_match and tools_ready and provider_ready
        telemetry = get_agent_telemetry(agent_id)
        recent_success = _recent_success(telemetry)
        recent_failure = _recent_failure_after_success(telemetry)

        if not enabled:
            status = "disabled"
        elif not instance_match:
            status = "instance_mismatch"
        elif mode == "reactive" and not routable:
            status = "not_routable"
        elif not tools_ready:
            status = "tools_missing"
        elif not provider_ready:
            status = "provider_unavailable"
        elif user_ready is False:
            status = "user_setup_required"
        elif recent_failure:
            status = "degraded"
        elif recent_success:
            status = "healthy"
        else:
            status = "unverified"

        items.append(
            {
                "agent_id": agent_id,
                "name": agent.get("name", agent_id),
                "role": agent.get("role", "specialist"),
                "execution_mode": mode,
                "configured": True,
                "loaded": True,
                "enabled": enabled,
                "instance_match": instance_match,
                "routable": routable,
                "declared_tools": declared_tools,
                "missing_tools": missing_tools,
                "tools_ready": tools_ready,
                "provider_ready": provider_ready,
                "platform_ready": platform_ready,
                "user_ready": user_ready,
                "healthy": status == "healthy",
                "operational": status == "healthy",
                "in_flight": int(telemetry.get("in_flight", 0)),
                "status": status,
                "last_success_at": telemetry.get("last_success_at"),
                "last_failure_at": telemetry.get("last_failure_at"),
                "last_latency_ms": telemetry.get("last_latency_ms"),
            }
        )

    counts = {
        "configured": len(items),
        "loaded": len(items),
        "enabled": sum(1 for item in items if item["enabled"]),
        "routable": sum(1 for item in items if item["routable"]),
        "healthy": sum(1 for item in items if item["healthy"]),
        "operational": sum(1 for item in items if item["operational"]),
        "unverified": sum(1 for item in items if item["status"] == "unverified"),
        "degraded": sum(1 for item in items if item["status"] == "degraded"),
        "in_flight": sum(item["in_flight"] for item in items),
    }
    return {
        "generated_at": _now_iso(),
        "scope": "current_runtime_instance",
        "instance": instance,
        "counts": counts,
        "agents": items,
        "cache": get_cache_stats(),
    }


def format_inventory_reply(inventory: Dict[str, Any]) -> str:
    counts = inventory["counts"]
    healthy = [item["name"] for item in inventory["agents"] if item["status"] == "healthy"]
    unavailable = [item["name"] for item in inventory["agents"] if item["status"] not in {"healthy", "unverified"}]
    healthy_text = ", ".join(healthy) if healthy else "nenhum com sucesso recente"
    unavailable_text = ", ".join(unavailable[:4]) if unavailable else "nenhum bloqueio estrutural"
    return (
        f"Tenho {counts['configured']} agentes cadastrados: {counts['routable']} roteaveis e {counts['healthy']} saudaveis.\n"
        f"Em execucao agora: {counts['in_flight']}; nao verificados: {counts['unverified']}.\n"
        f"Saudaveis: {healthy_text}.\n"
        f"Indisponiveis ou restritos: {unavailable_text}."
    )
