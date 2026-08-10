"""Agent loader - polls Firestore every 120s, caches agents/skills/tools in memory."""
import os
import time
import logging
import threading
from typing import Dict, Any, Optional, List

from core.timezone import now_brt

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = int(os.getenv("AGENT_RELOAD_INTERVAL_SEC", "120"))

_agents_cache: Dict[str, Dict[str, Any]] = {}
_skills_cache: Dict[str, Dict[str, Any]] = {}
_tools_cache: Dict[str, Dict[str, Any]] = {}

_last_loaded_at: float = 0
_last_reload_attempt_at: float = 0
_last_reload_error: Optional[str] = None
_config_generation: int = 0
_loader_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_cache_lock = threading.RLock()


def _now_iso() -> str:
    return now_brt().isoformat()


def _get_firestore_client():
    """Get Firestore client."""
    from google.cloud import firestore
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        return firestore.Client(project=project or "demo-project")
    if not project:
        return None
    return firestore.Client(project=project)


def _read_collection(collection_name: str) -> Optional[Dict[str, Dict[str, Any]]]:
    db = _get_firestore_client()
    if db is None:
        return None
    try:
        snapshot = {}
        for document in db.collection(collection_name).stream():
            data = document.to_dict()
            data["id"] = document.id
            snapshot[document.id] = data
        return snapshot
    except Exception as exc:
        logger.warning("Failed to load %s: %s", collection_name, exc)
        return None


def _replace_cache(target: Dict[str, Dict[str, Any]], snapshot: Dict[str, Dict[str, Any]]) -> None:
    with _cache_lock:
        target.clear()
        target.update(snapshot)


def _load_agents_from_firestore() -> int:
    snapshot = _read_collection("agents")
    if snapshot is None:
        return 0
    _replace_cache(_agents_cache, snapshot)
    logger.info("Loaded %s agents from Firestore", len(snapshot))
    return len(snapshot)


def _load_skills_from_firestore() -> int:
    snapshot = _read_collection("skills")
    if snapshot is None:
        return 0
    _replace_cache(_skills_cache, snapshot)
    logger.info("Loaded %s skills from Firestore", len(snapshot))
    return len(snapshot)


def _load_tools_from_firestore() -> int:
    snapshot = _read_collection("tools")
    if snapshot is None:
        return 0
    _replace_cache(_tools_cache, snapshot)
    logger.info("Loaded %s tools from Firestore", len(snapshot))
    return len(snapshot)


def _load_all() -> bool:
    global _last_loaded_at, _last_reload_attempt_at, _last_reload_error, _config_generation
    _last_reload_attempt_at = time.time()
    agents = _read_collection("agents")
    skills = _read_collection("skills")
    tools = _read_collection("tools")
    if agents is None or skills is None or tools is None:
        _last_reload_error = "firestore_unavailable_or_partial_reload"
        return False
    with _cache_lock:
        _agents_cache.clear()
        _agents_cache.update(agents)
        _skills_cache.clear()
        _skills_cache.update(skills)
        _tools_cache.clear()
        _tools_cache.update(tools)
        _last_loaded_at = time.time()
        _last_reload_error = None
        _config_generation += 1
    logger.info(
        "Atomic config reload complete: agents=%s skills=%s tools=%s generation=%s",
        len(agents),
        len(skills),
        len(tools),
        _config_generation,
    )
    return True


def _poll_loop():
    """Background polling loop."""
    logger.info(f"Agent loader starting (interval={POLL_INTERVAL_SEC}s)")
    while not _stop_event.is_set():
        try:
            _load_all()
        except Exception as e:
            logger.exception(f"Agent loader poll error: {e}")
        _stop_event.wait(POLL_INTERVAL_SEC)
    logger.info("Agent loader stopped")


def start_loader():
    """Start the background polling thread."""
    global _loader_thread
    if _loader_thread is not None and _loader_thread.is_alive():
        return
    _stop_event.clear()
    _load_all()
    seed_default_data()
    _loader_thread = threading.Thread(target=_poll_loop, daemon=True, name="agent-loader")
    _loader_thread.start()
    logger.info("Agent loader thread started")
    _prewarm_deep_agents()


def _prewarm_deep_agents() -> None:
    """Build the DeepAgent for every manager-* that has a registered
    prompt. Avoids the 13s cold-start penalty on the first request.

    Runs in a background thread so the FastAPI app starts accepting
    traffic immediately. Failures are logged and ignored — the
    per-request fallback to LLMProvider still works.
    """
    def _build_all() -> None:
        try:
            from deepagent_layer import get_deep_agent
            from deepagent_layer.agents import list_supported_managers
        except Exception as exc:
            logger.debug("prewarm skipped (deepagent_layer unavailable): %s", exc)
            return
        for manager_id in list_supported_managers():
            try:
                agent = get_deep_agent(manager_id)
                if agent is not None:
                    logger.info("prewarmed_deep_agent manager_id=%s", manager_id)
            except Exception as exc:
                logger.debug("prewarm_failed manager_id=%s err=%s", manager_id, exc)

    threading.Thread(target=_build_all, daemon=True, name="deepagent-prewarm").start()


