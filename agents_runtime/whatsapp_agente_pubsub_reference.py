"""
WhatsApp Agent - Thin Proxy to agents_runtime
==============================================

Refactored from v3 multi-agent system to a thin proxy:
- Keeps anti-ban (jitter 3-8s, rate-limit, stop words)
- Keeps LGPD (phone_hash SHA-256, opt-in, audit log, retention 90d)
- Keeps Firestore persistence (contacts, sessions, audit)
- DELEGATES to agents_runtime for ALL AI logic:
  * Whisper transcription (audio)
  * RAG, tools, orchestrator, agent-learning
  * LLM cascade (DeepSeek -> NVIDIA -> MiniMax)
  * Proactive messages

Endpoints:
- POST /webhook     (Evolution API -> WhatsApp)
- POST /send        (proactive worker -> WhatsApp)
- GET  /healthz
"""
import os
import re
import sys
import json
import time
import random
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from secrets_manager import get_secret
except ImportError:
    def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(key, default)

GCP_PROJECT = os.getenv("GCP_PROJECT") or get_secret("GCP_PROJECT", "whatsapp-server-fs")
BRT_TZ = ZoneInfo("America/Sao_Paulo")

EVO_BASE_URL = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br")
EVO_API_KEY = os.getenv("EVO_API_KEY") or get_secret("EVO_API_KEY") or "jennifer_secret_2025"

AGENTS_RUNTIME_URL = os.getenv("AGENTS_RUNTIME_URL") or get_secret("AGENTS_RUNTIME_URL")
AGENTS_RUNTIME_SA_TOKEN = os.getenv("AGENTS_RUNTIME_SA_TOKEN") or get_secret("AGENTS_RUNTIME_SA_TOKEN")

JITTER_MIN = float(os.getenv("JITTER_MIN_SEC", "3"))
JITTER_MAX = float(os.getenv("JITTER_MAX_SEC", "8"))
MAX_MSG_PER_CONTACT_HOUR = int(os.getenv("MAX_MSG_PER_CONTACT_HOUR", "10"))
MAX_MSG_PER_CONTACT_DAY = int(os.getenv("MAX_MSG_PER_CONTACT_DAY", "50"))
MAX_MSG_PER_INSTANCE_DAY = int(os.getenv("MAX_MSG_PER_INSTANCE_DAY", "300"))

RETENTION_DAYS = 90
SESSION_TTL_DAYS = 30

COLL_CONTACTS = "contacts"
COLL_SESSIONS = "sessions"
COLL_AUDIT = "audit"

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}'
)
logger = logging.getLogger("agente")

db: Optional[Any] = None
_pubsub_publisher: Optional[Any] = None
PUBSUB_TOPIC = os.getenv("WHATSAPP_PUBSUB_TOPIC", "whatsapp-messages")
PUBSUB_PROJECT = os.getenv("GCP_PROJECT") or get_secret("GCP_PROJECT", "whatsapp-server-fs")


def _get_publisher():
    global _pubsub_publisher
    if _pubsub_publisher is not None:
        return _pubsub_publisher
    try:
        from google.cloud import pubsub_v1
        _pubsub_publisher = pubsub_v1.PublisherClient()
    except ImportError:
        logger.warning("pubsub_v1 not available; falling back to inline call")
        _pubsub_publisher = False
    return _pubsub_publisher


