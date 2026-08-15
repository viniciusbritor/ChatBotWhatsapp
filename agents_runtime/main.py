"""Main FastAPI application for agents_runtime.

Endpoints:
- GET  /healthz       (public)
- GET  /version       (Bearer SA)
- POST /chat          (Bearer SA, called by webhook Evolution via /webhook)
- POST /proactive/send (Bearer SA, called by proactive_worker)
- /admin/*            (Bearer SA, proxy from Portal)
"""
import os
import json
import asyncio
import hmac
import logging
import re
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse as _JSONResponse, HTMLResponse, Response
from starlette.responses import RedirectResponse

from core.auth import auth_middleware
from core.delay_calculator import calculate_delay_ms
from core.logging import configure_logging
from core.masker import mask_pii
from core.timezone import now_brt
from core import metrics
from agent_loader import start_loader, stop_loader, list_agents, list_skills, list_tools, get_agent
from agent_loader import get_skill, get_tool_meta
from agent_loader import upsert_agent, delete_agent, upsert_skill, delete_skill, upsert_tool, delete_tool
from agent_loader import get_user, save_user, list_users
from orchestrator import orchestrate, get_recent_interactions, drain_indexing_tasks, index_audio_failure_for_audit


class JSONResponse(_JSONResponse):
    """JSONResponse with ensure_ascii=False for UTF-8 characters."""
    def render(self, content) -> bytes:
        import json
        return json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")


configure_logging()
logger = logging.getLogger(__name__)

VERSION = "1.0.0"
COMMIT_SHA = os.getenv("COMMIT_SHA", "local-dev")
DEPLOYED_AT = os.getenv("DEPLOYED_AT", "local")

# URL do Portal Coherence (frontend que emite o JWT). Test = portal-test.
COHERENCE_PORTAL_URL = (
    os.getenv("COHERENCE_PORTAL_URL")
    or os.getenv("PORTAL_URL")
    or "https://coherence-portal-test-894828119087.us-central1.run.app"
).rstrip("/")

