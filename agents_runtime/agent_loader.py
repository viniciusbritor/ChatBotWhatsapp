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
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "coherence-ominichannel-fs"
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        return firestore.Client(project=project or "demo-project")
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


def resolve_agent_for_instance(instance: str, agent_id: str) -> Optional[Dict[str, Any]]:
    """Resolve o agente correto para uma instancia (multi-tenant, M2).

    Busca primeiro {instance}__{agent_id} (instancia dedicada criada pelo
    seed), e faz fallback para o agent_id base (ex: jennifier). Isso permite
    que cada numero WhatsApp conectado tenha seus proprios agentes com
    system_prompt customizado, mantendo a Jennifer intacta.
    """
    if instance:
        prefixed = get_agent(f"{instance.lower()}__{agent_id}")
        if prefixed:
            return prefixed
    return get_agent(agent_id)


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


def delete_skill(skill_id: str) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        db.collection("skills").document(skill_id).delete()
        logger.info(f"Skill '{skill_id}' deleted from Firestore")
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to delete skill '{skill_id}': {e}")
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


def delete_tool(tool_id: str) -> bool:
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        db.collection("tools").document(tool_id).delete()
        logger.info(f"Tool '{tool_id}' deleted from Firestore")
        force_reload()
        return True
    except Exception as e:
        logger.error(f"Failed to delete tool '{tool_id}': {e}")
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


def get_coherence_module_role(email: str, uid: str = "") -> Optional[str]:
    """Consulta a permissao real configurada no Portal Coherence (user_permissions).

    Verifica a colecao `user_permissions` para o modulo omnichannel-agentes
    (chaves: {email}_omnichannel-agentes, {email}_omnichannel-agents, etc.).
    Retorna 'admin', 'agent_user' ou None (se nao encontrado).
    """
    email_clean = str(email or "").strip().lower()
    if not email_clean:
        return None
    db = _get_firestore_client()
    if db is None:
        return None
    try:
        possible_keys = [
            f"{email_clean}_omnichannel-agentes",
            f"{email_clean}_omnichannel-agents",
            f"{email_clean}_agents-omnichannel",
        ]
        for key in possible_keys:
            doc = db.collection("user_permissions").document(key).get()
            if doc.exists:
                data = doc.to_dict() or {}
                if data.get("is_active") is not False:
                    p_role = str(data.get("role", "") or "").strip().lower()
                    if p_role in ("admin", "super-admin", "super_admin"):
                        return "admin"
                    if p_role in ("analyst", "analista", "user", "agent_user", "member"):
                        return "agent_user"

        doc_user = db.collection("users").document(email_clean).get()
        if doc_user.exists:
            u_data = doc_user.to_dict() or {}
            g_role = str(u_data.get("global_role", "") or "").strip().lower()
            if g_role in ("analyst", "analista", "user", "agent_user"):
                return "agent_user"
            if u_data.get("is_super_admin") is True or g_role in ("admin", "super-admin"):
                return "admin"
    except Exception as exc:
        logger.debug("get_coherence_module_role failed: %s", exc)
    return None


def get_user_role(identifier: str) -> str:
    """Role do usuario: 'admin' ou 'agent_user' (default).

    Ordem de resolucao:
    1. Permissao explicita no Portal Coherence (user_permissions / users).
    2. Role explicito em usuarios/{identifier}.role.
    3. Whitelist config/admins.
    4. Owner de instancia (whatsapp_accounts.owner_phone).
    5. Default seguro: agent_user.
    """
    ident = str(identifier or "").strip().lower()
    if "@" in ident:
        coherence_role = get_coherence_module_role(ident)
        if coherence_role:
            return coherence_role

    user = get_user(identifier)
    if user:
        if user.get("email"):
            coherence_role = get_coherence_module_role(user["email"])
            if coherence_role:
                return coherence_role
        if user.get("role"):
            r = str(user.get("role", "")).strip().lower()
            if r in ("admin", "super-admin"):
                return "admin"
            if r in ("agent_user", "analyst", "analista", "user"):
                return "agent_user"

    if _is_admin_email(identifier) or _is_admin_uid(identifier):
        return "admin"

    if _is_instance_owner(identifier):
        return "admin"

    return "agent_user"


def _is_admin_email(identifier: str) -> bool:
    """True se ``identifier`` for um email na whitelist config/admins."""
    value = str(identifier or "").strip().lower()
    if not value or "@" not in value:
        return False
    admins = _get_admins_config()
    return value in {e.strip().lower() for e in admins.get("admin_emails", []) if e}


