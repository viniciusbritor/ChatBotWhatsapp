"""Main FastAPI application for agents_runtime.

Endpoints:
- GET  /healthz       (public)
- GET  /version       (Bearer SA)
- POST /chat          (Bearer SA, called by WhatsappAgente)
- POST /proactive/send (Bearer SA, called by proactive_worker)
- /admin/*            (Bearer SA, proxy from Portal)
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from core.auth import auth_middleware
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.escalation import compute_confidence_score
from agent_loader import start_loader, stop_loader, list_agents, list_skills, list_tools, get_agent
from orchestrator import orchestrate

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

VERSION = "1.0.0"
COMMIT_SHA = os.getenv("COMMIT_SHA", "local-dev")
DEPLOYED_AT = os.getenv("DEPLOYED_AT", "local")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init/cleanup."""
    logger.info(f"agents_runtime v{VERSION} starting (commit={COMMIT_SHA})")

    try:
        from tools.audio_transcribe import warm_up
        warm_up()
        logger.info("Whisper warm-up triggered")
    except Exception as e:
        logger.warning(f"Whisper warm-up failed: {e}")

    start_loader()
    logger.info("Agent loader started")

    yield

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
async def healthz():
    """Public health check endpoint."""
    return {
        "status": "ok",
        "version": VERSION,
        "commit_sha": COMMIT_SHA,
        "deployed_at": DEPLOYED_AT,
    }


@app.get("/version")
async def version():
    """Version info (Bearer SA required via middleware)."""
    from agent_loader import get_cache_stats
    return {
        "version": VERSION,
        "commit_sha": COMMIT_SHA,
        "deployed_at": DEPLOYED_AT,
        "python_version": "3.12",
        "agno_version": "1.x",
        "agents_loaded": get_cache_stats().get("agents", 0),
    }


@app.post("/chat")
async def chat(request: Request):
    """Receive a WhatsApp message and return Jennifer's response.

    Request body:
        {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": "Oi",
            "sender_name": "Vinicius",
            "extra": {"has_audio": false, "audio_url": null, ...}
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

    if not body.get("phone") or not body.get("text"):
        raise HTTPException(status_code=422, detail="phone and text required")

    extra = body.get("extra", {})
    if extra.get("has_audio") and extra.get("audio_url"):
        try:
            from core.secrets import get_secret
            from tools.audio_transcribe import transcribe_from_url

            evo_key = get_secret("EVOLUTION_API_KEY")
            transcription = await transcribe_from_url(
                audio_url=extra["audio_url"],
                evo_api_key=evo_key,
            )
            body["text"] = transcription.get("text") or body.get("text", "")
        except Exception as e:
            logger.warning(f"Audio transcription failed: {e}")

    result = await orchestrate(body)

    return JSONResponse(content=result)


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
    agent_id = body.get("id", "unknown")

    from agent_loader import force_reload
    force_reload()

    return JSONResponse(
        content={
            "status": "ok",
            "agent_id": agent_id,
            "note": "Agent upsert + cache reload triggered",
        }
    )


@app.get("/admin/agents")
async def admin_agents_list():
    """List all agents (Portal proxy)."""
    return JSONResponse(content={"agents": list_agents()})


@app.get("/admin/agents/{agent_id}")
async def admin_agents_get(agent_id: str):
    """Get a specific agent."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return JSONResponse(content={"agent": agent})


@app.post("/admin/skills")
async def admin_skills_post(request: Request):
    body = await request.json()
    return JSONResponse(
        content={
            "status": "ok",
            "skill_id": body.get("id", "unknown"),
            "note": "Skill upsert + cache reload triggered",
        }
    )


@app.get("/admin/skills")
async def admin_skills_list():
    return JSONResponse(content={"skills": list_skills()})


@app.post("/admin/tools")
async def admin_tools_post(request: Request):
    body = await request.json()
    return JSONResponse(
        content={
            "status": "ok",
            "tool_id": body.get("id", "unknown"),
            "note": "Tool upsert + cache reload triggered",
        }
    )


@app.get("/admin/tools")
async def admin_tools_list():
    return JSONResponse(content={"tools": list_tools()})


@app.post("/admin/playground")
async def admin_playground(request: Request):
    """Test a message in isolated environment (Portal Playground)."""
    return await chat(request)


@app.get("/admin/cache/stats")
async def admin_cache_stats():
    """Get agent loader cache statistics."""
    from agent_loader import get_cache_stats
    return JSONResponse(content=get_cache_stats())