MARK_READ_TIMEOUT_COLD_SEC = float(os.getenv("MARK_READ_TIMEOUT_COLD_SEC", "12"))
MARK_READ_TIMEOUT_WARM_SEC = float(os.getenv("MARK_READ_TIMEOUT_WARM_SEC", "5"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init/cleanup."""
    logger.info(f"agents_runtime v{VERSION} starting (commit={COMMIT_SHA})")

    await _validate_openai_key_on_startup()

    start_loader()
    logger.info("Agent loader started")

    yield

    await drain_indexing_tasks()
    stop_loader()
    logger.info("agents_runtime shutting down")


async def _validate_openai_key_on_startup() -> None:
    """PHASE 2 do loop RAG: valida OPENAI_API_KEY no boot.

    Falha nao-crash: log de erro apenas. Se key invalida, RAG
    indexing continuara falhando silenciosamente (ate Phase 4
    partial success), mas pelo menos o erro fica visivel.
    """
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        logger.error("OPENAI_API_KEY not set - RAG embeddings will fail")
        return
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        client.embeddings.create(
            model="text-embedding-3-small",
            input="ping",
        )
        logger.info("OPENAI_API_KEY valid (boot ping succeeded)")
    except Exception as exc:
        key_prefix = (key[:7] if key else "") + "***"
        logger.error(
            "OPENAI_API_KEY validation failed type=%s key_prefix=%s msg=%s",
            type(exc).__name__, key_prefix, str(exc)[:100],
        )


app = FastAPI(
    title="agents_runtime",
    version=VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.middleware("http")(auth_middleware)

# ==========================================================================
# Portal React (Google AI Studio / Stitch) — servido como static files.
# Fallback: se o dist nao existir, o module_ui.py legado continua servindo.
# ==========================================================================
_PORTAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portal", "dist")


def _portal_available() -> bool:
    return os.path.isdir(_PORTAL_DIR) and os.path.isfile(os.path.join(_PORTAL_DIR, "index.html"))


if _portal_available():
    try:
        from fastapi.staticfiles import StaticFiles

        app.mount("/portal", StaticFiles(directory=_PORTAL_DIR, html=True), name="portal")
        logger.info("portal_react_mounted dir=%s", _PORTAL_DIR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("portal_react_mount_failed exc=%s", exc)



@app.get("/healthz")
async def healthz():  # alias for compatibility with previous deployments
    return _health_payload()


@app.get("/health")
async def health():
    """Public health check endpoint (alias)."""
    return _health_payload()


def _health_payload() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": VERSION,
        "commit_sha": COMMIT_SHA,
        "deployed_at": DEPLOYED_AT,
    }


def _short_sha(value: str) -> str:
    if not value:
        return ""
    if "ghtokens" in value or "/" in value:
        return value.split("/")[-1][:7]
    return value[:7]


@app.get("/version")
async def version():
    """Version info (Bearer SA required via middleware)."""
    from agent_loader import get_cache_stats

    return {
        "version": VERSION,
        "commit_sha": _short_sha(COMMIT_SHA),
        "commit_sha_full": COMMIT_SHA,
        "deployed_at": DEPLOYED_AT,
        "python_version": "3.12",
        "agents_loaded": get_cache_stats().get("agents", 0),
    }


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus exposition format (text/plain)."""
    try:
        from core.agent_status import build_agent_inventory

        inventory = build_agent_inventory(instance=os.getenv("INSTANCE", "Jennifer"))
        metrics.observe_inventory(inventory)
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics inventory observe skipped: %s", exc)
    payload = metrics.generate_metrics()
    return Response(content=payload, media_type=metrics.METRICS_CONTENT_TYPE)


@app.post("/chat")
async def chat(request: Request):
    """Receive a WhatsApp message and return Jennifer's response.

    Request body:
        {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": "Oi ou ausente quando houver audio",
            "sender_name": "Vinicius",
            "extra": {"has_audio": false, "audio_base64": null, "audio_url": null, ...}
        }

    Response:
        {
            "reply": "Oi Vinicius!",
            "delay_ms": 4200,
            "presence": "composing",
            "metadata": {...}
        }
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid_json: {e}")

    extra = body.get("extra", {})
    has_audio = bool(extra.get("has_audio"))
    has_document = bool(extra.get("has_document"))
    if not body.get("phone"):
        raise HTTPException(status_code=422, detail="phone required")
    if not body.get("text") and not has_audio and not has_document:
        raise HTTPException(status_code=422, detail="text, audio, or document required")

    if has_audio:
        from core.audio_pipeline import transcribe_envelope_audio

        body["extra"] = extra
        audio = await transcribe_envelope_audio(body)
        if "error" in audio:
            if not body.get("text"):
                audit_result = await index_audio_failure_for_audit(body, audio["error"])
                if audio["error"].startswith("unavailable:"):
                    reply = "Nao consegui transcrever esse audio agora. Pode tentar novamente ou enviar em texto?"
                    err_code = "audio_transcription_unavailable"
                else:
                    reply = "Nao consegui processar esse audio com seguranca. Pode reenviar ou mandar a mensagem em texto?"
                    err_code = "audio_transcription_failed"
                return JSONResponse(content={
                    "reply": reply,
                    "delay_ms": calculate_delay_ms(reply),
                    "presence": "paused",
                    "metadata": {
                        "agent_id": "audio-transcriber",
                        "response_identity": "Jennifer",
                        "error": err_code,
                        "reason": audio["error"],
                        "audit_indexed": audit_result.get("status") == "indexed",
                        "audit_status": audit_result.get("status", "error"),
                    },
                })
        else:
            body["text"] = audio["transcript"]
            extra["audio_provider"] = audio.get("provider", "groq:whisper-large-v3-turbo")
            extra["audio_provider_reason"] = audio.get("reason", "")
            extra["audio_transcribed"] = True
            extra["audio_source"] = audio.get("source", "url")
            body["extra"] = extra

    if has_document:
        # F4d: handler de attachment foi MOVIDO para orchestrator._handle_attachment
        # (chamado por orchestrate()). /chat apenas valida que o attachment
        # nao deveria vir por aqui (use o webhook /pubsub/push).
        return JSONResponse(content={
            "reply": (
                "Documentos devem ser enviados via WhatsApp (webhook), "
                "nao via /chat. Use o fluxo normal."
            ),
            "delay_ms": calculate_delay_ms(
                "Documentos devem ser enviados via WhatsApp (webhook), "
                "nao via /chat. Use o fluxo normal."
            ),
            "presence": "paused",
            "metadata": {
                "agent_id": "document-handler-info",
                "response_identity": "Jennifer",
                "info": "attachment_via_webhook_only",
            },
        }, status_code=400)

    chat_started = time.monotonic()
    result = await orchestrate(body)
    has_error = bool((result.get("metadata") or {}).get("error"))
    metrics.record_chat(chat_started, success=not has_error)

    return JSONResponse(content=result)


@app.post("/webhook")
async def evolution_webhook(request: Request):
    """Receive WhatsApp message from Evolution webhook.

    Single source of truth for inbound WhatsApp messages. Validates the
    payload shape, extracts a normalized envelope, publishes to Pub/Sub
    and returns 200 OK immediately so Evolution does not time out.

    Filters applied (see core.evolution_webhook.extract_envelope):
    - non-message events (CONNECTION_UPDATE, etc)
    - fromMe echoes
    - broadcast lists
    - empty phone/instance
    - unsupported message types (image/video/document without text)
    """
    from core.evolution_webhook import extract_envelope
    from core.pubsub_publisher import get_publisher
    from core.message_ledger import register_or_load, resolve_message_id

    webhook_started = time.monotonic()
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(
            "webhook_invalid_json",
            extra={"event_name": "webhook_invalid_json", "error_type": type(e).__name__},
        )
        raise HTTPException(status_code=400, detail="invalid_json")
    if not isinstance(body, dict):
        logger.warning(
            "webhook_invalid_payload",
            extra={"event_name": "webhook_invalid_payload", "payload_type": type(body).__name__},
        )
        raise HTTPException(status_code=422, detail="payload must be an object")

    envelope = extract_envelope(body)
    if envelope is None:
        event = body.get("event") or body.get("type") or ""
        logger.info(
            "webhook_ignored",
            extra={
                "event_name": "webhook_ignored",
                "evolution_event": event,
                "latency_ms": round((time.monotonic() - webhook_started) * 1000, 2),
            },
        )
        if event and event not in {"MESSAGES_UPSERT", "messages.upsert"}:
            return JSONResponse(content={"status": "ignored", "event": event})
        data = body.get("data") or {}
        logger.info(
            "webhook_ignored_body_preview event=%s body_keys=%s data_keys=%s data_preview=%s",
            event,
            list(body.keys()) if isinstance(body, dict) else "NOT_DICT",
            list(data.keys()) if isinstance(data, dict) else "NOT_DICT",
            str(data)[:1200],
        )
        return JSONResponse(content={"status": "ignored", "reason": "filtered"})

    resolve_message_id(envelope)
    message_id = envelope["message_id"]
    phone = envelope.get("phone", "")

    from core.flood_protection import is_user_quarantined
    if phone and is_user_quarantined(phone):
        logger.info("webhook_ignored_quarantined phone=%s message_id=%s", phone, message_id)
        return JSONResponse(content={"status": "ignored", "reason": "quarantined"})

    ledger_snapshot = register_or_load(message_id, {"payload": envelope, **envelope})
    if ledger_snapshot and ledger_snapshot.get("state") in {"response_ready", "delivered", "failed_terminal"}:
        _schedule_mark_read(envelope)
        logger.info(
            "webhook_already_processed",
            extra={
                "event_name": "webhook_already_processed",
                "message_id": message_id,
                "ledger_state": ledger_snapshot.get("state"),
            },
        )
        return JSONResponse(content={"status": "duplicate", "message_id": message_id})

    _schedule_mark_read(envelope)
    publisher = get_publisher()
    try:
        message_id_published = publisher.publish(
            envelope,
            topic="chatbotwhatsapp-messages",
            attributes={
                "source": "evolution-webhook",
                "instance": envelope["instance"],
            },
        )
    except Exception as exc:
        logger.error(
            "webhook_publish_failed",
            extra={
                "event_name": "webhook_publish_failed",
                "request_id": envelope["request_id"],
                "error_type": type(exc).__name__,
                "latency_ms": round((time.monotonic() - webhook_started) * 1000, 2),
            },
        )
        raise HTTPException(status_code=503, detail="publish_failed")

    _schedule_mark_read(envelope)

    logger.info(
        "webhook_queued",
        extra={
            "event_name": "webhook_queued",
            "request_id": envelope["request_id"],
            "pubsub_message_id": message_id_published,
            "instance": envelope["instance"],
            "latency_ms": round((time.monotonic() - webhook_started) * 1000, 2),
        },
    )
    return JSONResponse(
        content={
            "queued": True,
            "message_id": message_id_published,
            "request_id": envelope["request_id"],
        }
    )


async def _safe_mark_read(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort Evolution read-receipt without blocking the webhook.

    Retorna um dicionário com ``status`` para que o callback assíncrono
    consiga diferenciar ``ok``, ``timeout`` e ``failed``. O webhook continua
    retornando imediatamente; nenhuma exceção vaza para o caller.

    Cold start mitigation: the first HTTP call to Evolution after a
    Cloud Run cold start pays DNS + TLS + fetchInstances cost (8-10s).
    The warm timeout (5s) kills the request before it completes, so
    the user never sees the read receipt. We detect cold start via
    ``_INSTANCE_CACHE`` emptiness and use a longer timeout.
    """
    message_id = envelope.get("message_id", "")
    remote_jid = envelope.get("remote_jid", "")
    instance = envelope.get("instance", "")
    if not remote_jid or not message_id:
        return {"status": "skipped", "reason": "missing_remote_jid_or_id"}
    try:
        from core.evolution_client import mark_messages_read, _is_evolution_warm

        timeout_sec = (
            MARK_READ_TIMEOUT_WARM_SEC
            if _is_evolution_warm()
            else MARK_READ_TIMEOUT_COLD_SEC
        )
        message_ids = [message_id]
        await asyncio.wait_for(
            mark_messages_read(instance, remote_jid, message_ids, from_me=False),
            timeout=timeout_sec,
        )
        return {
            "status": "ok",
            "message_id": message_id,
            "remote_jid": remote_jid,
            "instance": instance,
            "timeout_sec": timeout_sec,
        }
    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "message_id": message_id,
            "remote_jid": remote_jid,
            "instance": instance,
            "error_type": "TimeoutError",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "message_id": message_id,
            "remote_jid": remote_jid,
            "instance": instance,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _log_mark_read_result(task: "asyncio.Task[Dict[str, Any]]") -> None:
    """Callback assíncrono: emite log estruturado de cada tentativa.

    Estados possíveis:
      - ``ok``      → ``evolution_mark_read_ok``
      - ``timeout`` → ``evolution_mark_read_timeout``
      - ``failed``  → ``evolution_mark_read_failed``
      - ``skipped`` → ``evolution_mark_read_skipped``
    """
    if task.cancelled():
        logger.warning(
            "evolution_mark_read_failed",
            extra={"event_name": "evolution_mark_read_failed", "reason": "cancelled"},
        )
        return
    exc = task.exception()
    if exc is not None:
        logger.warning(
            "evolution_mark_read_failed",
            extra={
                "event_name": "evolution_mark_read_failed",
                "reason": "exception",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return
    result = task.result() or {}
    status = result.get("status", "failed")
    event_name = {
        "ok": "evolution_mark_read_ok",
        "timeout": "evolution_mark_read_timeout",
        "failed": "evolution_mark_read_failed",
        "skipped": "evolution_mark_read_skipped",
    }.get(status, "evolution_mark_read_failed")
    extras = {"event_name": event_name, **result}
    if status == "ok":
        logger.info(event_name, extra=extras)
    else:
        logger.warning(event_name, extra=extras)


def _schedule_mark_read(envelope: Dict[str, Any]) -> "asyncio.Task[Dict[str, Any]]":
    """Dispara o ack de leitura como tarefa paralela sem bloquear o webhook."""
    task = asyncio.create_task(_safe_mark_read(envelope))
    task.add_done_callback(_log_mark_read_result)
    return task


@app.post("/pubsub/push")
async def pubsub_push(request: Request):
    """Pub/Sub push endpoint (chatbotwhatsapp-messages).

    Validates the Google-signed OIDC token, claims a ledger lease, and
    processes the payload via ``orchestrator.orchestrate``. The ledger keeps
    Pub/Sub idempotent across instances and retries; no manual DLQ publish is
    performed (Pub/Sub's native DLQ policy handles exhaustion).
    """
    from core.pubsub_consumer import (
        parse_pubsub_push_body,
        verify_pubsub_token,
    )
    from core.pubsub_dispatcher import (
        TransientProcessingError,
        dispatch_with_ledger,
        record_delivery,
    )

    auth_header = request.headers.get("Authorization", "")
    if not verify_pubsub_token(auth_header):
        raise HTTPException(status_code=401, detail="invalid_pubsub_token")
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid_json: {e}")

    envelope = parse_pubsub_push_body(body)
    if envelope["data"]:
        try:
            payload = json.loads(envelope["data"])
        except json.JSONDecodeError:
            payload = {"raw": envelope["data"]}
    else:
        payload = envelope

    request_id = envelope["message_id"]
    message_id = (payload.get("message_id") if isinstance(payload, dict) else None) or request_id
    rate_limited_phone = (
        payload.get("phone", "")
        if isinstance(payload, dict)
        else ""
    )
    if rate_limited_phone:
        try:
            from core.rate_limit import is_rate_limited
            limited, _remaining = is_rate_limited(rate_limited_phone)
            if limited:
                logger.warning(
                    "rate_limited phone=%s request_id=%s",
                    rate_limited_phone, request_id,
                )
                return {
                    "status": "rate_limited",
                    "request_id": request_id,
                    "message_id": message_id,
                }
        except Exception as exc:
            logger.warning("rate_limit_check_failed: %s", exc)

    async def _process(p: Dict[str, Any]) -> Dict[str, Any]:
        from core.evolution_client import send_text
        from core.audio_pipeline import transcribe_envelope_audio
        from core.flood_protection import is_user_quarantined

        phone = p.get("phone", "")
        if phone and is_user_quarantined(phone):
            logger.info("pubsub_process_ignored_quarantined phone=%s", phone)
            return {"reply": "", "delay_ms": 0, "presence": "paused", "metadata": {"quarantined": True}}

        result = None
        if (p.get("extra") or {}).get("has_audio"):
            audio = await transcribe_envelope_audio(p)
            if "error" in audio:
                if (p.get("extra") or {}).get("is_group") and not (p.get("extra") or {}).get("was_mentioned_native"):
                    return {"reply": "", "delay_ms": 0, "presence": "paused"}
                await index_audio_failure_for_audit(p, audio["error"])
                reply = "Nao consegui transcrever esse audio agora. Pode tentar novamente ou enviar em texto?"
                result = {
                    "reply": reply,
                    "delay_ms": calculate_delay_ms(reply),
                    "presence": "paused",
                    "metadata": {
                        "agent_id": "audio-transcriber",
                        "response_identity": "Jennifer",
                        "error": "audio_transcription_unavailable",
                        "reason": audio["error"],
                    },
                }
            else:
                transcript = audio["transcript"]
                p["text"] = transcript
                extra_updates = p.setdefault("extra", {})
                extra_updates["audio_transcribed"] = True
                extra_updates["audio_provider"] = audio["provider"]

                # Em GRUPO: se o audio nao veio com mencao nativa do WhatsApp,
                # verificar se a pessoa FALOU "Jennifer" ou "Jenni" no audio.
                if extra_updates.get("is_group") and not extra_updates.get("was_mentioned_native"):
                    low_text = transcript.lower()
                    if "jennifer" not in low_text and "jenni" not in low_text:
                        logger.info("webhook_group_audio_skipped_no_spoken_mention phone=%s transcript=%s", p.get("phone"), transcript[:50])
                        return {"reply": "", "delay_ms": 0, "presence": "paused"}

        if result is None:
            result = await orchestrate(p)

        reply = result.get("reply", "")
        phone = p.get("phone", "") or (p.get("extra") or {}).get("phone", "")
        delivered = bool(result.get("delivered_as_image"))
        delivery_error = ""
        if reply and phone and not result.get("delivered_as_image"):
            try:
                await send_text(
                    instance=p.get("instance", "Jennifer"),
                    phone=phone,
                    text=reply,
                    delay_ms=result.get("delay_ms", 0),
                    presence=result.get("presence", "composing"),
                    remote_jid=p.get("remote_jid", "") or (p.get("extra") or {}).get("remote_jid", ""),
                )
                delivered = True
            except Exception as send_exc:
                delivery_error = f"{type(send_exc).__name__}:{send_exc}"
                logger.error(
                    "pubsub send_text_skipped reason=%s phone_present=%s instance=%s reply_len=%d",
                    type(send_exc).__name__, bool(phone), p.get("instance", "?"), len(reply),
                )
        elif reply and not phone:
            logger.error(
                "pubsub reply_dropped_empty_phone request_id=%s reply_len=%d instance=%s",
                request_id, len(reply), p.get("instance", "?"),
            )

        if message_id:
            record_delivery(
                message_id,
                success=delivered,
                error=delivery_error,
            )

        return {
            "status": "ok",
            "request_id": request_id,
            "message_id": message_id,
            "delivered": delivered,
            "delivery_error": delivery_error,
            "result": result,
        }

    try:
        result = await dispatch_with_ledger(
            {"data": json.dumps(payload, default=str), **payload},
            _process,
        )
    except TransientProcessingError:
        return JSONResponse(
            status_code=503,
            content={"status": "transient_error", "request_id": request_id},
        )
    if isinstance(result, dict) and result.get("status") == "failed_terminal":
        return JSONResponse(status_code=200, content=result)
    if isinstance(result, dict) and result.get("status") in {"duplicate", "lease_busy", "dropped"}:
        return JSONResponse(status_code=200, content=result)
    return JSONResponse(content=result or {"status": "ok"})


@app.post("/proactive/send")
async def proactive_send(request: Request):
    """Send a proactive message (called by proactive_worker)."""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid_json: {e}")

    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=422, detail="message required")

    from core.proactive_gate import is_prohibited_template
    if is_prohibited_template(message):
        logger.warning(f"Prohibited template detected: {message[:80]}")
        return JSONResponse(
            content={
                "sent": False,
                "reason": "prohibited_template",
            }
        )

    delay_ms = calculate_delay_ms(message)

    return JSONResponse(
        content={
            "sent": True,
            "message_id": "mock-" + os.urandom(4).hex(),
            "delay_ms_applied": delay_ms,
            "note": "Proactive worker integration - Fase 6.5",
        }
    )


@app.post("/admin/agents")
async def admin_agents_post(request: Request):
    """Create or update an agent (Portal proxy)."""
    body = await request.json()
    agent_id = body.get("id")
    if not agent_id:
        raise HTTPException(status_code=422, detail="id required")

    success = upsert_agent(agent_id, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "agent_id": agent_id,
        "upserted": success,
    })


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=43200,  # 12h
    )


def _authorise_admin(request: Request) -> bool:
    from core.auth import _is_valid_firebase_jwt, get_sa_token

    expected = get_sa_token()
    token = _bearer_token(request)
    if expected and token and hmac.compare_digest(token, expected):
        return True
    if token and _is_valid_firebase_jwt(token):
        return True
    return False


def _caller_role(request: Request) -> tuple:
    """Retorna (role, phone) do caller. SA token = admin."""
    from core.auth import resolve_caller

    return resolve_caller(request)


def _caller_profile(request: Request) -> dict:
    """Retorna profile completo do caller (role, phone, email, name, picture, is_admin)."""
    try:
        from core.auth import resolve_caller_profile

        return resolve_caller_profile(request)
    except Exception:
        role, phone = _caller_role(request)
        return {
            "role": role or "agent_user",
            "phone": phone or "",
            "email": "",
            "name": "Administrador" if role == "admin" else "Usuário",
            "picture": "",
            "is_admin": role == "admin",
        }


def _require_admin(request: Request) -> None:
    """Raise 403 se o caller nao for admin."""
    role, _ = _caller_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")


def _require_self_or_admin(request: Request, phone: str) -> None:
    """Raise 403 se agent_user tentar acessar recurso de outro phone."""
    role, caller_phone = _caller_role(request)
    if role == "admin":
        return
    if role == "":
        raise HTTPException(status_code=403, detail="auth_required")
    target = "".join(c for c in str(phone or "") if c.isdigit())
    if not caller_phone or target != caller_phone:
        raise HTTPException(status_code=403, detail="forbidden_resource")


@app.get("/")
@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Render the Agentes Omnichannel control plane.

    O acesso ao modulo e SEMPRE via Portal Coherence. Se nao ha token
    valido, redireciona para o portal (que emite o JWT). Com token,
    redireciona para o portal React ou usa o module_ui.py legado.
    """
    from core.auth import resolve_caller

    token = _bearer_token(request)
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        return RedirectResponse(url=COHERENCE_PORTAL_URL)

    if _portal_available():
        portal_url = "/portal/?token=" + token
        return RedirectResponse(url=portal_url)

    from core.module_ui import render_dashboard

    role, caller_phone = resolve_caller(request)
    response = HTMLResponse(content=render_dashboard(COMMIT_SHA, DEPLOYED_AT, role=role or "admin", caller_phone=caller_phone))
    # Anti-cache headers para Portal sempre servir versao nova
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    if token:
        _set_session_cookie(response, token)
    return response


@app.get("/admin/evolution/health")
async def admin_evolution_health():
    """Health-check da integracao Evolution admin: lista instancias + estado."""
    from core.evolution_admin import fetch_instances

    instances = await fetch_instances()
    summary = []
    for inst in instances:
        name = inst.get("name", "?")
        state = inst.get("connectionStatus") or inst.get("state") or "unknown"
        summary.append({"instance": name, "state": state})
    return JSONResponse(content={
        "connected": True,
        "instances": summary,
        "total": len(summary),
    })


@app.get("/admin/ping")
async def admin_ping():
    """Health-check rapido para o Portal e Cloud Scheduler warm-up.

    NAO toca Firestore, NAO chama LLM, NAO faz criptografia. Resposta
    em <50ms tipicamente. Use para:
    1. Portal detectar se runtime esta online (badge "runtime OK")
    2. Cloud Scheduler cron (a cada 5min) manter container warm
    """
    return JSONResponse(content={
        "pong": True,
        "commit": COMMIT_SHA,
        "deployed_at": DEPLOYED_AT,
        "version": VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


@app.post("/admin/cache/invalidate")
async def admin_cache_invalidate(request: Request):
    """Invalida caches in-process (agent_loader + folder_permissions)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    phone = body.get("phone") if isinstance(body, dict) else None
    if phone:
        from core.folder_permissions import force_reload_cache
        force_reload_cache(phone)
        return JSONResponse(content={"status": "ok", "scope": "phone", "phone": phone})
    from agent_loader import force_reload
    from core.folder_permissions import force_reload_cache as fp_reload
    try:
        force_reload()
    except Exception:
        pass
    fp_reload(None)
    return JSONResponse(content={"status": "ok", "scope": "all"})


@app.get("/admin/status")
async def admin_status(request: Request):
    from core.audio_transcribe import fallback_stats
    from core.agent_status import build_agent_inventory

    role, _ = _caller_role(request)
    api_key_set = False
    try:
        from core.llm_provider import LLMProvider

        api_key_set = bool(LLMProvider().is_available())
    except Exception:
        api_key_set = False
    inventory = build_agent_inventory()
    counts = inventory.get("counts", {})
    health_state = "ok"
    if counts.get("healthy", 0) == 0 and counts.get("routable", 0) == 0:
        health_state = "warn"
    if counts.get("healthy", 0) == 0 and counts.get("routable", 0) > 0:
        health_state = "warn"
    kpis = [
        {"label": "commit", "value": _short_sha(COMMIT_SHA)},
        {"label": "deployed_at", "value": DEPLOYED_AT},
        {"label": "llm_provider", "value": "deepseek-v4-flash", "sub": "sem cascade (Fase N 25/07/2026)"},
        {"label": "llm_api_key", "value": "configurada" if api_key_set else "ausente"},
        {"label": "agents_total", "value": counts.get("configured", 0), "sub": f"{counts.get('routable', 0)} roteaveis"},
        {"label": "agents_healthy", "value": counts.get("healthy", 0), "sub": f"{counts.get('degraded', 0)} degradados"},
        {"label": "in_flight", "value": counts.get("in_flight", 0), "sub": "execucoes em andamento"},
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_ok": health_state == "ok" and api_key_set,
        "health_state": health_state,
        "kpis": kpis,
        "llm": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "cascade": False,
            "api_key_set": api_key_set,
            "base_url_env": "DEEPSEEK_BASE_URL",
            "note": "Fase N (25/07/2026) removeu o cascade MiniMax/Gemini para LLM. Apenas DeepSeek V4 Flash atende chat/completions+tool_calls.",
        },
        "stt": fallback_stats(),
    }
    if role == "admin":
        payload["agents_summary"] = {
            "counts": counts,
            "generated_at": inventory.get("generated_at"),
        }
        try:
            payload["users_summary"] = _build_users_status()
        except Exception:
            payload["users_summary"] = {"users": [], "total": 0}
    else:
        try:
            payload["my_connections"] = _build_user_connections(request)
        except Exception:
            payload["my_connections"] = {"google": False, "composio": {}}
    return JSONResponse(content=payload)