def _is_admin_uid(identifier: str) -> bool:
    """True se ``identifier`` for um Firebase UID na whitelist config/admins."""
    value = str(identifier or "").strip()
    if not value:
        return False
    admins = _get_admins_config()
    return value in {u.strip() for u in admins.get("admin_uids", []) if u}


def _get_admins_config() -> Dict[str, Any]:
    """Le config/admins do Firestore (com cache in-process de 60s)."""
    cached = getattr(_get_admins_config, "_cache", None)
    if cached and cached[1] > time.time() - 60:
        return cached[0]
    result = {"admin_emails": [], "admin_uids": []}
    db = _get_firestore_client()
    if db is not None:
        try:
            doc = db.collection("config").document("admins").get()
            if doc.exists:
                data = doc.to_dict() or {}
                result = {
                    "admin_emails": data.get("admin_emails") or [],
                    "admin_uids": data.get("admin_uids") or [],
                }
        except Exception:
            pass
    _get_admins_config._cache = (result, time.time())  # type: ignore[attr-defined]
    return result


def lookup_phone_by_email(email: str) -> str:
    """Encontra o phone do usuario que tem ``email`` vinculado.

    Varre usuarios/{phone} procurando doc com campo ``email``,
    ``alternate_emails`` ou ``google_oauth_token.email``.
    Retorna o doc id (phone) ou "" se nao encontrar.
    """
    value = str(email or "").strip().lower()
    if not value or "@" not in value:
        return ""
    db = _get_firestore_client()
    if db is None:
        return ""
    try:
        for doc in db.collection("usuarios").stream():
            data = doc.to_dict() or {}
            doc_email = str(data.get("email", "") or "").strip().lower()
            doc_emails = [doc_email]
            for alt in data.get("alternate_emails") or []:
                doc_emails.append(str(alt).strip().lower())
            token_email = str((data.get("google_oauth_token") or {}).get("email", "") or "").strip().lower()
            if token_email:
                doc_emails.append(token_email)
            if value in doc_emails and any(doc_emails):
                return str(data.get("phone") or doc.id)
    except Exception:
        return ""
    return ""


def lookup_phone_by_uid(uid: str) -> str:
    """Encontra o phone do usuario que tem ``firebase_uid`` vinculado."""
    value = str(uid or "").strip()
    if not value:
        return ""
    db = _get_firestore_client()
    if db is None:
        return ""
    try:
        for doc in db.collection("usuarios").stream():
            data = doc.to_dict() or {}
            doc_uid = str(data.get("firebase_uid", "") or "").strip()
            if doc_uid == value:
                return doc.id
    except Exception:
        return ""
    return ""


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


def resolve_owner_phone() -> str:
    """Retorna o owner_phone da instancia Evolution (fallback 5511967389901)."""
    db = _get_firestore_client()
    if db is None:
        return "5511967389901"
    try:
        for doc in db.collection("whatsapp_accounts").stream():
            data = doc.to_dict() or {}
            phone = data.get("owner_phone") or data.get("phone") or ""
            digits = "".join(c for c in str(phone) if c.isdigit())
            if digits:
                return digits
    except Exception:
        pass
    return "5511967389901"


