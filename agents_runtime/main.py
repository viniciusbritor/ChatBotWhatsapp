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
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse as _JSONResponse, HTMLResponse, Response
from starlette.responses import RedirectResponse

from core.auth import auth_middleware
from core.delay_calculator import calculate_delay_ms
from core.logging import configure_logging
from core.masker import mask_pii
from core import metrics
from agent_loader import start_loader, stop_loader, list_agents, list_skills, list_tools, get_agent
from agent_loader import upsert_agent, delete_agent, upsert_skill, upsert_tool
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init/cleanup."""
    logger.info(f"agents_runtime v{VERSION} starting (commit={COMMIT_SHA})")

    start_loader()
    logger.info("Agent loader started")

    yield

    await drain_indexing_tasks()
    stop_loader()
    logger.info("agents_runtime shutting down")


app = FastAPI(
    title="agents_runtime",
    version=VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.middleware("http")(auth_middleware)


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
    if not body.get("phone"):
        raise HTTPException(status_code=422, detail="phone required")
    if not body.get("text") and not has_audio:
        raise HTTPException(status_code=422, detail="text or audio required")

    if has_audio:
        try:
            from core.audio_transcribe import (
                transcribe_base64,
                transcribe_url,
            )

            mimetype = extra.get("audio_mimetype", "audio/ogg")
            if extra.get("audio_base64"):
                result = await transcribe_base64(
                    extra["audio_base64"],
                    mimetype,
                    instance=body.get("instance", "Jennifer"),
                )
                source = "base64"
            elif extra.get("audio_url"):
                result = await transcribe_url(
                    extra["audio_url"],
                    mimetype,
                    instance=body.get("instance", "Jennifer"),
                )
                source = "url"
            else:
                raise ValueError("audio_payload_missing")

            transcript = result["transcript"]
            extra["audio_provider"] = result.get("provider", "minimax:MiniMax-M3")
            extra["audio_provider_reason"] = result.get("reason", "")
            body["text"] = mask_pii(transcript)
            extra["audio_transcribed"] = True
            extra["audio_source"] = source
            body["extra"] = extra
            logger.info(
                "Audio transcribed: source=%s provider=%s chars=%s",
                source,
                extra.get("audio_provider"),
                len(body["text"]),
            )
        except (ValueError, RuntimeError) as e:
            logger.warning("Audio transcription rejected: code=%s message_id=%s", str(e), body.get("message_id", ""))
            if not body.get("text"):
                audit_result = await index_audio_failure_for_audit(body, str(e))
                reply = "Nao consegui processar esse audio com seguranca. Pode reenviar ou mandar a mensagem em texto?"
                return JSONResponse(content={
                    "reply": reply,
                    "delay_ms": calculate_delay_ms(reply),
                    "presence": "paused",
                    "metadata": {
                        "agent_id": "audio-transcriber",
                        "response_identity": "Jennifer",
                        "error": "audio_transcription_failed",
                        "reason": str(e),
                        "audit_indexed": audit_result.get("status") == "indexed",
                        "audit_status": audit_result.get("status", "error"),
                    },
                })
        except Exception as e:
            logger.error(
                "Audio transcription failed: error_type=%s message_id=%s",
                type(e).__name__,
                body.get("message_id", ""),
            )
            if not body.get("text"):
                audit_result = await index_audio_failure_for_audit(body, f"unavailable:{type(e).__name__}")
                reply = "Nao consegui transcrever esse audio agora. Pode tentar novamente ou enviar em texto?"
                return JSONResponse(content={
                    "reply": reply,
                    "delay_ms": calculate_delay_ms(reply),
                    "presence": "paused",
                    "metadata": {
                        "agent_id": "audio-transcriber",
                        "response_identity": "Jennifer",
                        "error": "audio_transcription_unavailable",
                        "audit_indexed": audit_result.get("status") == "indexed",
                        "audit_status": audit_result.get("status", "error"),
                    },
                })

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
        return JSONResponse(content={"status": "ignored", "reason": "filtered"})

    resolve_message_id(envelope)
    message_id = envelope["message_id"]
    ledger_snapshot = register_or_load(message_id, {"payload": envelope, **envelope})
    if ledger_snapshot and ledger_snapshot.get("state") in {"response_ready", "delivered", "failed_terminal"}:
        asyncio.create_task(_safe_mark_read(envelope))
        logger.info(
            "webhook_already_processed",
            extra={
                "event_name": "webhook_already_processed",
                "message_id": message_id,
                "ledger_state": ledger_snapshot.get("state"),
            },
        )
        return JSONResponse(content={"status": "duplicate", "message_id": message_id})

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

    asyncio.create_task(_safe_mark_read(envelope))

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


async def _safe_mark_read(envelope: Dict[str, Any]) -> None:
    """Best-effort Evolution read-receipt without blocking the webhook."""
    try:
        from core.evolution_client import mark_messages_read

        remote_jid = envelope.get("remote_jid", "")
        message_ids = []
        explicit_id = envelope.get("message_id", "")
        if explicit_id:
            message_ids.append(explicit_id)
        if not remote_jid or not message_ids:
            return
        await asyncio.wait_for(
            mark_messages_read(envelope.get("instance", ""), remote_jid, message_ids, from_me=False),
            timeout=5,
        )
        logger.info(
            "evolution_mark_read_ok message_id=%s remote_jid=%s",
            explicit_id,
            remote_jid,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "evolution_mark_read_skipped message_id=%s error=%s",
            envelope.get("message_id", ""),
            type(exc).__name__,
        )


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

    async def _process(p: Dict[str, Any]) -> Dict[str, Any]:
        from core.evolution_client import send_text

        result = await orchestrate(p)
        reply = result.get("reply", "")
        phone = p.get("phone", "") or (p.get("extra") or {}).get("phone", "")
        delivered = False
        delivery_error = ""
        if reply and phone:
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
                logger.warning(
                    "pubsub send_text_skipped reason=%s phone_present=%s",
                    type(send_exc).__name__, bool(phone),
                )
        elif reply and not phone:
            logger.warning(
                "pubsub reply_dropped_empty_phone request_id=%s reply_len=%d",
                request_id, len(reply),
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


def _authorise_admin(request: Request) -> bool:
    from core.auth import _is_valid_firebase_jwt, get_sa_token

    expected = get_sa_token()
    token = _bearer_token(request)
    if expected and token and hmac.compare_digest(token, expected):
        return True
    if token and _is_valid_firebase_jwt(token):
        return True
    return False


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Render the Agentes Omnichannel control plane."""
    from core.module_ui import render_dashboard

    auth_token = _bearer_token(request)
    return HTMLResponse(content=render_dashboard(COMMIT_SHA, DEPLOYED_AT, auth_token))


