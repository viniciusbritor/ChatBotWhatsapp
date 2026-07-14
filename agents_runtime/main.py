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
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.responses import RedirectResponse

from core.auth import auth_middleware
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.escalation import compute_confidence_score
from agent_loader import start_loader, stop_loader, list_agents, list_skills, list_tools, get_agent
from agent_loader import force_reload, upsert_agent, delete_agent, upsert_skill, upsert_tool
from orchestrator import orchestrate, get_recent_interactions

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
    agent_id = body.get("id")
    if not agent_id:
        raise HTTPException(status_code=422, detail="id required")

    success = upsert_agent(agent_id, body)
    return JSONResponse(content={
        "status": "ok" if success else "error",
        "agent_id": agent_id,
        "upserted": success,
    })


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


@app.get("/admin/dashboard/orchestration")
async def admin_dashboard_orchestration():
    """Return last 5 orchestration interactions with full agent path."""
    interactions = get_recent_interactions(limit=5)
    return JSONResponse(content={
        "interactions": interactions,
        "count": len(interactions),
    })


@app.get("/admin/dashboard/diagrama")
async def admin_dashboard_diagrama():
    """Render Mermaid diagram of last 5 agent orchestration paths."""
    interactions = get_recent_interactions(limit=5)

    mermaid_lines = ["flowchart LR"]
    node_id = 0

    for idx, interaction in enumerate(interactions):
        ts = interaction.get("timestamp", 0)
        text = interaction.get("text_preview", "")[:30]
        reply = interaction.get("reply_preview", "")[:30]
        path = interaction.get("path", [])

        mermaid_lines.append(f"")
        mermaid_lines.append(f"    subgraph interacao{idx+1}[\" Msg {idx+1}: {text} \"]")
        mermaid_lines.append(f"        direction LR")

        prev_node = None
        for step in path:
            node_id += 1
            phase = step.get("phase", "")
            agent = step.get("agent", step.get("agent_id", phase))
            label = f"{step.get('step')}. {agent}"

            if phase == "result":
                label += f"\\nmodel: {step.get('model','')}"
                if step.get("escalated"):
                    label += "\\nESCALADO"

            node_style = "fill:#4CAF50,color:#fff" if phase == "result" else "fill:#2196F3,color:#fff"
            mermaid_lines.append(f"        n{node_id}[\"{label}\"]")
            mermaid_lines.append(f"        style n{node_id} {node_style}")

            if prev_node:
                mermaid_lines.append(f"        n{prev_node} --> n{node_id}")
            prev_node = node_id

        mermaid_lines.append(f"    end")

    mermaid_code = "\n".join(mermaid_lines)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Orchestration Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: monospace; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
  h2 {{ color: #4CAF50; }}
  .mermaid {{ background: #16213e; padding: 20px; border-radius: 8px; }}
  .legend {{ margin-top: 20px; padding: 10px; background: #0f3460; border-radius: 8px; }}
  .legend span {{ margin-right: 20px; }}
</style></head><body>
<h2>Agent Orchestration — Ultimas 5 Interacoes</h2>
<div class="legend">
  <span style="color:#2196F3">&#9632; Agente acionado</span>
  <span style="color:#4CAF50">&#9632; Resultado final</span>
</div>
<div class="mermaid">
{mermaid_code}
</div>
<script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
</body></html>"""

    return HTMLResponse(content=html)


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
    """Redirect root to orchestration dashboard, preserving Firebase token."""
    token = request.query_params.get("token", "")
    if token:
        return RedirectResponse(url=f"/admin/dashboard/diagrama?token={token}")
    return JSONResponse(content={
        "service": "agents_runtime",
        "version": VERSION,
        "endpoints": {
            "health": "/healthz",
            "dashboard": "/admin/dashboard/diagrama",
            "orchestration": "/admin/dashboard/orchestration",
            "agents": "/admin/agents",
        },
    })