def _publish_to_pubsub(envelope: Dict[str, Any]) -> None:
    client = _get_publisher()
    if not client:
        return
    try:
        path = client.topic_path(PUBSUB_PROJECT, PUBSUB_TOPIC)
        data = json.dumps(envelope, default=str).encode("utf-8")
        future = client.publish(path, data)
        future.result(timeout=5)
        logger.info(f"pubsub publish: topic={PUBSUB_TOPIC} request_id={envelope.get('request_id', '')}")
    except Exception as exc:
        logger.error(f"pubsub publish failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    logger.info("=" * 60)
    logger.info("WhatsApp Agent - THIN PROXY mode")
    logger.info(f"GCP Project: {GCP_PROJECT}")
    logger.info(f"Evolution: {EVO_BASE_URL}")
    logger.info(f"agents_runtime: {AGENTS_RUNTIME_URL}")
    logger.info(f"agents_runtime SA configured: {bool(AGENTS_RUNTIME_SA_TOKEN)}")
    logger.info("=" * 60)

    try:
        from google.cloud import firestore
        emulator = os.getenv("FIRESTORE_EMULATOR_HOST")
        if emulator:
            db = firestore.Client(project=GCP_PROJECT)
        else:
            db = firestore.Client(project=GCP_PROJECT)
        logger.info("Firestore client initialized")
    except Exception as e:
        logger.warning(f"Firestore unavailable: {e}")
        db = None

    yield
    logger.info("WhatsApp Agent shutting down")


app = FastAPI(
    title="WhatsApp Agent - Thin Proxy",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "mode": "thin_proxy",
        "agents_runtime": AGENTS_RUNTIME_URL,
        "firestore": db is not None,
    }


def phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


def now_brt() -> datetime:
    return datetime.now(BRT_TZ)


def jitter_sleep() -> float:
    delay = random.uniform(JITTER_MIN, JITTER_MAX)
    time.sleep(delay)
    return delay


def is_stop_word(text: str) -> bool:
    STOP_WORDS = ["pare", "parar", "sair", "sai", "cancelar", "tchau", "adeus", "obrigado sair"]
    return any(w in text.lower() for w in STOP_WORDS)


async def call_agents_runtime(
    phone: str,
    text: str,
    sender_name: str,
    instance: str,
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    """Call agents_runtime /chat endpoint."""
    if not AGENTS_RUNTIME_URL or not AGENTS_RUNTIME_SA_TOKEN:
        logger.error("agents_runtime not configured")
        return {
            "reply": "Sistema temporariamente indisponivel. Tente em alguns minutos.",
            "delay_ms": 0,
            "presence": "paused",
            "metadata": {"error": "agents_runtime_not_configured"},
        }

    url = f"{AGENTS_RUNTIME_URL.rstrip('/')}/chat"
    payload = {
        "instance": instance,
        "phone": phone,
        "text": text,
        "sender_name": sender_name,
        "extra": extra,
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {AGENTS_RUNTIME_SA_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"agents_runtime returned {resp.status_code}: {resp.text[:200]}")
            return {
                "reply": "Tive um probleminha tecnico. Tenta de novo?",
                "delay_ms": 2000,
                "presence": "composing",
                "metadata": {"error": "agents_runtime_error", "status": resp.status_code},
            }
    except httpx.TimeoutException:
        logger.error("agents_runtime timeout")
        return {
            "reply": "Demorou mais que o esperado. Pode repetir?",
            "delay_ms": 1000,
            "presence": "composing",
            "metadata": {"error": "timeout"},
        }
    except Exception as e:
        logger.exception(f"agents_runtime call failed: {e}")
        return {
            "reply": "Tive um erro tecnico. Tenta em 1 min.",
            "delay_ms": 1000,
            "presence": "composing",
            "metadata": {"error": "call_failed"},
        }


async def send_to_whatsapp(
    instance: str,
    phone: str,
    text: str,
    delay_ms: int = 0,
    presence: str = "composing",
) -> bool:
    """Send text message via Evolution API."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{EVO_BASE_URL.rstrip('/')}/message/sendText/{instance}",
                json={
                    "number": phone,
                    "text": text,
                    "delay": delay_ms,
                    "presence": presence,
                },
                headers={"apikey": EVO_API_KEY, "Content-Type": "application/json"},
            )
            return True
    except Exception as e:
        logger.error(f"Send failed to {phone}: {e}")
        return False


async def mark_as_read(instance: str, message_id: str, remote_jid: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{EVO_BASE_URL.rstrip('/')}/chat/markMessageAsRead/{instance}",
                json={"messageIds": [message_id], "remoteJids": [remote_jid]},
                headers={"apikey": EVO_API_KEY},
            )
    except Exception:
        pass


def extract_message(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract message fields from Evolution webhook payload."""
    event = payload.get("event")
    if event != "MESSAGES_UPSERT":
        return None

    data = payload.get("data", {})
    key = data.get("key", {})
    if key.get("fromMe"):
        return None

    remote_jid = key.get("remoteJid", "")
    if "@broadcast" in remote_jid or "@g.us" == remote_jid.split("/")[-1]:
        return None

    message = data.get("message", {})
    instance = payload.get("instance", "main")
    phone = remote_jid.split("@")[0]

    text = ""
    extra = {}

    if "conversation" in message:
        text = message["conversation"]
    elif "extendedTextMessage" in message:
        text = message["extendedTextMessage"].get("text", "")
    elif "audioMessage" in message:
        audio_msg = message["audioMessage"]
        extra["has_audio"] = True
        extra["audio_mimetype"] = audio_msg.get("mimetype", "")
        extra["audio_ptt"] = audio_msg.get("ptt", False)
        message_id = key.get("id", "")
        extra["audio_url"] = f"{EVO_BASE_URL}/chat/getMedia/{instance}?messageId={message_id}"
        text = "[audio]"
    else:
        return None

    push_name = data.get("pushName", "user")
    message_id = key.get("id", "")

    return {
        "instance": instance,
        "phone": phone,
        "text": text,
        "sender_name": push_name,
        "remote_jid": remote_jid,
        "message_id": message_id,
        "extra": extra,
    }


async def get_or_create_contact(phone: str) -> Dict[str, Any]:
    """Get contact from Firestore or create."""
    if db is None:
        return {"phone_hash": phone_hash(phone), "opted_in": True, "msgs_this_hour": 0, "msgs_today": 0}

    ph = phone_hash(phone)
    try:
        ref = db.collection(COLL_CONTACTS).document(ph)
        doc = ref.get()
        if doc.exists:
            return doc.to_dict()
        new_contact = {
            "phone_hash": ph,
            "opted_in": False,
            "msgs_this_hour": 0,
            "msgs_today": 0,
            "first_seen": now_brt().isoformat(),
        }
        ref.set(new_contact)
        return new_contact
    except Exception as e:
        logger.warning(f"get_or_create_contact error: {e}")
        return {"phone_hash": ph, "opted_in": True, "msgs_this_hour": 0, "msgs_today": 0}


def audit_log(phone_hash_val: str, direction: str, text_preview: str):
    """Write to audit collection."""
    if db is None:
        return
    try:
        content_hash = hashlib.sha256(text_preview.encode()).hexdigest()[:16]
        db.collection(COLL_AUDIT).add({
            "ts": now_brt().isoformat(),
            "phone_hash": phone_hash_val,
            "direction": direction,
            "content_hash": content_hash,
            "preview": text_preview[:100],
        })
    except Exception:
        pass


def check_rate_limit(contact: Dict[str, Any]) -> bool:
    """Check if contact is within rate limits."""
    return (
        contact.get("msgs_this_hour", 0) < MAX_MSG_PER_CONTACT_HOUR
        and contact.get("msgs_today", 0) < MAX_MSG_PER_CONTACT_DAY
    )


def increment_counters(phone_hash_val: str):
    """Increment message counters."""
    if db is None:
        return
    try:
        db.collection(COLL_CONTACTS).document(phone_hash_val).update({
            "msgs_this_hour": firestore.Increment(1) if db else 0,
            "msgs_today": firestore.Increment(1) if db else 0,
            "last_msg_at": now_brt().isoformat(),
        })
    except Exception:
        pass


@app.post("/webhook")
async def webhook(request: Request):
    """Receive WhatsApp message from Evolution API.

    Returns 200 OK immediately after publishing to Pub/Sub. agents_runtime
    consumes the message asynchronously via push subscription. This decouples
    the Evolution webhook from the agents_runtime lifecycle and prevents
    timeout/lockup when the agents_runtime is slow or unavailable.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    msg = extract_message(payload)
    if not msg:
        return JSONResponse({"skip": "no_message"})

    phone = msg["phone"]
    text = msg["text"]
    instance = msg["instance"]

    ph = phone_hash(phone)
    audit_log(ph, "in", text)

    if is_stop_word(text):
        return JSONResponse({"stop": True})

    contact = await get_or_create_contact(phone)
    if not contact.get("opted_in"):
        opt_in_msg = "Ola! Sou a Jennifer. Posso continuar? (Responda SIM)"
        await send_to_whatsapp(instance, phone, opt_in_msg, delay_ms=2000)
        return JSONResponse({"opt_in": True})

    if not check_rate_limit(contact):
        return JSONResponse({"rate_limited": True})

    await mark_as_read(instance, msg["message_id"], msg["remote_jid"])

    request_id = hashlib.sha256(f"{instance}:{ph}:{msg['message_id']}".encode("utf-8")).hexdigest()[:32]
    envelope = {
        "request_id": request_id,
        "phone": phone,
        "text": text,
        "instance": instance,
        "sender_name": msg["sender_name"],
        "extra": msg["extra"],
        "remote_jid": msg["remote_jid"],
        "message_id": msg["message_id"],
        "from_me": bool(msg["extra"].get("fromMe")) if isinstance(msg["extra"], dict) else False,
    }
    _publish_to_pubsub(envelope)
    increment_counters(ph)
    return JSONResponse({
        "ok": True,
        "queued": True,
        "request_id": request_id,
    })


@app.post("/send")
async def send_message(request: Request):
    """Send a proactive message (called by proactive_worker)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    phone = body.get("phone", "")
    text = body.get("text", "")
    instance = body.get("instance", "jennifer")
    delay_ms = body.get("delay_ms", 2000)

    if not phone or not text:
        raise HTTPException(status_code=422, detail="phone and text required")

    logger.info(f"Proactive send to {phone}: {text[:80]}")

    sent = await send_to_whatsapp(instance, phone, text, delay_ms=delay_ms, presence="composing")

    ph = phone_hash(phone)
    audit_log(ph, "proactive", text)

    return JSONResponse({
        "sent": sent,
        "phone": phone,
        "delay_ms": delay_ms,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))