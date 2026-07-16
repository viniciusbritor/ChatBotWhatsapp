"""Agent loader - polls Firestore every 120s, caches agents/skills/tools in memory."""
import os
import time
import asyncio
import logging
import threading
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = int(os.getenv("AGENT_RELOAD_INTERVAL_SEC", "120"))

_agents_cache: Dict[str, Dict[str, Any]] = {}
_skills_cache: Dict[str, Dict[str, Any]] = {}
_tools_cache: Dict[str, Dict[str, Any]] = {}

_last_loaded_at: float = 0
_loader_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


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


def _load_agents_from_firestore() -> int:
    """Load all agents from Firestore."""
    db = _get_firestore_client()
    if db is None:
        logger.debug("Firestore not configured, skipping agents load")
        return 0
    try:
        docs = db.collection("agents").stream()
        count = 0
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            _agents_cache[doc.id] = data
            count += 1
        logger.info(f"Loaded {count} agents from Firestore")
        return count
    except Exception as e:
        logger.warning(f"Failed to load agents: {e}")
        return 0


def _load_skills_from_firestore() -> int:
    """Load all skills from Firestore."""
    db = _get_firestore_client()
    if db is None:
        return 0
    try:
        docs = db.collection("skills").stream()
        count = 0
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            _skills_cache[doc.id] = data
            count += 1
        logger.info(f"Loaded {count} skills from Firestore")
        return count
    except Exception as e:
        logger.warning(f"Failed to load skills: {e}")
        return 0


def _load_tools_from_firestore() -> int:
    """Load all tools from Firestore."""
    db = _get_firestore_client()
    if db is None:
        return 0
    try:
        docs = db.collection("tools").stream()
        count = 0
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            _tools_cache[doc.id] = data
            count += 1
        logger.info(f"Loaded {count} tools from Firestore")
        return count
    except Exception as e:
        logger.warning(f"Failed to load tools: {e}")
        return 0


def _load_all():
    """Load all collections from Firestore."""
    global _last_loaded_at
    _load_agents_from_firestore()
    _load_skills_from_firestore()
    _load_tools_from_firestore()
    _last_loaded_at = time.time()


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


def stop_loader():
    """Stop the background polling thread."""
    _stop_event.set()


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get agent from cache."""
    return _agents_cache.get(agent_id)


def get_skill(skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill from cache."""
    return _skills_cache.get(skill_id)


def get_tool_meta(tool_id: str) -> Optional[Dict[str, Any]]:
    """Get tool metadata from cache."""
    return _tools_cache.get(tool_id)


def list_agents() -> List[Dict[str, Any]]:
    """List all cached agents."""
    return list(_agents_cache.values())


def list_skills() -> List[Dict[str, Any]]:
    """List all cached skills."""
    return list(_skills_cache.values())


def list_tools() -> List[Dict[str, Any]]:
    """List all cached tools."""
    return list(_tools_cache.values())


def force_reload():
    """Force immediate reload from Firestore."""
    _load_all()
    logger.info("Forced reload complete")


def upsert_agent(agent_id: str, data: Dict[str, Any]) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
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
        data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
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
        data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        db.collection("tools").document(tool_id).set(data, merge=True)
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert tool '{tool_id}': {e}")
        return False


def get_user(phone: str) -> Optional[Dict[str, Any]]:
    """Get user from Firestore usuarios/{phone}."""
    db = _get_firestore_client()
    if db is None:
        return None
    try:
        doc = db.collection("usuarios").document(phone).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Failed to get user '{phone}': {e}")
        return None


def save_user(phone: str, data: Dict[str, Any]) -> bool:
    """Create or update a user in Firestore."""
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        data["phone"] = phone
        db.collection("usuarios").document(phone).set(data, merge=True)
        return True
    except Exception as e:
        logger.error(f"Failed to save user '{phone}': {e}")
        return False


def list_users() -> List[Dict[str, Any]]:
    """List all registered users."""
    db = _get_firestore_client()
    if db is None:
        return []
    try:
        return [doc.to_dict() for doc in db.collection("usuarios").stream()]
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
    """Get cache statistics."""
    return {
        "agents": len(_agents_cache),
        "skills": len(_skills_cache),
        "tools": len(_tools_cache),
        "last_loaded_at": _last_loaded_at,
        "poll_interval_sec": POLL_INTERVAL_SEC,
    }


def seed_default_data():
    """Seed default agents, skills, and tools if Firestore is empty.

    Called on startup if cache is empty.
    """
    if _agents_cache or _skills_cache or _tools_cache:
        return

    from scripts.seed_initial_data import DEFAULT_AGENTS, DEFAULT_SKILLS, DEFAULT_TOOLS

    db = _get_firestore_client()
    if db is None:
        logger.info("Firestore not configured, using in-memory defaults only")
        for agent in DEFAULT_AGENTS:
            _agents_cache[agent["id"]] = agent
        for skill in DEFAULT_SKILLS:
            _skills_cache[skill["id"]] = skill
        for tool in DEFAULT_TOOLS:
            _tools_cache[tool["id"]] = tool
        return

    try:
        batch = db.batch()
        for agent in DEFAULT_AGENTS:
            ref = db.collection("agents").document(agent["id"])
            batch.set(ref, agent)
        for skill in DEFAULT_SKILLS:
            ref = db.collection("skills").document(skill["id"])
            batch.set(ref, skill)
        for tool in DEFAULT_TOOLS:
            ref = db.collection("tools").document(tool["id"])
            batch.set(ref, tool)
        batch.commit()
        logger.info("Seeded default agents, skills, and tools to Firestore")
        _load_all()
    except Exception as e:
        logger.warning(f"Failed to seed to Firestore, using in-memory: {e}")
        for agent in DEFAULT_AGENTS:
            _agents_cache[agent["id"]] = agent
        for skill in DEFAULT_SKILLS:
            _skills_cache[skill["id"]] = skill
        for tool in DEFAULT_TOOLS:
            _tools_cache[tool["id"]] = tool