def sync_user_profile(
    phone: str,
    email: str = "",
    uid: str = "",
    name: str = "",
    picture: str = "",
    role: str = "",
) -> bool:
    """Vincula email, uid, name, picture e role ao doc usuarios/{phone} no Firestore."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return False
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        update_data: Dict[str, Any] = {
            "updated_at": _now_iso(),
            "phone": canonical,
        }
        if email:
            update_data["email"] = str(email).strip().lower()
        if uid:
            update_data["firebase_uid"] = str(uid).strip()
        if name and name != "user":
            update_data["name"] = name
            update_data["display_name"] = name
        if picture:
            update_data["picture"] = picture
        if role:
            update_data["role"] = role
        db.collection("usuarios").document(canonical).set(update_data, merge=True)
        return True
    except Exception as exc:
        logger.debug("sync_user_profile failed for phone=%s: %s", phone, exc)
        return False


def _normalize_phones(phone: str) -> List[str]:
    """Gera variacoes de formato de telefone para busca robusta."""
    candidates = []
    clean = "".join(c for c in str(phone or "") if c.isdigit())
    if not clean:
        return []
    candidates.append(clean)
    canonical = _canonical_phone(clean)
    if canonical and canonical not in candidates:
        candidates.append(canonical)
    if clean.startswith("55") and len(clean) > 10:
        candidates.append(clean[2:])
    else:
        candidates.append("55" + clean)
    candidates.append("+" + clean)
    seen = []
    result = []
    for c in candidates:
        if c and c not in seen:
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
    """Create or update a user in Firestore.

    Salva no canonical e sincroniza em quaisquer documentos variantes
    existentes para evitar descompasso em webhooks internacionais.
    """
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        data["updated_at"] = _now_iso()
        canonical = _canonical_phone(phone) or "".join(c for c in str(phone or "") if c.isdigit())
        if not canonical:
            return False
        data["phone"] = canonical
        # Sincroniza em docs existentes de variantes do telefone
        for p in _normalize_phones(phone):
            try:
                doc = db.collection("usuarios").document(p).get()
                if doc.exists and p != canonical:
                    db.collection("usuarios").document(p).set(data, merge=True)
            except Exception:
                pass
        db.collection("usuarios").document(canonical).set(data, merge=True)
        return True
    except Exception as e:
        logger.error(f"Failed to save user '{phone}': {e}")
        return False


def is_user_approved(phone: str) -> bool:
    """Verifica se o usuario esta aprovado como admin ou analista.

    1. Owner da instancia e admin sempre sao aprovados.
    2. Usuario com is_approved=True ou token Google / email vinculado no Portal.
    3. Retorna False se o usuario for guest ou nao aprovado.
    """
    canonical = _canonical_phone(phone)
    if not canonical:
        return False
    if canonical == resolve_owner_phone() or _is_instance_owner(canonical):
        return True

    user = get_user(canonical)
    if not user:
        return False
    if user.get("is_approved") is True:
        return True
    if user.get("google_oauth_token") or user.get("approved_by"):
        return True
    if user.get("email"):
        coherence_role = get_coherence_module_role(user["email"])
        if coherence_role in ("admin", "agent_user", "analyst", "analista"):
            return True
    role = str(user.get("role", "")).strip().lower()
    if role in ("admin", "analyst", "analista", "agent_user") and role != "guest":
        return True
    return False


def _is_placeholder_name(name: Any) -> bool:
    """True se o nome e um placeholder generico, numero, vazio ou indefinido."""
    if not name or not isinstance(name, str):
        return True
    s = name.strip()
    if not s:
        return True
    if s.isdigit():
        return True
    if s.startswith("+"):
        return True
    lower = s.lower()
    if lower.startswith("contato") or lower in ("user", "usuario", "usuário", "none", "null", "guest", "undefined"):
        return True
    return False


def _lookup_portal_profile_for_phone_or_name(db, phone: str, name: str = "", email: str = "") -> Dict[str, Any]:
    """Busca informacoes ricas de perfil na colecao users do Portal Coherence."""
    if db is None:
        return {}
    res: Dict[str, Any] = {}
    try:
        clean_email = str(email or "").strip().lower()
        if clean_email and "@" in clean_email:
            u_doc = db.collection("users").document(clean_email).get()
            if u_doc.exists:
                u_data = u_doc.to_dict() or {}
                if u_data.get("name") and not _is_placeholder_name(u_data.get("name")):
                    res["name"] = str(u_data["name"]).strip()
                    res["display_name"] = str(u_data["name"]).strip()
                if u_data.get("picture"):
                    res["picture"] = u_data["picture"]
                if u_data.get("global_role") in ("analyst", "super-admin") or u_data.get("role") in ("analyst", "admin"):
                    res["role"] = "analyst"
                    res["is_approved"] = True
                return res

        clean_name_lower = str(name or "").strip().lower()
        for doc in db.collection("users").stream():
            u_data = doc.to_dict() or {}
            doc_email = str(u_data.get("email") or doc.id).strip().lower()
            doc_name = str(u_data.get("name") or "").strip()
            if clean_name_lower and doc_name and (clean_name_lower in doc_name.lower() or doc_name.lower() in clean_name_lower):
                if doc_name and not _is_placeholder_name(doc_name):
                    res["name"] = doc_name
                    res["display_name"] = doc_name
                if doc_email and "@" in doc_email:
                    res["email"] = doc_email
                if u_data.get("picture"):
                    res["picture"] = u_data["picture"]
                if u_data.get("global_role") in ("analyst", "super-admin") or u_data.get("role") in ("analyst", "admin"):
                    res["role"] = "analyst"
                    res["is_approved"] = True
                return res
    except Exception as exc:
        logger.debug("lookup_portal_profile failed: %s", exc)
    return res


def enrich_user_from_all_sources(phone: str) -> bool:
    """Enriquece o usuario no Firestore usando WhatsApp push_name, Portal users e Google API."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return False
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        doc_ref = db.collection("usuarios").document(canonical)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        curr_name = str(data.get("name") or "").strip()
        curr_email = str(data.get("email") or "").strip().lower()
        push_name = str(data.get("push_name") or "").strip()
        
        updates: Dict[str, Any] = {}
        
        if push_name and not _is_placeholder_name(push_name) and _is_placeholder_name(curr_name):
            updates["name"] = push_name
            updates["display_name"] = push_name
            curr_name = push_name
            
        portal_info = _lookup_portal_profile_for_phone_or_name(db, canonical, name=curr_name, email=curr_email)
        if portal_info:
            updates.update(portal_info)
            if portal_info.get("name"):
                curr_name = portal_info["name"]
            if portal_info.get("email"):
                curr_email = portal_info["email"]

        if data.get("google_oauth_token") and (not curr_email or _is_placeholder_name(curr_name)):
            try:
                from core.oauth_per_user import get_valid_user_token
                import requests
                tok = get_valid_user_token(canonical)
                if tok:
                    gm_res = requests.get(
                        "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                        headers={"Authorization": f"Bearer {tok}"},
                        timeout=5,
                    )
                    if gm_res.status_code == 200:
                        gm_email = str(gm_res.json().get("emailAddress") or "").strip().lower()
                        if gm_email and "@" in gm_email:
                            updates["email"] = gm_email
                            p_info = _lookup_portal_profile_for_phone_or_name(db, canonical, email=gm_email)
                            if p_info:
                                updates.update(p_info)
            except Exception:
                pass
                
        if updates:
            updates["updated_at"] = _now_iso()
            doc_ref.set(updates, merge=True)
            return True
        return False
    except Exception as exc:
        logger.debug("enrich_user_from_all_sources failed for %s: %s", phone, exc)
        return False