def stop_loader():
    """Stop the background polling thread."""
    _stop_event.set()


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        agent = _agents_cache.get(agent_id)
        return dict(agent) if agent else None


def get_skill(skill_id: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        skill = _skills_cache.get(skill_id)
        return dict(skill) if skill else None


def get_tool_meta(tool_id: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        tool = _tools_cache.get(tool_id)
        return dict(tool) if tool else None


def list_agents() -> List[Dict[str, Any]]:
    with _cache_lock:
        return [dict(agent) for agent in _agents_cache.values()]


def list_skills() -> List[Dict[str, Any]]:
    with _cache_lock:
        return [dict(skill) for skill in _skills_cache.values()]


def list_tools() -> List[Dict[str, Any]]:
    with _cache_lock:
        return [dict(tool) for tool in _tools_cache.values()]


def force_reload() -> bool:
    success = _load_all()
    if success:
        logger.info("Forced reload complete")
    else:
        logger.warning("Forced reload kept last valid snapshot")
    return success


def upsert_agent(agent_id: str, data: Dict[str, Any]) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = _now_iso()
        db.collection("agents").document(agent_id).set(data, merge=True)
        logger.info(f"Agent '{agent_id}' upserted to Firestore")
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert agent '{agent_id}': {e}")
        return False


def delete_agent(agent_id: str) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        db.collection("agents").document(agent_id).delete()
        logger.info(f"Agent '{agent_id}' deleted from Firestore")
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to delete agent '{agent_id}': {e}")
        return False


def upsert_skill(skill_id: str, data: Dict[str, Any]) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = _now_iso()
        db.collection("skills").document(skill_id).set(data, merge=True)
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert skill '{skill_id}': {e}")
        return False


def upsert_tool(tool_id: str, data: Dict[str, Any]) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = _now_iso()
        db.collection("tools").document(tool_id).set(data, merge=True)
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert tool '{tool_id}': {e}")
        return False


def get_user(phone: str) -> Optional[Dict[str, Any]]:
    """Get user from Firestore usuarios/{phone}. Tenta multiplos formatos."""
    db = _get_firestore_client()
    if db is None:
        return None
    phones_to_try = _normalize_phones(phone)
    try:
        for p in phones_to_try:
            doc = db.collection("usuarios").document(p).get()
            if doc.exists:
                return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Failed to get user '{phone}': {e}")
        return None


def get_user_role(phone: str) -> str:
    """Role do usuario: 'admin' ou 'agent_user' (default).

    Owner de qualquer instancia (whatsapp_accounts.owner_phone) eh admin
    automatico — nao depende do campo role no Firestore. Demais telefones
    usam usuarios/{phone}.role (default 'agent_user').
    """
    if _is_instance_owner(phone):
        return "admin"
    user = get_user(phone)
    if not user:
        return "agent_user"
    return "agent_user" if user.get("role") not in ("admin", "agent_user") else user["role"]


def _is_instance_owner(phone: str) -> bool:
    """True se ``phone`` for owner_phone de alguma instancia Evolution."""
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if not digits:
        return False
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        for doc in db.collection("whatsapp_accounts").stream():
            owner = (doc.to_dict() or {}).get("owner_phone", "") or ""
            if "".join(c for c in str(owner) if c.isdigit()) == digits:
                return True
    except Exception:
        return False
    return False


def _normalize_phones(phone: str) -> List[str]:
    """Gera variacoes de formato de telefone para busca robusta."""
    candidates = []
    clean = phone.strip().lstrip("+")
    candidates.append(clean)
    if clean.startswith("55"):
        candidates.append(clean[2:])
    else:
        candidates.append("55" + clean)
    if not clean.startswith("+"):
        candidates.append("+" + clean)
    seen = []
    result = []
    for c in candidates:
        if c not in seen:
            seen.append(c)
            result.append(c)
    return result


def has_nickname(phone: str) -> bool:
    """Verifica se usuario ja tem apelido consentido no Firestore."""
    cache: Dict[str, bool] = getattr(has_nickname, "cache", {})
    if phone in cache:
        return cache[phone]
    import hashlib
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        ph = hashlib.sha256(phone.encode()).hexdigest()[:32]
        doc = db.collection("apelidos_custom").document(ph).get()
        if doc.exists:
            data = doc.to_dict()
            result = bool(data.get("accepted", False))
            cache[phone] = result
            has_nickname.cache = cache  # type: ignore[attr-defined]
            return result
        return False
    except Exception:
        return False


def save_user(phone: str, data: Dict[str, Any]) -> bool:
    """Create or update a user in Firestore."""
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = _now_iso()
        data["phone"] = phone
        db.collection("usuarios").document(phone).set(data, merge=True)
        return True
    except Exception as e:
        logger.error(f"Failed to save user '{phone}': {e}")
        return False


def _canonical_phone(phone: str) -> str:
    """Canonicaliza phone para E.164 BR: '55' + 11 digitos.

    Aceita +5511966830020, 55119966830020, 11966830020, 119966830020
    → sempre retorna 5511966830020 (ou o primeiro formato valido com 55).
    """
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if len(digits) == 12 and digits.startswith("55"):
        return digits  # já é 55 + 11
    if len(digits) == 11:
        return "55" + digits
    if len(digits) == 10:
        return "55" + digits
    return digits


def list_users() -> List[Dict[str, Any]]:
    """List all registered users, deduplicated by canonical phone."""
    db = _get_firestore_client()
    if db is None:
        return []
    try:
        seen: Dict[str, Dict[str, Any]] = {}
        for doc in db.collection("usuarios").stream():
            data = doc.to_dict() or {}
            phone = data.get("phone") or doc.id or ""
            canonical = _canonical_phone(phone)
            # Prefere o doc com google_oauth_token (mais completo)
            prev = seen.get(canonical)
            if prev is None or (not prev.get("google_oauth_token") and data.get("google_oauth_token")):
                merged = dict(prev or {})
                merged.update({k: v for k, v in data.items() if v})
                merged["phone"] = canonical
                merged["phone_canonical"] = canonical
                seen[canonical] = merged
        return list(seen.values())
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []


def get_config(section: str) -> Optional[Dict[str, Any]]:
    """Read config from Firestore config/{section}."""
    db = _get_firestore_client()
    if db is None:
        return None
    try:
        doc = db.collection("config").document(section).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Failed to read config/{section}: {e}")
        return None


def get_cache_stats() -> Dict[str, Any]:
    with _cache_lock:
        return {
            "agents": len(_agents_cache),
            "skills": len(_skills_cache),
            "tools": len(_tools_cache),
            "last_loaded_at": _last_loaded_at,
            "last_reload_attempt_at": _last_reload_attempt_at,
            "last_reload_error": _last_reload_error,
            "config_generation": _config_generation,
            "poll_interval_sec": POLL_INTERVAL_SEC,
        }


def seed_default_data():
    from scripts.seed_initial_data import DEFAULT_AGENTS, DEFAULT_SKILLS, DEFAULT_TOOLS

    with _cache_lock:
        missing_agents = not _agents_cache
        missing_skills = not _skills_cache
        missing_tools = not _tools_cache
    if not any([missing_agents, missing_skills, missing_tools]):
        return

    db = _get_firestore_client()
    if db is None:
        logger.info("Firestore not configured, filling missing in-memory defaults")
        with _cache_lock:
            if missing_agents:
                _agents_cache.update({agent["id"]: dict(agent) for agent in DEFAULT_AGENTS})
            if missing_skills:
                _skills_cache.update({skill["id"]: dict(skill) for skill in DEFAULT_SKILLS})
            if missing_tools:
                _tools_cache.update({tool["id"]: dict(tool) for tool in DEFAULT_TOOLS})
        return

    try:
        batch = db.batch()
        if missing_agents:
            for agent in DEFAULT_AGENTS:
                batch.set(db.collection("agents").document(agent["id"]), agent)
        if missing_skills:
            for skill in DEFAULT_SKILLS:
                batch.set(db.collection("skills").document(skill["id"]), skill)
        if missing_tools:
            for tool in DEFAULT_TOOLS:
                batch.set(db.collection("tools").document(tool["id"]), tool)
        batch.commit()
        logger.info(
            "Seeded missing defaults: agents=%s skills=%s tools=%s",
            missing_agents,
            missing_skills,
            missing_tools,
        )
        _load_all()
    except Exception as exc:
        logger.warning("Failed to seed Firestore, filling missing in-memory defaults: %s", exc)
        with _cache_lock:
            if missing_agents:
                _agents_cache.update({agent["id"]: dict(agent) for agent in DEFAULT_AGENTS})
            if missing_skills:
                _skills_cache.update({skill["id"]: dict(skill) for skill in DEFAULT_SKILLS})
            if missing_tools:
                _tools_cache.update({tool["id"]: dict(tool) for tool in DEFAULT_TOOLS})