def _build_users_status() -> Dict[str, Any]:
    """Resumo de usuarios + status de conexoes (admin, tabela de monitoramento).

    Varre usuarios/* e cruza com folder_permissions e composio (best-effort).
    """
    from agent_loader import list_users

    users = list_users()
    rows = []
    for u in users:
        phone = u.get("phone_canonical") or u.get("phone") or ""
        google_token = u.get("google_oauth_token") or {}
        rows.append({
            "phone": phone,
            "email": u.get("email", ""),
            "role": u.get("role", "agent_user"),
            "has_google": bool(google_token and google_token.get("token")),
            "google_linked_at": u.get("google_oauth_linked_at", ""),
            "has_composio": bool(u.get("composio_linked_at")),
            "created_at": u.get("created_at", "") or u.get("updated_at", ""),
        })
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {
        "users": rows,
        "total": len(rows),
        "with_google": sum(1 for r in rows if r["has_google"]),
    }


def _build_user_connections(request: Request) -> Dict[str, Any]:
    """Status das conexoes do proprio agente_user (cards no Portal)."""
    role, phone = _caller_role(request)
    if not phone:
        return {"google": False, "composio": {}, "phone": ""}
    from agent_loader import get_user

    user = get_user(phone) or {}
    google_token = user.get("google_oauth_token") or {}
    has_google = bool(google_token and google_token.get("token"))
    composio_apps: Dict[str, Any] = {}
    try:
        from tools.composio_connect import get_status as composio_status

        result = asyncio.run(composio_status(phone))
        if result.get("apps"):
            composio_apps = result["apps"]
    except Exception:
        pass
    return {
        "phone": phone,
        "email": user.get("email", ""),
        "google": has_google,
        "google_linked_at": user.get("google_oauth_linked_at", ""),
        "composio": {slug: bool(app.get("connected")) for slug, app in composio_apps.items()},
    }


@app.get("/admin/accounts")
async def admin_accounts_list(request: Request):
    from agent_loader import _get_firestore_client

    role, caller_phone = _caller_role(request)
    caller_digits = "".join(c for c in str(caller_phone or "") if c.isdigit())

    db = _get_firestore_client()
    if db is None:
        return JSONResponse(content={"accounts": []})
    try:
        rows = []
        for doc in db.collection("whatsapp_accounts").stream():
            data = doc.to_dict() or {}
            data["id"] = doc.id
            if role != "admin":
                owner = "".join(c for c in str(data.get("owner_phone", "") or "") if c.isdigit())
                if not caller_digits or owner != caller_digits:
                    continue
            rows.append(data)
        await _enrich_accounts_with_evolution_state(rows)
        return JSONResponse(content={"accounts": rows})
    except Exception as exc:
        logger.warning("admin_accounts_list failed: %s", exc)
        return JSONResponse(content={"accounts": []})


async def _enrich_accounts_with_evolution_state(rows: list) -> None:
    """Preenche connection_status ao vivo consultando a Evolution API.

    O campo `status` gravado em whatsapp_accounts e administrativo
    ("active"); o estado real de conexao vem da Evolution
    (open/connecting/close). Isso resolve o "unknown" na aba Contas.
    """
    from core.evolution_admin import get_connection_state

    for row in rows:
        instance = str(row.get("instance") or "").strip()
        if not instance:
            continue
        state = await get_connection_state(instance)
        conn = (state or {}).get("state") or ""
        if conn:
            row["connection_status"] = conn
            row["state"] = conn


@app.get("/admin/accounts/{account_id}")
async def admin_accounts_get(account_id: str):
    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="firestore_unavailable")
    doc = db.collection("whatsapp_accounts").document(account_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="account_not_found")
    payload = doc.to_dict() or {}
    payload["id"] = doc.id
    return JSONResponse(content={"account": payload})


