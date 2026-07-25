"""LangGraph orchestration graph for the Jennifer agent ecosystem.

The graph defines the runtime flow for a single WhatsApp turn:

```
[entry] -> jennifier_node -> classify_intent -> guard_node
                                                    |
                            +-----------------------+
                            |                       |
                    verdict=allow         verdict != allow
                            |                       |
                    manager_node              reply_node (early exit)
                            |
                    reply_node -> [END]
```

Every node is a plain async function operating on a :class:`TurnState`
dict. The graph itself uses LangGraph's :class:`StateGraph` so that:

- Cycles and conditional routing are explicit (no hidden control flow).
- Each step is observable via ``print_step`` for tracing.
- The state is serializable for replay/debugging.

The actual Google tool calls still happen in the manager nodes
(``calendar``, ``drive``, ``gmail``). This module is purely the
orchestrator shell.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _build_state_graph():
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError as exc:  # pragma: no cover - defensive
        raise RuntimeError("langgraph is required: pip install langgraph") from exc
    return StateGraph, START, END


TurnState = Dict[str, Any]


async def jennifier_node(state: TurnState) -> TurnState:
    state["jennifier_visited"] = True
    state.setdefault("trace", []).append({"node": "jennifier", "ok": True})
    return state


async def classify_intent_node(state: TurnState) -> TurnState:
    text = (state.get("text") or "").lower()
    intent = {
        "is_calendar": any(kw in text for kw in ("agenda", "compromisso", "reuniao", "calendar")),
        "is_drive": any(kw in text for kw in ("drive", "arquivo", "pasta", "documento")),
        "is_email": any(kw in text for kw in ("email", "e-mail", "inbox", "gmail")),
    }
    state["intent"] = intent
    state.setdefault("trace", []).append({"node": "classify_intent", "intent": intent})
    return state


async def guard_node(state: TurnState) -> TurnState:
    from agent_orchestration.access_guardian import decide_guardian

    intent = state.get("intent") or {}
    capability = _pick_capability(intent)
    if capability is None:
        state["guardian_decision"] = {
            "verdict": "allow",
            "capability": "none",
            "reason": "no_google_intent",
        }
        state.setdefault("trace", []).append({"node": "guardian", "verdict": "allow", "reason": "no_google_intent"})
        return state

    decision = decide_guardian(
        instance=state.get("instance", ""),
        phone=state.get("phone", ""),
        capability=capability,
    )
    state["guardian_decision"] = decision.to_dict()
    state["next_agent"] = _resolve_next_agent(decision.verdict)
    state.setdefault("trace", []).append({
        "node": "guardian",
        "verdict": decision.verdict,
        "capability": capability,
        "reason": decision.reason,
    })
    return state


def _pick_capability(intent: Dict[str, bool]) -> Optional[str]:
    if intent.get("is_calendar"):
        return "calendar.list_events"
    if intent.get("is_drive"):
        return "drive.search_files"
    if intent.get("is_email"):
        return "gmail.search_messages"
    return None


def _resolve_next_agent(verdict: str) -> Optional[str]:
    if verdict == "allow":
        return "manager"
    return None


async def manager_node(state: TurnState) -> TurnState:
    from orchestrator import _prefetch_calendar, _prefetch_email, _prefetch_drive_multi

    intent = state.get("intent") or {}
    instance = state.get("instance", "")
    phone = state.get("phone", "")
    text = state.get("text", "")
    prefetch = None
    try:
        if intent.get("is_calendar"):
            prefetch = await _prefetch_calendar(phone, instance)
        elif intent.get("is_email"):
            prefetch = await _prefetch_email(phone, instance)
        elif intent.get("is_drive"):
            prefetch = await _prefetch_drive_multi(phone, text, instance)
    except Exception as exc:
        logger.warning("manager_node prefetch failed: %s", exc)
    state["prefetch"] = prefetch
    state.setdefault("trace", []).append({"node": "manager", "prefetch_empty": prefetch is None})
    return state


async def reply_node(state: TurnState) -> TurnState:
    guardian = state.get("guardian_decision") or {}
    verdict = guardian.get("verdict", "allow")
    if verdict == "deny":
        state["reply"] = (
            f"Oi! Essa acao ({guardian.get('capability', '')}) so pode ser "
            "executada pelo proprietario da conta WhatsApp."
        )
        state["blocked"] = True
        state["blocked_reason"] = guardian.get("reason", "deny")
    elif verdict == "request_oauth":
        link = guardian.get("oauth_link", "")
        state["reply"] = (
            "Oi! Para acessar " + guardian.get("capability", "essa ferramenta") +
            ", preciso que voce autorize sua conta Google. "
            f"Acesse este link e faca o login: {link}"
        )
        state["blocked"] = True
        state["blocked_reason"] = guardian.get("reason", "request_oauth")
    else:
        prefetch = state.get("prefetch")
        state["reply"] = (
            "Resultado pronto." if prefetch else "Nenhum dado encontrado para essa consulta."
        )
    state.setdefault("trace", []).append({"node": "reply", "verdict": verdict})
    return state


def _route_after_guard(state: TurnState) -> str:
    decision = state.get("guardian_decision") or {}
    verdict = decision.get("verdict", "allow")
    if verdict == "allow":
        return "manager"
    return "reply"


def build_graph():
    StateGraph, START, END = _build_state_graph()
    graph = StateGraph(TurnState)

    graph.add_node("jennifier", jennifier_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("guardian", guard_node)
    graph.add_node("manager", manager_node)
    graph.add_node("reply", reply_node)

    graph.add_edge(START, "jennifier")
    graph.add_edge("jennifier", "classify_intent")
    graph.add_edge("classify_intent", "guardian")
    graph.add_conditional_edges(
        "guardian",
        _route_after_guard,
        {"manager": "manager", "reply": "reply"},
    )
    graph.add_edge("manager", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_turn(initial_state: TurnState) -> TurnState:
    graph = get_compiled_graph()
    final = await graph.ainvoke(initial_state) if hasattr(graph, "ainvoke") else graph.invoke(initial_state)
    return final