def enrich_all_registered_users() -> int:
    """Varre e enriquece todos os usuarios cadastrados no Firestore."""
    db = _get_firestore_client()
    if db is None:
        return 0
    count = 0
    try:
        for doc in db.collection("usuarios").stream():
            phone = str(doc.to_dict().get("phone") or doc.id)
            if enrich_user_from_all_sources(phone):
                count += 1
    except Exception as exc:
        logger.error("enrich_all_registered_users failed: %s", exc)
    return count


def ensure_user_registered(phone: str, sender_name: str = "", instance: str = "jennifer") -> bool:
    """Garante que qualquer contato que interaja com a Jennifer fique registrado em usuarios/{phone} com nome real enriquecido."""
    canonical = _canonical_phone(phone)
    if not canonical:
        return False
    db = _get_firestore_client()
    if db is None:
        return False
    try:
        doc_ref = db.collection("usuarios").document(canonical)
        doc = doc_ref.get()
        payload: Dict[str, Any] = {
            "phone": canonical,
            "updated_at": _now_iso(),
            "instance": instance,
        }
        clean_sender = str(sender_name or "").strip()
        has_valid_sender = bool(clean_sender and not _is_placeholder_name(clean_sender))
        if has_valid_sender:
            payload["push_name"] = clean_sender
            payload["name"] = clean_sender
            payload["display_name"] = clean_sender

        if not doc.exists:
            payload["created_at"] = _now_iso()
            payload["role"] = "guest"
            payload["is_approved"] = False
            
            portal_info = _lookup_portal_profile_for_phone_or_name(db, canonical, name=clean_sender)
            if portal_info:
                payload.update(portal_info)
                
            doc_ref.set(payload)
        else:
            existing = doc.to_dict() or {}
            curr_name = str(existing.get("name") or "").strip()
            if has_valid_sender and _is_placeholder_name(curr_name):
                payload["name"] = clean_sender
                payload["display_name"] = clean_sender
                
            if not existing.get("email") or not existing.get("picture") or _is_placeholder_name(curr_name):
                portal_info = _lookup_portal_profile_for_phone_or_name(
                    db,
                    canonical,
                    name=clean_sender or curr_name,
                    email=existing.get("email", ""),
                )
                if portal_info:
                    payload.update(portal_info)
                    
            doc_ref.set(payload, merge=True)
        return True
    except Exception as exc:
        logger.debug("ensure_user_registered failed for phone=%s: %s", phone, exc)
        return False