async def _write_account(account_id: str, body: Dict[str, Any]) -> bool:
    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    if db is None:
        return False
    phone = re.sub(r"\D", "", str(body.get("owner_phone", "")))
    payload = {
        "name": str(body.get("name", "")).strip() or account_id,
        "instance": str(body.get("instance", "")).strip(),
        "owner_phone": phone,
        "owner_uid": str(body.get("owner_uid", "")).strip() or phone,
        "status": str(body.get("status", "active")),
        "updated_at": now_brt().isoformat(),
    }
    db.collection("whatsapp_accounts").document(account_id).set(payload, merge=True)
    return True


@app.post("/admin/accounts")
async def admin_accounts_create(request: Request):
    body = await request.json()
    instance = str(body.get("instance", "")).strip()
    if not instance:
        raise HTTPException(status_code=422, detail="instance required")
    account_id = instance
    ok = await _write_account(account_id, body)
    return JSONResponse(content={"status": "ok" if ok else "error", "account_id": account_id, "upserted": ok})


@app.put("/admin/accounts/{account_id}")
async def admin_accounts_update(account_id: str, request: Request):
    body = await request.json()
    ok = await _write_account(account_id, body)
    return JSONResponse(content={"status": "ok" if ok else "error", "account_id": account_id, "upserted": ok})


@app.delete("/admin/accounts/{account_id}")
async def admin_accounts_delete(account_id: str):
    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="firestore_unavailable")
    doc = db.collection("whatsapp_accounts").document(account_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="account_not_found")
    db.collection("whatsapp_accounts").document(account_id).delete()
    return JSONResponse(content={"status": "ok", "account_id": account_id, "deleted": True})


@app.post("/admin/instances")
async def admin_instances_create(request: Request):
    """Cria uma nova instancia Evolution + registra conta no Firestore.

    Body: {"name": "Maycon", "owner_phone": "5511999999999", "webhook_url": "..."}
    1. Cria instancia na Evolution API (create_instance + get_qr_code)
    2. Registra whatsapp_accounts/{id}
    3. Nao faz seed automatico aqui — o portal chama /seed apos QR lido.
    """
    from core.evolution_admin import create_instance, get_qr_code

    body = await request.json()
    instance_name = str(body.get("name", "") or "").strip()
    owner_phone = re.sub(r"\D", "", str(body.get("owner_phone", "") or ""))
    if not instance_name or not owner_phone:
        raise HTTPException(status_code=422, detail="name e owner_phone obrigatorios")
    base_url = os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br").rstrip("/")
    instance_base = base_url.replace("https://", "").replace("http://", "").replace(".", "-").replace("/", "")
    webhook_url = (body.get("webhook_url") or "").strip() or f"https://{instance_base}/webhook"

    created = await create_instance(instance_name, webhook_url=webhook_url)
    if created.get("error"):
        raise HTTPException(status_code=502, detail=created["error"])

    account_id = f"{instance_name.lower()}"
    await _write_account(account_id, {
        "name": instance_name,
        "instance": instance_name,
        "owner_phone": owner_phone,
        "owner_uid": owner_phone,
        "status": "created",
    })

    qr = await get_qr_code(instance_name)
    return JSONResponse(content={
        "status": "created",
        "account_id": account_id,
        "instance": instance_name,
        "qr_base64": qr.get("qr_base64", ""),
        "qr_code": qr.get("code", ""),
        "connected": False,
    })


@app.post("/admin/instances/{instance_id}/seed")
async def admin_instances_seed(instance_id: str):
    """Duplica a config da Jennifer (agentes/skills/tools) para a nova instancia.

    Copia todos os agentes da Jennifer com instances=['{instance}'].
    Skills e tools sao compartilhadas (mesma collection). O agente principal
    assume o nome da instancia.
    """
    from agent_loader import _get_firestore_client, list_agents

    db = _get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="firestore_unavailable")
    instance = instance_id.strip()
    if not instance:
        raise HTTPException(status_code=422, detail="instance_id required")

    source_agents = list_agents()
    jennifier_agents = [a for a in source_agents if "jennifer" in [str(i).lower() for i in a.get("instances", [])]]
    if not jennifier_agents:
        jennifier_agents = source_agents

    copied = 0
    for agent in jennifier_agents:
        agent_id = agent.get("agent_id") or agent.get("id") or ""
        if not agent_id:
            continue
        # agent_id unico por instancia: {instance}__{agent_id}
        new_agent_id = f"{instance.lower()}__{agent_id}"
        new_agent = dict(agent)
        new_agent["agent_id"] = new_agent_id
        new_agent["instances"] = [instance, instance.title()]
        if new_agent.get("role") in ("orchestrator", "manager"):
            new_agent["name"] = instance.title()
        new_agent["updated_at"] = now_brt().isoformat()
        db.collection("agents").document(new_agent_id).set(new_agent, merge=True)
        copied += 1

    account_ref = db.collection("whatsapp_accounts").document(instance)
    if account_ref.get().exists:
        account_ref.update({"status": "seeded", "seeded_at": now_brt().isoformat()})

    return JSONResponse(content={"status": "ok", "instance": instance, "agents_copied": copied})


@app.get("/admin/owners")
async def admin_owners_list():
    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    if db is None:
        return JSONResponse(content={"owners": []})
    rows: list = []
    try:
        for doc in db.collection("whatsapp_accounts").stream():
            data = doc.to_dict() or {}
            rows.append({
                "owner_uid": data.get("owner_uid") or data.get("owner_phone"),
                "owner_phone": data.get("owner_phone"),
                "display_name": data.get("name"),
                "instance": data.get("instance"),
            })
    except Exception as exc:
        logger.warning("admin_owners_list failed: %s", exc)
    return JSONResponse(content={"owners": rows})