@app.get("/admin/status")
async def admin_status():
    from core.audio_transcribe import fallback_stats

    return JSONResponse(content={
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "kpis": [
            {"label": "commit", "value": _short_sha(COMMIT_SHA)},
            {"label": "deployed_at", "value": DEPLOYED_AT},
            {"label": "stt_primary", "value": "whisper-local"},
            {"label": "stt_fallback", "value": "gemini-2.5-flash"},
        ],
        "stt_fallback": fallback_stats(),
    })


@app.get("/admin/accounts")
async def admin_accounts_list():
    from agent_loader import _get_firestore_client

    db = _get_firestore_client()
    if db is None:
        return JSONResponse(content={"accounts": []})
    try:
        rows = []
        for doc in db.collection("whatsapp_accounts").stream():
            data = doc.to_dict() or {}
            data["id"] = doc.id
            rows.append(data)
        return JSONResponse(content={"accounts": rows})
    except Exception as exc:
        logger.warning("admin_accounts_list failed: %s", exc)
        return JSONResponse(content={"accounts": []})


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
        "updated_at": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
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


@app.get("/admin/knowledge")
async def admin_knowledge_documents(request: Request):
    from agent_loader import _get_firestore_client
    from core.rag import (
        MEMORY_COLLECTION,
        PRIVATE_COLLECTION,
        SHARED_COLLECTION,
    )

    limit = min(int(request.query_params.get("limit", "10")), 50)
    db = _get_firestore_client()
    documents: list = []
    if db is not None:
        for collection in (PRIVATE_COLLECTION, SHARED_COLLECTION, MEMORY_COLLECTION):
            try:
                for doc in db.collection(collection).limit(limit).stream():
                    data = doc.to_dict() or {}
                    documents.append({
                        "doc_id": doc.id,
                        "title": data.get("source_title") or data.get("titulo") or doc.id,
                        "text": (data.get("text_content") or data.get("conteudo") or data.get("text_masked") or "")[:500],
                        "owner_id": data.get("owner_hash"),
                        "collection": collection,
                    })
            except Exception as exc:
                logger.warning("admin_knowledge_documents failed for %s: %s", collection, exc)
    documents = documents[:limit]
    return JSONResponse(content={"documents": documents, "limit": limit})


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


@app.post("/admin/register-user")
async def admin_register_user(request: Request):
    """Register or update a user with their OAuth token."""
    body = await request.json()
    phone = body.get("phone")
    if not phone:
        raise HTTPException(status_code=422, detail="phone required")
    success = save_user(phone, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "phone": phone,
        "registered": success,
    })


@app.get("/admin/users")
async def admin_users_list():
    """List all registered users."""
    return JSONResponse(content={"users": list_users()})


@app.get("/admin/users/{phone}")
async def admin_users_get(phone: str):
    """Get a specific user."""
    user = get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    return JSONResponse(content={"user": user})


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


@app.get("/")
async def root_redirect(request: Request):
    """Return the service metadata. The Portal opens ``/admin/dashboard`` directly."""
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
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "").strip()


def _oauth_redirect_uri(request: Request) -> str:
    if OAUTH_REDIRECT_URI:
        return OAUTH_REDIRECT_URI
    forwarded_proto = request.headers.get("x-forwarded-proto", "").strip().lower()
    scheme = forwarded_proto or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    return f"{scheme}://{host}/oauth/callback"


@app.get("/oauth/google")
async def oauth_google(request: Request):
    import urllib.parse
    from core.oauth_per_user import create_oauth_state

    phone = request.query_params.get("phone", "")
    if not phone:
        raise HTTPException(status_code=422, detail="phone required")
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
    from core.oauth_per_user import BRT, parse_oauth_state

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

        now_brt = datetime.now(BRT)
        token_data = {
            "token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token", ""),
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": OAUTH_SCOPES,
            "expiry": str(time.time() + token_response.get("expires_in", 3600)),
            "linked_at": now_brt.isoformat(),
        }
        from agent_loader import save_user
        saved = save_user(phone, {
            "phone": phone,
            "google_oauth_token": token_data,
            "scopes": OAUTH_SCOPES,
            "google_oauth_linked_at": now_brt.isoformat(),
        })
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