def _canonical_phone(phone: str) -> str:
    """Canonicaliza phone para E.164.

    Para números brasileiros sem 55:
    - 11 dígitos com DDD válido (11 a 99) e nono dígito 9 (ex: 11966830020) → 5511966830020
    - 10 dígitos com DDD válido (11 a 99) (ex: 1132345678) → 551132345678
    - 12 ou 13 dígitos começando com 55 (ex: 5511966830020) → 5511966830020
    Para números internacionais (ex: Suíça 41783430540, EUA 14155552671, etc.):
    - Mantém os dígitos originais sem prefixar 55 indevidamente.
    """
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if not digits:
        return ""
    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits
    if len(digits) == 11 and digits.startswith("55"):
        return digits
    # Se tem 11 dígitos e começa com DDD brasileiro (11 a 99) com 9 no 3º dígito:
    if len(digits) == 11 and digits[:2].isdigit() and int(digits[:2]) in range(11, 100) and digits[2] == "9":
        return "55" + digits
    # Se tem 10 dígitos e começa com DDD brasileiro (11 a 99) e dígitos fixos (2 a 5):
    if len(digits) == 10 and digits[:2].isdigit() and int(digits[:2]) in range(11, 100) and digits[2] in "2345":
        return "55" + digits
    return digits


def list_users() -> List[Dict[str, Any]]:
    """List all registered users, deduplicated by canonical phone.

    Quando existem docs duplicados (ex: ``usuarios/11966830020`` e
    ``usuarios/5511966830020``), o merge prefere o documento com o token
    OAuth MAIS completo (mais scopes); em empate, o com
    ``google_oauth_linked_at``/``updated_at`` mais recente. Isso evita que
    um doc antigo com menos scopes "sombre" o token reautorizado.
    """
    db = _get_firestore_client()
    if db is None:
        return []
    try:
        seen: Dict[str, Dict[str, Any]] = {}
        for doc in db.collection("usuarios").stream():
            data = doc.to_dict() or {}
            if not _user_doc_is_real(data):
                continue
            phone = data.get("phone") or doc.id or ""
            canonical = _canonical_phone(phone)
            prev = seen.get(canonical)
            if prev is None:
                seen[canonical] = _merge_user_docs({}, data, canonical)
                continue
            if _user_doc_is_better(data, prev):
                seen[canonical] = _merge_user_docs(prev, data, canonical)
        return list(seen.values())
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []


_GHOST_ONLY_FIELDS = {"group_memberships", "group_memberships_updated_at"}


def _user_doc_is_real(data: Dict[str, Any]) -> bool:
    """True se o doc representa um usuario real ou contato catalogado."""
    if data.get("phone") or data.get("name") or data.get("role") or data.get("google_oauth_token"):
        return True
    for key, value in data.items():
        if key in _GHOST_ONLY_FIELDS:
            continue
        if value:
            return True
    return False


def _user_doc_scopes(data: Dict[str, Any]) -> int:
    token = data.get("google_oauth_token") or {}
    return len(token.get("scopes") or data.get("scopes") or [])


def _user_doc_timestamp(data: Dict[str, Any]) -> str:
    return str(
        data.get("google_oauth_linked_at")
        or data.get("updated_at")
        or ""
    )


def _user_doc_is_better(candidate: Dict[str, Any], current: Dict[str, Any]) -> bool:
    """True se ``candidate`` deve substituir ``current`` (mais scopes ou mais recente)."""
    if _user_doc_scopes(candidate) > _user_doc_scopes(current):
        return True
    if _user_doc_scopes(candidate) == _user_doc_scopes(current):
        if _user_doc_timestamp(candidate) > _user_doc_timestamp(current):
            return True
    return False


def _merge_user_docs(base: Dict[str, Any], data: Dict[str, Any], canonical: str) -> Dict[str, Any]:
    """Faz merge preservando o token mais completo do doc que esta entrando."""
    merged = dict(base)
    merged.update({k: v for k, v in data.items() if v})
    merged["phone"] = canonical
    merged["phone_canonical"] = canonical
    return merged


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