@app.get("/admin/integrations")
async def admin_integrations_list(request: Request):
    """Lista as integracoes disponiveis (Google, Composio, Evolution, etc)."""
    from tools.composio_connect import get_status

    integrations: list = []
    google = {
        "id": "google-oauth",
        "name": "Google OAuth 2.0 (Per-User)",
        "category": "OAuth Core",
        "status": "Conectado",
        "details": {
            "active_scopes": len(OAUTH_SCOPES),
            "redirect_uri": _oauth_redirect_uri(request),
        },
    }
    integrations.append(google)

    try:
        user = get_user("5511966830020") or {}
        status = await get_status(str(user.get("phone") or "5511966830020"))
        apps = (status or {}).get("apps") or {}
        connected = sum(1 for a in apps.values() if (a or {}).get("connected"))
        integrations.append({
            "id": "composio",
            "name": "Composio MCP SDK",
            "category": "Multi-App Automation",
            "status": "Ativo",
            "details": {"apps_connected": connected, "apps_total": len(apps)},
        })
    except Exception as exc:  # noqa: BLE001
        integrations.append({
            "id": "composio",
            "name": "Composio MCP SDK",
            "category": "Multi-App Automation",
            "status": "Ativo",
            "details": {"apps_connected": 0, "apps_total": 0, "error": str(exc)[:100]},
        })

    integrations.append({
        "id": "evolution",
        "name": "Evolution API v2.3.7",
        "category": "Messaging Gateway",
        "status": "Conectado",
        "details": {"endpoint": os.getenv("EVO_BASE_URL", "https://evolution.coherenceai.com.br")},
    })
    integrations.append({
        "id": "firestore",
        "name": "Firestore (Dados + RAG Vector)",
        "category": "Storage",
        "status": "Operacional",
        "details": {"project": os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")},
    })
    return JSONResponse(content={"integrations": integrations})


@app.get("/admin/knowledge")
async def admin_knowledge_documents(request: Request):
    import hashlib
    from agent_loader import _get_firestore_client
    from core.rag import KNOWLEDGE_DATABASE

    limit = min(int(request.query_params.get("limit", "50")), 200)
    role, caller_phone = _caller_role(request)
    caller_digits = "".join(c for c in str(caller_phone or "") if c.isdigit())
    caller_hash = hashlib.sha256(caller_digits.encode("utf-8")).hexdigest()[:32] if caller_digits else ""

    db = _get_firestore_client()
    documents: list = []
    grouped: Dict[str, Dict[str, Any]] = {}
    owner_map = _build_owner_hash_map()
    if db is not None:
        plain_pairs = [
            (KNOWLEDGE_DATABASE, KNOWLEDGE_DATABASE),
        ]
        for plain_collection, vector_collection in plain_pairs:
            try:
                stream = db.collection(plain_collection).limit(limit * 4).stream()
            except Exception as exc:
                logger.warning("admin_knowledge_documents failed for %s: %s", plain_collection, exc)
                continue
            try:
                for doc in stream:
                    data = doc.to_dict() or {}
                    owner_hash = data.get("owner_hash") or ""
                    owner_phone = owner_map.get(owner_hash, "")

                    # Se for analista (não admin), isolamento estrito: só vê seus próprios documentos
                    if role != "admin":
                        if not caller_digits:
                            continue
                        if owner_hash != caller_hash and owner_phone != caller_digits:
                            continue

                    source_title = data.get("source_title") or data.get("titulo") or doc.id
                    klass = data.get("class") or data.get("category") or ""
                    grp = data.get("group") or ""
                    theme = data.get("theme") or ""
                    key = f"{plain_collection}::{source_title}"
                    bucket = grouped.setdefault(key, {
                        "doc_id": source_title,
                        "title": source_title,
                        "text": (data.get("text_content") or data.get("conteudo") or "")[:500],
                        "owner_id": owner_hash[:12] if owner_hash else None,
                        "owner_phone": owner_phone,
                        "collection": plain_collection,
                        "vector_collection": vector_collection,
                        "chunk_count": 0,
                        "chunk_indices": [],
                        "klass": klass,
                        "group": grp,
                        "theme": theme,
                        "language": data.get("language", "pt-BR"),
                        "created_at": data.get("created_at", ""),
                        "source_url": data.get("source_url", ""),
                    })
                    bucket["chunk_count"] += 1
                    idx = data.get("chunk_index")
                    if isinstance(idx, int):
                        bucket["chunk_indices"].append(idx)
            except Exception as exc:
                logger.warning("admin_knowledge_documents stream failed for %s: %s", plain_collection, exc)
        documents = list(grouped.values())
        documents.sort(key=lambda d: (d.get("created_at") or "", d.get("title") or ""))
        documents = documents[:limit]
        for doc in documents:
            doc["chunk_indices"].sort()
    return JSONResponse(content={"documents": documents, "limit": limit, "total_groups": len(grouped)})


@app.get("/admin/knowledge/{source_title:path}")
async def admin_knowledge_document_detail(source_title: str, request: Request):
    """Return all chunks for a single document, identified by source_title."""
    from agent_loader import _get_firestore_client
    from core.rag import KNOWLEDGE_DATABASE

    collection = request.query_params.get("collection") or KNOWLEDGE_DATABASE
    db = _get_firestore_client()
    chunks: list = []
    metadata = {
        "source_title": source_title,
        "klass": "",
        "group": "",
        "theme": "",
        "language": "pt-BR",
        "owner_id": "",
        "created_at": "",
        "source_url": "",
        "chunk_count": 0,
        "vector_collection": KNOWLEDGE_DATABASE,
    }
    if db is not None:
        try:
            plain_refs = (KNOWLEDGE_DATABASE,)
            found_any = False
            for plain_coll in plain_refs:
                query = db.collection(plain_coll).where("source_title", "==", source_title)
                for doc in query.stream():
                    data = doc.to_dict() or {}
                    found_any = True
                    if not metadata["klass"]:
                        metadata["klass"] = data.get("class") or data.get("category") or ""
                    if not metadata["group"]:
                        metadata["group"] = data.get("group") or ""
                    if not metadata["theme"]:
                        metadata["theme"] = data.get("theme") or ""
                    metadata["owner_id"] = metadata["owner_id"] or (data.get("owner_hash") or "")[:12]
                    metadata["created_at"] = metadata["created_at"] or data.get("created_at", "")
                    metadata["source_url"] = metadata["source_url"] or data.get("source_url", "")
                    metadata["language"] = data.get("language", metadata["language"])
                    metadata["vector_collection"] = plain_coll.replace("-plain", "") if plain_coll.endswith("-plain") else plain_coll
                    chunks.append({
                        "chunk_index": data.get("chunk_index", len(chunks)),
                        "text": data.get("text_content", "") or "",
                        "chars": len(data.get("text_content", "") or ""),
                        "chunk_id": doc.id,
                    })
            chunks.sort(key=lambda c: c.get("chunk_index", 0))
            metadata["chunk_count"] = len(chunks)
            if found_any:
                metadata["title"] = source_title
                metadata["collection"] = collection
            else:
                raise HTTPException(status_code=404, detail="document_not_found")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("admin_knowledge_document_detail failed for %s: %s", source_title, exc)
            raise HTTPException(status_code=500, detail="rag_lookup_failed") from exc
    else:
        raise HTTPException(status_code=503, detail="firestore_unavailable")
    return JSONResponse(content={"document": {**metadata, "chunks": chunks}})


@app.delete("/admin/knowledge/{source_title:path}")
async def admin_knowledge_document_delete(source_title: str, request: Request):
    """Delete all chunks of a document from the knowledge collections."""
    from agent_loader import _get_firestore_client
    from core.rag import KNOWLEDGE_DATABASE

    db = _get_firestore_client()
    if db is None:
        raise HTTPException(status_code=503, detail="firestore_unavailable")
    deleted = 0
    for coll in (KNOWLEDGE_DATABASE,):
        try:
            query = db.collection(coll).where("source_title", "==", source_title)
            for doc in query.stream():
                db.collection(coll).document(doc.id).delete()
                deleted += 1
        except Exception as exc:
            logger.warning("admin_knowledge_delete failed coll=%s source=%s: %s", coll, source_title, exc)
            raise HTTPException(status_code=500, detail="rag_delete_failed") from exc
    if deleted == 0:
        raise HTTPException(status_code=404, detail="document_not_found")
    return JSONResponse(content={"status": "ok", "source_title": source_title, "deleted": deleted})


@app.get("/admin/agents")
async def admin_agents_list():
    """List all agents (Portal proxy)."""
    return JSONResponse(content={"agents": list_agents()})


@app.get("/admin/agents/status")
async def admin_agents_status(request: Request):
    from core.agent_status import build_agent_inventory

    instance = request.query_params.get("instance", "jennifer")
    phone = request.query_params.get("phone")
    return JSONResponse(content=build_agent_inventory(instance=instance, phone=phone))


@app.get("/admin/agents/{agent_id}/status")
async def admin_agent_status(agent_id: str, request: Request):
    from core.agent_status import build_agent_inventory

    instance = request.query_params.get("instance", "jennifer")
    phone = request.query_params.get("phone")
    inventory = build_agent_inventory(instance=instance, phone=phone)
    agent = next((item for item in inventory["agents"] if item["agent_id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return JSONResponse(content={"generated_at": inventory["generated_at"], "agent": agent})


@app.get("/admin/agents/{agent_id}")
async def admin_agents_get(agent_id: str):
    """Get a specific agent."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return JSONResponse(content={"agent": agent})


@app.delete("/admin/agents/{agent_id}")
async def admin_agents_delete(agent_id: str):
    """Delete an agent (Portal proxy)."""
    success = delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=500, detail="delete_failed")
    return JSONResponse(content={"status": "ok", "agent_id": agent_id, "deleted": True})


@app.post("/admin/skills")
async def admin_skills_post(request: Request):
    """Create or update a skill (Portal proxy)."""
    body = await request.json()
    skill_id = body.get("id")
    if not skill_id:
        raise HTTPException(status_code=422, detail="id required")

    success = upsert_skill(skill_id, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "skill_id": skill_id,
        "upserted": success,
    })


@app.get("/admin/skills")
async def admin_skills_list():
    """List all skills (Portal proxy)."""
    return JSONResponse(content={"skills": list_skills()})


@app.get("/admin/skills/{skill_id}")
async def admin_skills_get(skill_id: str):
    """Get a specific skill (Portal proxy)."""
    skill = get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="skill_not_found")
    return JSONResponse(content={"skill": skill})


@app.delete("/admin/skills/{skill_id}")
async def admin_skills_delete(skill_id: str):
    """Delete a skill (Portal proxy)."""
    success = delete_skill(skill_id)
    if not success:
        raise HTTPException(status_code=500, detail="delete_failed")
    return JSONResponse(content={"status": "ok", "skill_id": skill_id, "deleted": True})


@app.post("/admin/tools")
async def admin_tools_post(request: Request):
    """Create or update a tool (Portal proxy)."""
    body = await request.json()
    tool_id = body.get("id")
    if not tool_id:
        raise HTTPException(status_code=422, detail="id required")

    success = upsert_tool(tool_id, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "tool_id": tool_id,
        "upserted": success,
    })


@app.get("/admin/tools")
async def admin_tools_list():
    """List all tools (Portal proxy)."""
    return JSONResponse(content={"tools": list_tools()})


@app.get("/admin/tools/{tool_id}")
async def admin_tools_get(tool_id: str):
    """Get a specific tool (Portal proxy)."""
    tool = get_tool_meta(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="tool_not_found")
    return JSONResponse(content={"tool": tool})


@app.delete("/admin/tools/{tool_id}")
async def admin_tools_delete(tool_id: str):
    """Delete a tool (Portal proxy)."""
    success = delete_tool(tool_id)
    if not success:
        raise HTTPException(status_code=500, detail="delete_failed")
    return JSONResponse(content={"status": "ok", "tool_id": tool_id, "deleted": True})


@app.post("/admin/register-user")
async def admin_register_user(request: Request):
    """Register or update a user with their OAuth token."""
    body = await request.json()
    phone = body.get("phone")
    if not phone:
        raise HTTPException(status_code=422, detail="phone required")
    role, _ = _caller_role(request)
    if role == "agent_user":
        _require_self_or_admin(request, phone)
    if "role" in body and body["role"] == "admin" and role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    success = save_user(phone, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "phone": phone,
        "registered": success,
    })


@app.get("/admin/me")
async def admin_me(request: Request):
    """Return identity and role of caller."""
    role, caller_phone = _caller_role(request)
    profile = _caller_profile(request)
    if role:
        profile["role"] = role
        profile["is_admin"] = role == "admin"
    if caller_phone:
        profile["phone"] = caller_phone
    return JSONResponse(content=profile)


@app.get("/admin/users")
async def admin_users_list(request: Request):
    """List registered users. Admin sees all; analyst sees only self."""
    role, caller_phone = _caller_role(request)
    if role == "admin":
        users = list_users()
    else:
        user = get_user(caller_phone) if caller_phone else None
        users = [user] if user else []
    for user in users:
        await _enrich_user_connections(user)
    return JSONResponse(content={"users": users})


# Mapa de servicos Google (D1: dinamico). Fonte unica: core.google_scopes.
# O portal renderiza exatamente o que esse modulo gera; o fragmento de escopo
# (svc["scope"]) e o que liga o servico ao token OAuth concedido.
from core.google_scopes import GOOGLE_SERVICES as _GOOGLE_SERVICE_MAP  # noqa: E402


def _build_owner_hash_map() -> Dict[str, str]:
    """Mapeia owner_hash (sha256 do phone) -> phone para exibir dono dos docs."""
    import hashlib

    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    mapping: Dict[str, str] = {}
    if db is None:
        return mapping
    try:
        for doc in db.collection("usuarios").stream():
            phone = str((doc.to_dict() or {}).get("phone") or doc.id or "")
            digits = "".join(c for c in phone if c.isdigit())
            if digits:
                h = hashlib.sha256(digits.encode("utf-8")).hexdigest()[:32]
                mapping[h] = phone
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_owner_hash_map failed exc=%s", exc)
    return mapping


async def _enrich_user_connections(user: Dict[str, Any]) -> None:
    """Adiciona google_scopes + composio_apps ao dict do user (D1).

    - google.services: lista TODOS os servicos Google conhecidos, com
      status connected/pending baseado nos scopes do token.
    - composio.services: lista todos os apps Composio (connected ou nao).
    """
    try:
        token = (user.get("google_oauth_token") or {})
        scopes = token.get("scopes") or user.get("scopes") or []
        scope_str = " ".join(str(s) for s in scopes)
        user["google"] = {
            "connected": bool(token),
            "email": token.get("email") or user.get("email") or "",
            "scopes_total": len(OAUTH_SCOPES),
            "scopes_loaded": len(scopes),
            "services": [
                {
                    "id": svc["id"],
                    "label": svc["label"],
                    "icon": svc["icon"],
                    "connected": svc["scope"] in scope_str,
                    "needs_scope": True,
                }
                for svc in _GOOGLE_SERVICE_MAP
            ],
            "scopes": [str(s) for s in scopes],
        }
    except Exception as exc:  # noqa: BLE001
        user["google"] = {"connected": False, "email": "", "services": [], "scopes": []}
        logger.debug("enrich_google_skipped phone=%s exc=%s", user.get("phone"), exc)
    try:
        from tools.composio_connect import get_status

        _COMPOSIO_FRIENDLY_CATALOG = {
            "googledocs": {
                "label": "Google Docs",
                "icon": "description",
                "description": "Criação, leitura e edição de documentos",
            },
            "linkedin": {
                "label": "LinkedIn",
                "icon": "share",
                "description": "Publicação de posts e engajamento profissional",
            },
            "youtube": {
                "label": "YouTube",
                "icon": "smart_display",
                "description": "Pesquisa de vídeos e detalhes de canais",
            },
            "notion": {
                "label": "Notion",
                "icon": "edit_note",
                "description": "Leitura e criação de páginas e notas corporativas",
            },
            "github": {
                "label": "GitHub",
                "icon": "code",
                "description": "Repositórios, PRs e issues de código",
            },
            "onedrive": {
                "label": "Microsoft OneDrive",
                "icon": "cloud",
                "description": "Acesso a arquivos e pastas na nuvem",
            },
        }
        _COMPOSIO_EXCLUDED = {"googlecalendar", "gmail", "googledrive", "google_maps"}

        status = await get_status(str(user.get("phone") or ""))
        apps = (status or {}).get("apps") or {}
        comp_services = []
        for slug, data in apps.items():
            if slug in _COMPOSIO_EXCLUDED:
                continue
            meta = _COMPOSIO_FRIENDLY_CATALOG.get(slug, {
                "label": (data or {}).get("name") or slug.replace("_", " ").title(),
                "icon": "hub",
                "description": f"Conexão com {slug}",
            })
            comp_services.append({
                "id": slug,
                "label": meta["label"],
                "icon": meta["icon"],
                "description": meta["description"],
                "connected": bool((data or {}).get("connected")),
            })
        user["composio"] = {"services": comp_services}
    except Exception as exc:  # noqa: BLE001
        user["composio"] = {"services": []}
        logger.debug("enrich_composio_skipped phone=%s exc=%s", user.get("phone"), exc)


@app.api_route("/admin/approve-user", methods=["GET", "POST"])
async def admin_approve_user(
    request: Request,
    phone: str = "",
    token: str = "",
):
    """Aprova acesso de novo usuário e dispara WhatsApp com link de conexões."""
    from core.admin_notify import parse_approval_token
    from agent_loader import _canonical_phone, save_user, _now_iso, get_user, enrich_user_from_all_sources
    from core.magic_link import build_magic_link_url
    from core.evolution_client import send_text
    from core.auth import resolve_caller_profile

    if request.method == "POST":
        try:
            body_bytes = await request.body()
            if body_bytes:
                import urllib.parse
                import json
                body_str = body_bytes.decode("utf-8", errors="ignore")
                parsed_qs = urllib.parse.parse_qs(body_str)
                if "token" in parsed_qs:
                    token = parsed_qs["token"][0]
                if "phone" in parsed_qs:
                    phone = parsed_qs["phone"][0]
                if not token and body_str.startswith("{"):
                    json_data = json.loads(body_str)
                    token = json_data.get("token", token)
                    phone = json_data.get("phone", phone)
        except Exception:
            pass

    if not token:
        token = request.query_params.get("token", "")
    if not phone:
        phone = request.query_params.get("phone", "")

    approved_phone = parse_approval_token(token)
    if not approved_phone:
        try:
            caller = resolve_caller_profile(request)
            if caller.get("is_admin") and phone:
                approved_phone = phone
        except Exception:
            pass

    if not approved_phone:
        return HTMLResponse(
            content="""<!DOCTYPE html><html><body style="background:#0f172a;color:#ef4444;font-family:sans-serif;text-align:center;padding:40px;">
            <h2>Link de Aprovação Inválido ou Expirado</h2><p>Solicite uma nova aprovação ou configure diretamente no painel do administrador.</p>
            </body></html>""",
            status_code=403,
        )

    canonical = _canonical_phone(approved_phone) or approved_phone
    user_info = get_user(canonical) or {}
    user_name = user_info.get("name") or user_info.get("push_name") or ""
    display_name = user_name if user_name and not user_name.isdigit() and not user_name.startswith("+") else "Novo Contato"

    confirm = request.query_params.get("confirm", "")
    if request.method == "GET" and confirm != "1":
        html_confirm = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aprovar Usuário | Coherence AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 24px; padding: 36px 28px; max-width: 440px; width: 100%; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
    .icon {{ width: 68px; height: 68px; background: rgba(59,130,246,0.15); border: 2px solid #3b82f6; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 34px; color: #3b82f6; }}
    h1 {{ font-size: 22px; margin: 0 0 10px; color: #fff; font-weight: 700; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 24px; }}
    .user-badge {{ display: inline-block; background: #334155; color: #38bdf8; font-weight: 600; padding: 10px 20px; border-radius: 20px; font-size: 15px; margin-bottom: 24px; }}
    .btn {{ display: block; width: 100%; background: #16a34a; color: white; border: none; font-size: 16px; font-weight: 600; padding: 14px 24px; border-radius: 12px; cursor: pointer; transition: background 0.2s; box-sizing: border-box; }}
    .btn:hover {{ background: #15803d; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">👤</div>
    <h1>Solicitação de Acesso</h1>
    <p>Você deseja liberar o acesso como <strong>Analista</strong> para:</p>
    <div class="user-badge">{display_name} (+{canonical})</div>
    <form method="POST" action="/admin/approve-user">
      <input type="hidden" name="phone" value="{canonical}">
      <input type="hidden" name="token" value="{token}">
      <button type="submit" class="btn">✓ Confirmar e Liberar Acesso</button>
    </form>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html_confirm)

    save_user(canonical, {
        "role": "analyst",
        "is_approved": True,
        "approved_at": _now_iso(),
        "approved_by": "admin_whatsapp_link",
    })
    enrich_user_from_all_sources(canonical)

    first_name = display_name.split()[0] if display_name and display_name != "Novo Contato" else ""
    greeting = f"Olá, {first_name}!" if first_name else "Olá!"
    link_url = build_magic_link_url(canonical)
    message = (
        f"🎉 *Acesso Liberado!*\n\n"
        f"{greeting} O administrador liberou seu acesso como *Analista* à Jennifer.\n\n"
        "Para conectar suas contas seguras (Google Agenda, Gmail, Drive, GitHub ou LinkedIn), acesse o link abaixo:\n\n"
        f"👉 {link_url}\n\n"
        "_Agora você já pode pedir resumos de agenda, e-mails e tarefas para a Jennifer no WhatsApp!_"
    )
    try:
        await send_text(phone=canonical, text=message, instance="Jennifer")
    except Exception as exc:
        logger.warning("welcome_msg_send_failed phone=%s exc=%s", canonical, exc)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acesso Liberado | Coherence AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 24px; padding: 36px 28px; max-width: 440px; width: 100%; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
    .icon {{ width: 68px; height: 68px; background: rgba(16,185,129,0.15); border: 2px solid #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 34px; color: #10b981; }}
    h1 {{ font-size: 22px; margin: 0 0 10px; color: #fff; font-weight: 700; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 24px; }}
    .badge {{ display: inline-block; background: #0284c7; color: white; font-weight: 600; padding: 6px 16px; border-radius: 20px; font-size: 13px; margin-bottom: 20px; letter-spacing: 0.5px; }}
    .btn {{ display: block; background: #2563eb; color: white; text-decoration: none; font-weight: 600; padding: 14px 24px; border-radius: 12px; transition: background 0.2s; }}
    .btn:hover {{ background: #1d4ed8; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✓</div>
    <div class="badge">Analista Aprovado</div>
    <h1>Acesso Concedido com Sucesso!</h1>
    <p>O usuário <strong>{display_name} (+{canonical})</strong> foi aprovado como <strong>Analista</strong>.<br>Uma notificação com o link de conexões já foi enviada no WhatsApp dele.</p>
    <a href="/admin" class="btn">Abrir Painel de Controle</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.api_route("/admin/unblock-user", methods=["GET", "POST"])
async def admin_unblock_user(
    request: Request,
    phone: str = "",
    token: str = "",
):
    """Desbloqueia usuário colocado em quarentena por flood/segurança com 1 clique."""
    from core.admin_notify import parse_unblock_token
    from core.flood_protection import unquarantine_user, get_user_finops_metrics
    from agent_loader import _canonical_phone
    from core.auth import resolve_caller_profile

    if request.method == "POST":
        try:
            body_bytes = await request.body()
            if body_bytes:
                import urllib.parse
                import json
                body_str = body_bytes.decode("utf-8", errors="ignore")
                parsed_qs = urllib.parse.parse_qs(body_str)
                if "token" in parsed_qs:
                    token = parsed_qs["token"][0]
                if "phone" in parsed_qs:
                    phone = parsed_qs["phone"][0]
                if not token and body_str.startswith("{"):
                    json_data = json.loads(body_str)
                    token = json_data.get("token", token)
                    phone = json_data.get("phone", phone)
        except Exception:
            pass

    if not token:
        token = request.query_params.get("token", "")
    if not phone:
        phone = request.query_params.get("phone", "")

    unblocked_phone = parse_unblock_token(token)
    if not unblocked_phone:
        try:
            caller = resolve_caller_profile(request)
            if caller.get("is_admin") and phone:
                unblocked_phone = _canonical_phone(phone)
        except Exception:
            pass

    if not unblocked_phone:
        return HTMLResponse(
            content="""<!DOCTYPE html><html><body style="background:#0f172a;color:#ef4444;font-family:sans-serif;text-align:center;padding:40px;">
            <h2>Link de Liberação Inválido ou Expirado</h2><p>Solicite um novo link ou desbloqueie o usuário diretamente no painel FinOps do administrador.</p>
            </body></html>""",
            status_code=400,
        )

    canonical = _canonical_phone(unblocked_phone)
    success = unquarantine_user(canonical)
    metrics = get_user_finops_metrics(canonical)
    display_name = metrics.get("name", f"+{canonical}")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Usuário Liberado | Coherence AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 24px; padding: 36px 28px; max-width: 440px; width: 100%; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
    .icon {{ width: 68px; height: 68px; background: rgba(16,185,129,0.15); border: 2px solid #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 34px; color: #10b981; }}
    h1 {{ font-size: 22px; margin: 0 0 10px; color: #fff; font-weight: 700; }}
    p {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 24px; }}
    .badge {{ display: inline-block; background: #10b981; color: white; font-weight: 600; padding: 6px 16px; border-radius: 20px; font-size: 13px; margin-bottom: 20px; letter-spacing: 0.5px; }}
    .btn {{ display: block; background: #2563eb; color: white; text-decoration: none; font-weight: 600; padding: 14px 24px; border-radius: 12px; transition: background 0.2s; }}
    .btn:hover {{ background: #1d4ed8; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✓</div>
    <div class="badge">Usuário Liberado</div>
    <h1>Jennifer Desbloqueada com Sucesso!</h1>
    <p>O usuário <strong>{display_name} (+{canonical})</strong> foi liberado.<br>A Jennifer voltará a responder às mensagens e comandos normalmente.</p>
    <a href="/admin" class="btn">Abrir Painel Omnichannel</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.get("/admin/finops/overview")
async def admin_finops_overview(request: Request, instance: str = ""):
    """Retorna visão geral de custos, mensagens e usuários para o painel FinOps."""
    from core.auth import resolve_caller_profile
    from core.flood_protection import get_all_finops_overview

    caller = resolve_caller_profile(request)
    if not caller.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin_only")

    overview = get_all_finops_overview(instance=instance)
    return JSONResponse(content=overview)


@app.post("/admin/users/{phone}/unblock")
async def admin_user_unblock_api(phone: str, request: Request):
    """Desbloqueia um usuário manualmente pelo painel."""
    from core.auth import resolve_caller_profile
    from core.flood_protection import unquarantine_user
    from agent_loader import _canonical_phone

    caller = resolve_caller_profile(request)
    if not caller.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin_only")

    canonical = _canonical_phone(phone)
    success = unquarantine_user(canonical)
    return JSONResponse(content={"status": "ok", "unblocked": success, "phone": canonical})


@app.post("/admin/users/{phone}/block")
async def admin_user_block_api(phone: str, request: Request):
    """Bloqueia/coloca um usuário em quarentena manualmente pelo painel."""
    from core.auth import resolve_caller_profile
    from core.flood_protection import quarantine_user
    from agent_loader import _canonical_phone

    caller = resolve_caller_profile(request)
    if not caller.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin_only")

    canonical = _canonical_phone(phone)
    quarantine_user(canonical, reason="admin_manual_block")
    return JSONResponse(content={"status": "ok", "blocked": True, "phone": canonical})


@app.post("/admin/me/phone")
async def admin_me_phone_update(request: Request):
    """Vincula o telefone WhatsApp do usuário autenticado no Portal via Google SSO."""
    from core.auth import resolve_caller_profile
    from agent_loader import _canonical_phone, save_user, _now_iso

    caller = resolve_caller_profile(request)
    email = caller.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="unauthenticated")

    body = await request.json()
    new_phone = body.get("phone", "")
    canonical = _canonical_phone(new_phone)
    if not canonical:
        raise HTTPException(status_code=422, detail="invalid_phone")

    save_user(canonical, {
        "email": email.lower().strip(),
        "phone": canonical,
        "name": caller.get("name") or "",
        "picture": caller.get("picture") or "",
        "firebase_uid": caller.get("uid") or "",
        "role": "analyst",
        "is_approved": True,
        "updated_at": _now_iso(),
    })
    return JSONResponse(content={"status": "ok", "phone": canonical})


@app.get("/admin/users/{phone}")
async def admin_users_get(phone: str, request: Request):
    """Get a specific user (self or admin)."""
    _require_self_or_admin(request, phone)
    user = get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    return JSONResponse(content={"user": user})


@app.get("/admin/users/{phone}/magic-link")
async def admin_users_magic_link(phone: str, request: Request):
    """Gera o magic link do usuário (admin ou self)."""
    _require_self_or_admin(request, phone)
    from core.magic_link import build_magic_link_url
    from agent_loader import _canonical_phone

    canonical = _canonical_phone(phone) or phone
    url = build_magic_link_url(canonical)
    return JSONResponse(content={"phone": canonical, "magic_link": url})


@app.post("/admin/users/{phone}/invite")
async def admin_users_invite(phone: str, request: Request):
    """Admin dispara convite via WhatsApp com Magic Link para o usuário conectar suas contas."""
    _require_admin(request)
    from core.magic_link import build_magic_link_url
    from core.evolution_client import send_text
    from agent_loader import _canonical_phone, save_user, _now_iso

    canonical = _canonical_phone(phone) or phone
    save_user(canonical, {
        "role": "analyst",
        "is_approved": True,
        "approved_at": _now_iso(),
        "approved_by": "admin_portal_invite",
    })

    link_url = build_magic_link_url(canonical)
    message = (
        "👋 *Olá!*\n\n"
        "Seu acesso às integrações e conexões da *Jennifer* foi liberado pelo Administrador.\n\n"
        "Para conectar suas contas seguras (Google Agenda, Gmail, Drive, GitHub ou LinkedIn), acesse o link abaixo:\n\n"
        f"🔗 {link_url}\n\n"
        "_Após conectar suas contas, você poderá solicitar consultas de agenda, e-mails e tarefas diretamente para a Jennifer aqui no WhatsApp!_"
    )
    send_res = False
    try:
        send_res = await send_text(phone=canonical, text=message, instance="Jennifer")
    except Exception as exc:
        logger.warning("invite_send_text_failed phone=%s exc=%s", canonical, exc)
        send_res = False

    return JSONResponse(content={
        "status": "ok",
        "phone": canonical,
        "magic_link": link_url,
        "whatsapp_sent": bool(send_res),
    })


@app.post("/admin/users/{phone}/folder-permissions")
async def admin_users_folder_permissions_grant(phone: str, request: Request):
    """Grant (or blacklist) a folder permission for a user.

    Body:
        {"tool": "drive"|"gmail"|"calendar",
         "pattern": "folder_id_or_email_or_*",
         "scope": "whitelist"|"blacklist",
         "created_by": "..."  (optional, defaults to admin-sa-token)}

    Permissoes sao armazenadas em
    usuarios/{phone}/folder_permissions/{permission_id}.
    """
    _require_self_or_admin(request, phone)
    from core.folder_permissions import grant_folder_permission

    body = await request.json()
    tool = body.get("tool", "")
    pattern = body.get("pattern", "")
    scope = body.get("scope", "whitelist")
    created_by = body.get("created_by", "admin-sa-token")
    if not tool or not pattern:
        raise HTTPException(
            status_code=422, detail="tool e pattern obrigatorios",
        )
    try:
        perm = grant_folder_permission(
            phone=phone,
            tool=tool,
            pattern=pattern,
            scope=scope,
            created_by=created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if perm is None:
        raise HTTPException(
            status_code=503, detail="firestore_unavailable",
        )
    return JSONResponse(content={"status": "ok", "permission": perm})


@app.get("/admin/users/{phone}/folder-permissions")
async def admin_users_folder_permissions_list(phone: str, request: Request):
    """Lista todas as permissoes do user."""
    _require_self_or_admin(request, phone)
    from core.folder_permissions import list_folder_permissions

    return JSONResponse(
        content={"phone": phone, "permissions": list_folder_permissions(phone)},
    )


@app.delete("/admin/users/{phone}/folder-permissions/{permission_id}")
async def admin_users_folder_permissions_revoke(phone: str, permission_id: str, request: Request):
    """Revoga permissao por ID."""
    _require_self_or_admin(request, phone)
    from core.folder_permissions import revoke_folder_permission

    ok = revoke_folder_permission(phone, permission_id)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail="firestore_unavailable_or_not_found",
        )
    return JSONResponse(
        content={"status": "ok", "phone": phone, "permission_id": permission_id},
    )


@app.get("/admin/groups")
async def admin_groups_list(request: Request):
    """List groups where a phone is a member (for Portal)."""
    phone = request.query_params.get("phone", "")
    if not phone:
        raise HTTPException(status_code=422, detail="phone query param required")
    try:
        from tools.group import list_active_groups, get_member_confirmation
        all_groups = await list_active_groups()
        result = []
        for g in all_groups:
            members = g.get("members", [])
            is_member = phone in members
            if is_member:
                group_jid = g.get("group_jid", "")
                confirmed = await get_member_confirmation(group_jid, phone)
                result.append({
                    "group_jid": group_jid,
                    "name": g.get("name", group_jid),
                    "members_count": g.get("members_count", len(members)),
                    "drive_folder_id": g.get("drive_folder_id"),
                    "confirmed": confirmed,
                })
        return JSONResponse(content={"groups": result})
    except Exception as e:
        return JSONResponse(content={"groups": [], "error": str(e)})


@app.post("/admin/groups/confirm")
async def admin_groups_confirm(request: Request):
    """Toggle group data sharing confirmation for a member."""
    body = await request.json()
    group_jid = body.get("group_jid", "")
    phone = body.get("phone", "")
    confirmed = body.get("confirmed", True)
    if not group_jid or not phone:
        raise HTTPException(status_code=422, detail="group_jid and phone required")
    try:
        from tools.group import set_member_confirmation
        success = await set_member_confirmation(group_jid, phone, confirmed)
        return JSONResponse(content={"status": "ok" if success else "error", "confirmed": confirmed})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)})


@app.post("/admin/knowledge")
async def admin_knowledge_post(request: Request):
    """Index a document in the shared knowledge base."""
    body = await request.json()
    titulo = body.get("titulo", "")
    conteudo = body.get("conteudo", "")
    categoria = body.get("categoria", "geral")
    if not titulo or not conteudo:
        raise HTTPException(status_code=422, detail="titulo and conteudo required")

    try:
        from core.rag import EMBEDDING_DIM, SCHEMA_VERSION, index_shared_document
        doc_id = await index_shared_document(titulo, conteudo, categoria)
        return JSONResponse(content={
            "status": "ok",
            "doc_id": doc_id,
            "embedding_dim": EMBEDDING_DIM,
            "schema_version": SCHEMA_VERSION,
        })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/knowledge/user")
async def admin_knowledge_user_post(request: Request):
    """Index a document into the USER's private Firestore Vector (knowledge-database).

    Mesmo pipeline que a Jennifer usa para conhecimento individual: chunking
    semantico + embedding OpenAI + armazenamento em knowledge-database (scope=private).
    Body: {"phone": "...", "titulo": "...", "conteudo": "...", "categoria": "..."}
    """
    body = await request.json()
    phone = str(body.get("phone", "") or "").strip()
    titulo = str(body.get("titulo", "") or "").strip()
    conteudo = str(body.get("conteudo", "") or "")
    categoria = str(body.get("categoria", "") or "geral").strip()
    if not phone:
        raise HTTPException(status_code=422, detail="phone required")
    if not titulo or not conteudo:
        raise HTTPException(status_code=422, detail="titulo and conteudo required")

    try:
        from core.rag import EMBEDDING_DIM, SCHEMA_VERSION, index_private_document
        result = await index_private_document(
            phone=phone,
            text_content=conteudo,
            source_title=titulo,
            category=categoria,
            class_=categoria,
            group=None,
            theme=None,
        )
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return JSONResponse(content={
            "status": "ok",
            "doc_ids": result.get("doc_ids", []),
            "chunks_indexed": result.get("chunks_indexed", 0),
            "chunks": result.get("chunks", 0),
            "embedding_dim": EMBEDDING_DIM,
            "schema_version": SCHEMA_VERSION,
            "truncated": result.get("truncated", False),
            "collection": result.get("collection", "knowledge-database"),
        })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/knowledge/search")
async def admin_knowledge_search(request: Request):
    """Semantic search in shared knowledge base."""
    query = request.query_params.get("q", "")
    limit = int(request.query_params.get("limit", "5"))
    if not query:
        raise HTTPException(status_code=422, detail="q parameter required")

    try:
        from core.rag import search_knowledge
        results = await search_knowledge(query, limit=limit)
        return JSONResponse(content={"query": query, "results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/dashboard/orchestration")
async def admin_dashboard_orchestration():
    """Return last 5 orchestration interactions with full agent path."""
    interactions = get_recent_interactions(limit=5)
    return JSONResponse(content={
        "interactions": interactions,
        "count": len(interactions),
    })


@app.post("/admin/playground")
async def admin_playground(request: Request):
    """Test a message in isolated environment (Portal Playground)."""
    return await chat(request)


@app.get("/admin/cache/stats")
async def admin_cache_stats():
    """Get agent loader cache statistics."""
    from agent_loader import get_cache_stats
    return JSONResponse(content=get_cache_stats())


# ==============================================================================
# Composio Platform — Connect API (Portal Omnichannel / Agent Module)
# ==============================================================================


@app.get("/api/v1/composio/status")
async def composio_status(request: Request, phone: str = ""):
    """Retorna status de conexao de todos os auth configs do usuario."""
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    _require_self_or_admin(request, phone)
    from tools.composio_connect import get_status
    result = await get_status(phone)
    return JSONResponse(content=result)


@app.post("/api/v1/composio/connect-all")
async def composio_connect_all(request: Request):
    """Gera Connect Links para todos os apps NAO conectados do usuario."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    phone = (body.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    _require_self_or_admin(request, phone)
    from tools.composio_connect import connect_all
    result = await connect_all(phone)
    return JSONResponse(content=result)


@app.post("/api/v1/composio/authorize-owner")
async def composio_authorize_owner(request: Request):
    """Gera Connect Links para TODOS os 12 auth configs (owner)."""
    _require_admin(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    phone = (body.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    from tools.composio_connect import authorize_owner
    result = await authorize_owner(phone)
    return JSONResponse(content=result)


@app.post("/api/v1/composio/authorize")
async def composio_authorize(request: Request):
    """Gera Connect Link para UM app Composio de qualquer usuario (multi-tenant).

    Body: {"phone": "...", "toolkit": "linkedin|youtube|..."} (toolkit opcional —
    sem toolkit, gera links para todos os apps pendentes).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    phone = (body.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    _require_self_or_admin(request, phone)
    toolkit = (body.get("toolkit") or "").strip()
    from tools.composio_connect import connect_all
    result = await connect_all(phone, toolkit=toolkit)
    if toolkit:
        links = result.get("links", [])
        result["links"] = [item for item in links if item.get("toolkit") == toolkit]
    return JSONResponse(content=result)


@app.get("/")
async def root_redirect(request: Request):
    """Return the service metadata for plain API clients, or the HTML module
    UI when the caller authenticates (Bearer header or ``?token=`` query). The
    Portal opens the runtime via this URL with a token; detecting the token
    and serving ``render_dashboard()`` keeps the integration zero-config.
    """
    token = _bearer_token(request)
    if not token:
        token = request.query_params.get("token", "")
    if token:
        from core.module_ui import render_dashboard
        response = HTMLResponse(content=render_dashboard(COMMIT_SHA, DEPLOYED_AT))
        _set_session_cookie(response, token)
        return response
    return JSONResponse(content={
        "service": "agents_runtime",
        "version": VERSION,
        "endpoints": {
            "health": "/healthz",
            "dashboard": "/admin/dashboard",
            "orchestration": "/admin/dashboard/orchestration",
            "agents": "/admin/agents",
            "accounts": "/admin/accounts",
            "status": "/admin/status",
        },
    })


OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "").strip()
OAUTH_CLIENT_SECRET = (os.getenv("OAUTH_CLIENT_SECRET") or "").strip()
from core.google_scopes import ALL_OAUTH_SCOPES as OAUTH_SCOPES  # noqa: E402
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "").strip()


def _oauth_redirect_uri(request: Request) -> str:
    if OAUTH_REDIRECT_URI:
        return OAUTH_REDIRECT_URI
    forwarded_proto = request.headers.get("x-forwarded-proto", "").strip().lower()
    scheme = forwarded_proto or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    return f"{scheme}://{host}/oauth/callback"


@app.get("/a/{phone}/conectar")
async def onboarding_conectar(phone: str, request: Request):
    """Página pública de onboarding: conecta Google + TODOS os apps Composio."""
    from agent_loader import get_user

    user = get_user(phone) or {}
    has_google = bool(user.get("google_oauth_token"))
    base = _oauth_redirect_uri(request).replace("/oauth/callback", "")
    google_html = (
        '<p style="color:#16a34a;font-weight:600">✅ Google já conectado</p>'
        if has_google else
        '<a href="' + base + '/oauth/google?phone=' + phone + '">'
        '<button style="background:#4285F4;color:#fff;border:0;padding:14px 28px;border-radius:8px;'
        'font-size:16px;font-weight:600;cursor:pointer">Conectar Google</button></a>'
    )
    html = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Conectar contas</title>
    <style>body{font-family:Inter,system-ui,sans-serif;background:#f9fafb;margin:0;padding:40px 16px}
    .card{max-width:520px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:32px}
    h1{font-size:22px;color:#111827} .sec{margin:24px 0} .sec h2{font-size:15px;color:#374151;margin-bottom:12px}
    .hint{font-size:13px;color:#6b7280;margin-top:10px;line-height:1.5}
    #comp-status{font-size:13px;color:#6b7280;margin-top:12px}
    .ok{color:#16a34a;font-weight:600}</style></head><body><div class="card">
    <h1>Conectar suas contas</h1>
    <p style="color:#6b7280;font-size:14px">Autorize o acesso para que a Jennifer consiga usar seus serviços. São 2 cliques.</p>
    <div class="sec"><h2>🔵 Google</h2>{google_html}
      <p class="hint">Calendário, Gmail e Drive — após autorizar, o browser volta para cá.</p></div>
    <div class="sec"><h2>🟣 Apps (Composio)</h2>
      <button onclick="conectarComposio()" style="background:#111827;color:#fff;border:0;padding:14px 28px;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer">Conectar TODOS os apps</button>
      <div id="comp-status"></div>
      <p class="hint">YouTube, LinkedIn, GitHub, Notion, GoogleDocs, OneDrive e mais. Cada app abre uma aba para autorizar.</p></div>
    <p class="hint" style="margin-top:28px">Depois de conectar, volte ao WhatsApp e continue a conversa com a Jennifer. 🚀</p>
    </div>
    <script>
    const BASE = {base_js};
    const PHONE = {phone_js};
    async function conectarComposio() {
      const st = document.getElementById('comp-status');
      st.innerHTML = 'Gerando links de conexão…';
      try {
        const res = await fetch(BASE + '/a/' + PHONE + '/composio', {method:'POST'});
        const data = await res.json();
        const links = data.links || [];
        const pendentes = links.filter(l => l.url);
        if (!pendentes.length) { st.innerHTML = '<span class="ok">Todos os apps já estão conectados! ✅</span>'; return; }
        st.innerHTML = 'Abra ' + pendentes.length + ' aba(s) e autorize cada app. Depois volte aqui.';
        pendentes.forEach(l => window.open(l.url, '_blank'));
      } catch (e) { st.innerHTML = 'Erro: ' + e.message; }
    }
    </script></body></html>"""
    html = (
        html.replace("{google_html}", google_html)
        .replace("{base_js}", json.dumps(base))
        .replace("{phone_js}", json.dumps(phone))
    )
    return HTMLResponse(content=html)


@app.post("/a/{phone}/composio")
async def onboarding_composio(phone: str, toolkit: Optional[str] = None):
    """Gera links de conexao para apps Composio (todos ou toolkit especifico)."""
    from tools.composio_connect import connect_all

    result = await connect_all(phone, toolkit=toolkit or "")
    links = result.get("links", [])
    out = [
        {"toolkit": item.get("toolkit"), "url": item.get("connect_url") or item.get("url")}
        for item in links
        if item.get("connect_url") or item.get("url")
    ]
    already = sum(1 for item in links if item.get("status") == "connected")
    return JSONResponse(content={"phone": phone, "links": out, "already_connected": already, "total": len(links)})


@app.get("/oauth/google")
async def oauth_google(request: Request):
    import urllib.parse
    from core.oauth_per_user import create_oauth_state

    phone = request.query_params.get("phone", "")
    if not phone:
        raise HTTPException(status_code=422, detail="phone required")
    role, caller_phone = _caller_role(request)
    if role == "agent_user":
        target = "".join(c for c in str(phone) if c.isdigit())
        if not caller_phone or target != caller_phone:
            raise HTTPException(status_code=403, detail="forbidden_resource")
    if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="oauth_not_configured")
    try:
        state = create_oauth_state(phone)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_phone")
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": _oauth_redirect_uri(request),
        "scope": " ".join(OAUTH_SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=auth_url)


@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    import requests
    from core.oauth_per_user import parse_oauth_state

    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    if not code:
        return HTMLResponse(content="<h2>Erro: codigo de autorizacao nao recebido</h2>", status_code=400)
    phone = parse_oauth_state(state)
    if not phone:
        return HTMLResponse(content="<h2>Erro: autorizacao expirada ou invalida</h2>", status_code=400)
    if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
        return HTMLResponse(content="<h2>Erro: OAuth nao configurado</h2>", status_code=503)

    try:
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": _oauth_redirect_uri(request),
            "grant_type": "authorization_code",
        }, timeout=15)
        response.raise_for_status()
        token_response = response.json()
        if "error" in token_response or not token_response.get("access_token"):
            return HTMLResponse(content="<h2>Erro ao obter autorizacao</h2>", status_code=502)

        now_brt_dt = now_brt()
        # F4 (12/08/2026): salvar os scopes REALMENTE concedidos pelo Google.
        # O token_response traz "scope" (separado por espaco) com o que foi
        # aprovado na tela de consentimento. Fallback para OAUTH_SCOPES.
        granted_raw = token_response.get("scope", "")
        granted_scopes = [s.strip() for s in granted_raw.split() if s.strip()] if granted_raw else list(OAUTH_SCOPES)
        token_data = {
            "token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token", ""),
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": granted_scopes,
            "expiry": str(time.time() + token_response.get("expires_in", 3600)),
            "linked_at": now_brt_dt.isoformat(),
        }
        from agent_loader import save_user, sync_user_profile, enrich_user_from_all_sources
        
        # Enriquecer perfil via Gmail / ID token / Portal Coherence
        user_email = ""
        user_name = ""
        user_picture = ""
        
        # 1. Tentar ler Gmail Profile
        try:
            gm_res = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {token_response['access_token']}"},
                timeout=5,
            )
            if gm_res.status_code == 200:
                user_email = gm_res.json().get("emailAddress", "")
        except Exception:
            pass

        # 2. Tentar ID token se disponivel
        id_token = token_response.get("id_token")
        if id_token and "." in id_token:
            try:
                import base64
                import json
                payload_part = id_token.split(".")[1]
                payload_part += "=" * (-len(payload_part) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload_part.encode()).decode("utf-8"))
                if not user_email:
                    user_email = claims.get("email", "")
                if not user_name:
                    user_name = claims.get("name", "")
                if not user_picture:
                    user_picture = claims.get("picture", "")
            except Exception:
                pass

        user_update: Dict[str, Any] = {
            "phone": phone,
            "google_oauth_token": token_data,
            "scopes": granted_scopes,
            "google_oauth_linked_at": now_brt_dt.isoformat(),
            "role": "analyst",
            "is_approved": True,
        }
        if user_email:
            user_update["email"] = user_email.lower().strip()
        if user_name:
            user_update["name"] = user_name
            user_update["display_name"] = user_name
        if user_picture:
            user_update["picture"] = user_picture

        saved = save_user(phone, user_update)
        if user_email:
            sync_user_profile(phone, email=user_email, name=user_name, picture=user_picture, role="analyst")
        enrich_user_from_all_sources(phone)

        if not saved:
            return HTMLResponse(content="<h2>Erro ao salvar autorizacao</h2>", status_code=503)
        return HTMLResponse(content="""
        <html><body style="font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f9fafb">
        <div style="text-align:center"><h1 style="color:#16a34a">Vinculado com sucesso!</h1>
        <p style="color:#374151">Sua conta Google foi conectada. A Jennifer ja pode acessar sua agenda e emails.</p>
        <p style="color:#9ca3af;font-size:14px">Feche esta pagina e volte ao WhatsApp.</p></div></body></html>
        """)
    except Exception as exc:
        logger.error(
            "oauth_callback_failed",
            extra={"event_name": "oauth_callback_failed", "error_type": type(exc).__name__},
        )
        return HTMLResponse(content="<h2>Erro ao concluir autorizacao</h2>", status_code=502)
