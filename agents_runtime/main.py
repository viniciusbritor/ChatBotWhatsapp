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
from fastapi.responses import JSONResponse as _JSONResponse, HTMLResponse
from starlette.responses import RedirectResponse

class JSONResponse(_JSONResponse):
    """JSONResponse with ensure_ascii=False for UTF-8 characters."""
    def render(self, content) -> bytes:
        import json
        return json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")

from core.auth import auth_middleware
from core.delay_calculator import calculate_delay_ms, calculate_presence
from core.llm_provider import LLMProvider, LLMError
from core.masker import mask_pii
from core.escalation import compute_confidence_score
from agent_loader import start_loader, stop_loader, list_agents, list_skills, list_tools, get_agent
from agent_loader import force_reload, upsert_agent, delete_agent, upsert_skill, upsert_tool
from agent_loader import get_user, save_user, list_users
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
        from core.rag import index_document, embed_query
        emb_test = await embed_query(titulo + " " + conteudo[:500])
        doc_id = await index_document(titulo, conteudo, categoria)
        return JSONResponse(content={
            "status": "ok",
            "doc_id": doc_id,
            "embedding_dim": len(emb_test) if emb_test else 0,
        })
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


@app.get("/admin/dashboard/diagrama")
async def admin_dashboard_diagrama(request: Request):
    """Full dashboard with 3 tabs: Fluxo, Agentes, Gerenciar."""
    token = request.query_params.get("token", "")
    auth_param = f"?token={token}" if token else ""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Agentes Omnichannel — Coherence</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Inter,-apple-system,sans-serif;background:#f9fafb;color:#171717;min-height:100vh}}
.header{{background:#fff;border-bottom:1px solid #e5e7eb;padding:0 24px;height:56px;display:flex;align-items:center;gap:12px}}
.header img{{height:28px}}
.header .divider{{width:1px;height:20px;background:#d1d5db}}
.header h1{{font-size:15px;font-weight:600;color:#374151}}
.tabs{{display:flex;gap:0;background:#fff;border-bottom:1px solid #e5e7eb;padding:0 24px}}
.tab{{padding:12px 20px;cursor:pointer;font-size:13px;font-weight:500;color:#6b7280;border-bottom:2px solid transparent;transition:all .2s}}
.tab:hover{{color:#374151}}
.tab.active{{color:#3b82f6;border-bottom-color:#3b82f6}}
.tab-content{{display:none;padding:24px}}
.tab-content.active{{display:block}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,0.04)}}
.card h3{{font-size:14px;font-weight:600;color:#111827;margin-bottom:12px}}
.mermaid-box{{overflow-x:auto}}
.interaction-row{{display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #f3f4f6;font-size:13px}}
.interaction-row .step{{background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}}
.interaction-row .step.green{{background:#dcfce7;color:#166534}}
.agent-card{{border-left:3px solid #3b82f6;margin-bottom:12px}}
.agent-card .role{{font-size:11px;text-transform:uppercase;color:#6b7280;letter-spacing:.5px}}
.agent-card .name{{font-size:15px;font-weight:600;color:#111827}}
.agent-card .skills{{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}}
.agent-card .skill-tag{{background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:10px;font-size:11px}}
.agent-card .tool-tag{{background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:11px}}
.form-group{{margin-bottom:12px}}
.form-group label{{display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:4px}}
.form-group input,.form-group textarea,.form-group select{{width:100%;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;font-family:inherit}}
.form-group textarea{{min-height:100px;resize:vertical}}
.btn{{padding:8px 16px;border-radius:6px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:all .15s}}
.btn-primary{{background:#3b82f6;color:#fff}}
.btn-primary:hover{{background:#2563eb}}
.btn-danger{{background:#ef4444;color:#fff;margin-left:8px}}
.btn-danger:hover{{background:#dc2626}}
.btn-sm{{padding:4px 10px;font-size:11px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.loading{{text-align:center;color:#9ca3af;padding:40px;font-size:14px}}
.error{{background:#fef2f2;color:#dc2626;padding:12px;border-radius:6px;font-size:13px}}
.legend{{display:flex;gap:16px;margin-bottom:16px;font-size:12px}}
.legend span{{display:flex;align-items:center;gap:6px}}
.dot{{width:10px;height:10px;border-radius:50%}}
.dot.blue{{background:#3b82f6}}
.dot.green{{background:#22c55e}}
.dot.gray{{background:#9ca3af}}
</style>
</head>
<body>

<div class="header">
  <img src="https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/logo-top-v2.png" alt="Coherence" onerror="this.style.display='none'">
  <div class="divider"></div>
  <h1>Agentes Omnichannel</h1>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('fluxo')">Fluxo de Orquestração</div>
  <div class="tab" onclick="switchTab('agentes')">Agentes & Skills</div>
  <div class="tab" onclick="switchTab('gerenciar')">Gerenciar</div>
  <div class="tab" onclick="switchTab('usuarios')">Usuários</div>
  <div class="tab" onclick="switchTab('grupos')">Grupos</div>
</div>

<div id="tab-fluxo" class="tab-content active">
  <div class="legend">
    <span><span class="dot blue"></span> Agente acionado</span>
    <span><span class="dot green"></span> Resultado final</span>
    <span><span class="dot gray"></span> Passo intermediário</span>
  </div>
  <div id="fluxo-content" class="loading">Carregando fluxo de orquestração...</div>
</div>

<div id="tab-agentes" class="tab-content">
  <div id="agentes-content" class="loading">Carregando agentes...</div>
</div>

<div id="tab-gerenciar" class="tab-content">
  <div class="grid2">
    <div class="card">
      <h3>Criar / Editar Agente</h3>
      <div class="form-group"><label>Selecionar Agente Existente</label><select id="agent-select" onchange="loadAgentForEdit()"><option value="">-- Novo Agente --</option></select></div>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button class="btn btn-primary btn-sm" onclick="newAgentForm()">Novo Agente</button>
        <button class="btn btn-danger btn-sm" id="btn-delete-agent" onclick="deleteAgent()" style="display:none">Excluir</button>
      </div>
      <div class="form-group"><label>ID do Agente</label><input id="agent-id" placeholder="ex: manager-calendar"></div>
      <div class="form-group"><label>Nome</label><input id="agent-name" placeholder="Calendar Manager"></div>
      <div class="form-group"><label>Role</label><select id="agent-role"><option value="orchestrator">Orchestrator</option><option value="manager">Manager</option><option value="specialist">Specialist</option></select></div>
      <div class="form-group"><label>Modelo</label><select id="agent-model"><option value="deepseek-v4-flash">DeepSeek V4 Flash</option><option value="deepseek-v4-pro">DeepSeek V4 Pro</option></select></div>
      <div class="form-group"><label>System Prompt</label><textarea id="agent-prompt" placeholder="System prompt do agente..." style="min-height:120px"></textarea></div>
      <div class="form-group"><label>Skills (IDs separados por vírgula)</label><input id="agent-skills" placeholder="skill-motivacao,skill-busca-contexto"></div>
      <button class="btn btn-primary" onclick="saveAgent()">Salvar Agente</button>
      <div id="agent-msg" style="margin-top:8px;font-size:12px"></div>
    </div>
    <div>
      <div class="card">
        <h3>Criar / Editar Skill</h3>
        <div class="form-group"><label>ID da Skill</label><input id="skill-id" placeholder="ex: skill-motivacao"></div>
        <div class="form-group"><label>Nome</label><input id="skill-name" placeholder="Motivacao pre-reuniao"></div>
        <div class="form-group"><label>Conteúdo (Markdown)</label><textarea id="skill-content" placeholder="Conteudo da skill em markdown..." style="min-height:80px"></textarea></div>
        <button class="btn btn-primary" onclick="saveSkill()">Salvar Skill</button>
        <div id="skill-msg" style="margin-top:8px;font-size:12px"></div>
      </div>
      <div class="card" id="skills-list-card">
        <h3>Skills Existentes</h3>
        <div id="skills-list" class="loading" style="padding:10px">Carregando...</div>
      </div>
    </div>
  </div>
</div>

<div id="tab-usuarios" class="tab-content">
  <div class="card">
    <h3>Vincular Conta Google</h3>
    <p style="font-size:13px;color:#6b7280;margin-bottom:12px">Autorize a Jennifer a acessar seu Calendar, Drive e Gmail. Cada pessoa tem seu proprio token.</p>
    <div class="form-group"><label>Seu telefone com DDI (WhatsApp)</label><input id="user-phone" placeholder="5511999999999"></div>
    <p style="font-size:11px;color:#9ca3af;margin-top:4px">Formato: DDI + DDD + numero. Ex: 5511966830020 (55 = Brasil)</p>
    <button class="btn btn-primary" onclick="startOAuth()">🔑 Vincular Agenda / Email / Drive</button>
    <div id="oauth-msg" style="margin-top:8px;font-size:12px"></div>
  </div>
  <div class="card">
    <h3>Usuários Cadastrados</h3>
    <div id="usuarios-content" class="loading">Carregando...</div>
  </div>
</div>

<div id="tab-grupos" class="tab-content">
  <div class="card">
    <h3>Meus Grupos</h3>
    <p style="font-size:13px;color:#6b7280;margin-bottom:12px">Gerencie em quais grupos a Jennifer pode acessar seus dados (Drive, Calendar, Email).</p>
    <div class="form-group">
      <label>Seu telefone (com DDI)</label>
      <input id="group-phone" placeholder="5511999999999" style="width:280px">
      <button class="btn btn-primary" onclick="loadMeusGrupos()">Buscar Meus Grupos</button>
    </div>
    <div id="grupos-content" style="margin-top:12px;font-size:13px;color:#9ca3af">Informe seu telefone e clique em Buscar.</div>
  </div>
</div>

<script>
const AUTH = '{auth_param}';
const BASE = '';

async function api(path) {{
  const sep = path.includes('?') ? '&amp;' : '';
  const url = BASE + path + (AUTH ? sep + AUTH.substring(1) : '');
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}}

async function apiPost(path, body) {{
  const sep = path.includes('?') ? '&amp;' : '';
  const url = BASE + path + (AUTH ? sep + AUTH.substring(1) : '');
  const r = await fetch(url, {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(body) }});
  return r.json();
}}

async function apiDelete(path) {{
  const url = BASE + path + AUTH;
  const r = await fetch(url, {{ method:'DELETE' }});
  return r.json();
}}

function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const idx = name==='fluxo'?1:name==='agentes'?2:name==='gerenciar'?3:4;
  document.querySelector(`.tab:nth-child(${{idx}})`).classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
  if (name==='fluxo') loadFluxo();
  if (name==='agentes') loadAgentes();
  if (name==='gerenciar') {{ loadSkillsList(); loadAgentSelect(); }}
  if (name==='usuarios') loadUsuarios();
}}

async function loadFluxo() {{
  try {{
    const data = await api('/admin/dashboard/orchestration');
    const interactions = data.interactions || [];
    const last = interactions[0] || {{}};
    const lastPath = last.path || [];
    const activeNodes = lastPath.map(p => p.agent||p.agent_id||p.phase||'').filter(Boolean);
    const lastModel = lastPath.slice(-1)[0]?.model || '';

    let arch = `flowchart TB
subgraph WHATSAPP["WhatsApp"]
    USER["Usuario / Grupos"]
end
subgraph PROXY["Whatsapp-Agente"]
    WEBHOOK["POST /webhook\\\\nG1-G6 guardrails"]
end
subgraph ORCHESTRATOR["Jennifer Orchestrator\\\\ngemini-2.5-flash"]
    INTENT["detect_intent()"]
    ROUTE["resolve_agent()"]
end
subgraph MANAGERS["4 Managers"]
    CAL["Calendar\\\\nlist_events, create, update"]
    DRV["Drive\\\\nsearch, upload, list"]
    EML["Email\\\\nsearch_messages, send"]
    WEB["Web\\\\nserper_search"]
end
subgraph LLMS["LLM Cascade"]
    GEM["1. Gemini 2.5 Flash\\\\nVertex AI ADC - 3-8s"]
    DS["2. DeepSeek V4 Flash\\\\n5-15s"]
    DSP["3. DeepSeek V4 Pro"]
    NV["4-5. NVIDIA NIM"]
    MM["6. MiniMax M3"]
end

USER --> EVO --> WEBHOOK --> ORCHESTRATOR
ORCHESTRATOR --> INTENT --> ROUTE
ROUTE -->|calendar| CAL
ROUTE -->|drive| DRV
ROUTE -->|email| EML
ROUTE -->|web| WEB
CAL --> GEM
DRV --> GEM
EML --> GEM
WEB --> GEM
GEM -->|fallback| DS -->|fallback| DSP -->|fallback| NV -->|fallback| MM

style ORCHESTRATOR fill:#3b82f6,color:#fff
style GEM fill:#22c55e,color:#fff
style WEBHOOK fill:#f59e0b,color:#fff`;

    document.getElementById('fluxo-content').innerHTML = `
      <div class="card">
        <div class="mermaid-box"><div class="mermaid">${{arch}}</div></div>
      </div>
      <div class="card"><h3>Últimas Interações</h3>
        ${{interactions.length===0 ? '<p style="color:#9ca3af;font-size:13px">Nenhuma interacao registrada.</p>' : interactions.map((ix,idx) => `
          <div class="interaction-row">
            <span style="color:#9ca3af;min-width:20px">#${{idx+1}}</span>
            <span style="flex:1;font-weight:500">${{ix.text_preview||''}}</span>
            <span class="step green">${{(ix.path||[]).slice(-1)[0]?.agent_id||'?'}}</span>
            <span style="color:#9ca3af;font-size:11px">${{(ix.path||[]).slice(-1)[0]?.model||''}}</span>
          </div>`).join('')}}
      </div>`;
    setTimeout(() => {{
      if (window.mermaid) mermaid.initialize({{startOnLoad:true, theme:'neutral'}});
    }}, 100);
  }} catch(e) {{
    document.getElementById('fluxo-content').innerHTML = `<div class="error">Erro: ${{e.message}}</div>`;
  }}
}}

async function loadAgentes() {{
  try {{
    const agents = (await api('/admin/agents')).agents || [];
    const skills = (await api('/admin/skills')).skills || [];
    const skillMap = {{}};
    skills.forEach(s => skillMap[s.id] = s);
    document.getElementById('agentes-content').innerHTML = agents.map(a => `
      <div class="card agent-card">
        <div class="role">${{a.role}}</div>
        <div class="name">${{a.name}} <span style="font-weight:400;font-size:12px;color:#9ca3af">(${{a.id}})</span></div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px">Modelo: ${{a.model||'-'}} ${{a.model_escalation?'| Escalação: '+a.model_escalation:''}}</div>
        <div style="font-size:12px;color:#6b7280">Ativo: ${{a.enabled?'Sim':'Não'}} | Thinking: ${{a.thinking||'disabled'}}</div>
        <div class="skills">
          ${{(a.skills||[]).map(sid => `<span class="skill-tag">${{skillMap[sid]?.name||sid}}</span>`).join('')}}
          ${{(a.tools||[]).map(tid => `<span class="tool-tag">${{tid}}</span>`).join('')}}
        </div>
        ${{(a.delegates_to||[]).length ? `<div style="font-size:11px;color:#9ca3af;margin-top:4px">Delega para: ${{a.delegates_to.join(', ')}}</div>` : ''}}
      </div>`).join('');
    if (agents.length===0) document.getElementById('agentes-content').innerHTML = '<p style="color:#9ca3af">Nenhum agente carregado.</p>';
  }} catch(e) {{
    document.getElementById('agentes-content').innerHTML = `<div class="error">Erro: ${{e.message}}</div>`;
  }}
}}

async function loadSkillsList() {{
  try {{
    const skills = (await api('/admin/skills')).skills || [];
    document.getElementById('skills-list').innerHTML = skills.map(s => `
      <div style="padding:6px 0;border-bottom:1px solid #f3f4f6;font-size:13px">
        <span style="font-weight:600">${{s.name}}</span>
        <span style="color:#9ca3af;margin-left:8px">(${{s.id}})</span>
      </div>`).join('') || '<span style="color:#9ca3af">Nenhuma skill cadastrada.</span>';
  }} catch(e) {{}}
}}

var agentDataForEdit = null;

async function loadAgentSelect() {{
  try {{
    const agents = (await api('/admin/agents')).agents || [];
    const sel = document.getElementById('agent-select');
    sel.innerHTML = '<option value="">-- Novo Agente --</option>';
    agents.forEach(a => {{
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = a.name + ' (' + a.id + ')';
      sel.appendChild(opt);
    }});
    agentDataForEdit = agents;
  }} catch(e) {{}}
}}

function loadAgentForEdit() {{
  const sel = document.getElementById('agent-select');
  const id = sel.value;
  if (!id) {{ newAgentForm(); return; }}
  const agent = agentDataForEdit.find(a => a.id === id);
  if (!agent) return;
  document.getElementById('agent-id').value = agent.id || '';
  document.getElementById('agent-name').value = agent.name || '';
  document.getElementById('agent-role').value = agent.role || 'specialist';
  document.getElementById('agent-model').value = agent.model || 'deepseek-v4-flash';
  document.getElementById('agent-prompt').value = agent.system_prompt || '';
  document.getElementById('agent-skills').value = (agent.skills||[]).join(', ');
  document.getElementById('btn-delete-agent').style.display = 'inline-block';
  document.getElementById('agent-msg').innerHTML = '';
}}

function newAgentForm() {{
  document.getElementById('agent-select').value = '';
  document.getElementById('agent-id').value = '';
  document.getElementById('agent-name').value = '';
  document.getElementById('agent-role').value = 'specialist';
  document.getElementById('agent-model').value = 'deepseek-v4-flash';
  document.getElementById('agent-prompt').value = '';
  document.getElementById('agent-skills').value = '';
  document.getElementById('btn-delete-agent').style.display = 'none';
  document.getElementById('agent-msg').innerHTML = '';
}}

async function saveAgent() {{
  const body = {{
    id: document.getElementById('agent-id').value.trim(),
    name: document.getElementById('agent-name').value.trim(),
    role: document.getElementById('agent-role').value,
    model: document.getElementById('agent-model').value,
    system_prompt: document.getElementById('agent-prompt').value.trim(),
    skills: document.getElementById('agent-skills').value.split(',').map(s=>s.trim()).filter(Boolean),
    tools: [],
    instances: ['jennifer'],
    enabled: true,
    thinking: 'disabled',
  }};
  if (!body.id) {{ document.getElementById('agent-msg').innerHTML = '<span style="color:#dc2626">Preencha o ID</span>'; return; }}
  try {{
    const r = await apiPost('/admin/agents', body);
    document.getElementById('agent-msg').innerHTML = r.upserted
      ? '<span style="color:#16a34a">Agente salvo com sucesso!</span>'
      : '<span style="color:#dc2626">Falha ao salvar</span>';
  }} catch(e) {{
    document.getElementById('agent-msg').innerHTML = `<span style="color:#dc2626">Erro: ${{e.message}}</span>`;
  }}
}}

async function deleteAgent() {{
  const id = document.getElementById('agent-id').value.trim();
  if (!id) return;
  if (!confirm(`Excluir agente "${{id}}"?`)) return;
  try {{
    await apiDelete('/admin/agents/'+id);
    document.getElementById('agent-msg').innerHTML = '<span style="color:#16a34a">Agente excluído!</span>';
    newAgentForm();
    loadAgentSelect();
  }} catch(e) {{
    document.getElementById('agent-msg').innerHTML = `<span style="color:#dc2626">Erro: ${{e.message}}</span>`;
  }}
}}

async function saveSkill() {{
  const body = {{
    id: document.getElementById('skill-id').value.trim(),
    name: document.getElementById('skill-name').value.trim(),
    content: document.getElementById('skill-content').value.trim(),
  }};
  if (!body.id) {{ document.getElementById('skill-msg').innerHTML = '<span style="color:#dc2626">Preencha o ID</span>'; return; }}
  try {{
    const r = await apiPost('/admin/skills', body);
    document.getElementById('skill-msg').innerHTML = r.upserted
      ? '<span style="color:#16a34a">Skill salva!</span>'
      : '<span style="color:#dc2626">Falha ao salvar</span>';
    loadSkillsList();
  }} catch(e) {{
    document.getElementById('skill-msg').innerHTML = `<span style="color:#dc2626">Erro: ${{e.message}}</span>`;
  }}
}}

function startOAuth() {{
  const phone = document.getElementById('user-phone').value.trim();
  if (!phone) {{ document.getElementById('oauth-msg').innerHTML = '<span style="color:#dc2626">Informe seu telefone</span>'; return; }}
  if (!phone.startsWith('55')) {{ document.getElementById('oauth-msg').innerHTML = '<span style="color:#dc2626">Inclua o DDI do Brasil (55). Ex: 55119XXXXXXXX</span>'; return; }}
  if (phone.length < 10) {{ document.getElementById('oauth-msg').innerHTML = '<span style="color:#dc2626">Numero muito curto. Use DDI + DDD + numero completo</span>'; return; }}
  document.getElementById('oauth-msg').innerHTML = '<span style="color:#3b82f6">Redirecionando para o Google...</span>';
  const state = btoa(phone);
  window.location.href = '/oauth/google?state=' + encodeURIComponent(state);
}}

async function loadUsuarios() {{
  try {{
    const data = await api('/admin/users');
    const users = data.users || [];
    if (users.length===0) {{
      document.getElementById('usuarios-content').innerHTML = '<p style="color:#9ca3af;font-size:13px">Nenhum usuario cadastrado. Use o formulario acima para vincular sua conta Google.</p>';
      return;
    }}
    document.getElementById('usuarios-content').innerHTML = users.map(u => `
      <div style="padding:8px 0;border-bottom:1px solid #f3f4f6;font-size:13px;display:flex;justify-content:space-between;align-items:center">
        <div>
          <span style="font-weight:600">${{u.display_name||u.phone||'?'}}</span>
          <span style="color:#9ca3af;margin-left:8px">(${{u.phone}})</span>
        </div>
        <span style="color:${{u.google_oauth_token?'#16a34a':'#9ca3af'}};font-size:12px">${{u.google_oauth_token?'Conectado':'Pendente'}}</span>
      </div>`).join('');
  }} catch(e) {{}}
}}

async function loadMeusGrupos() {{
  const phone = document.getElementById('group-phone').value.trim();
  if (!phone) {{ document.getElementById('grupos-content').innerHTML = '<span style="color:#dc2626">Informe seu telefone</span>'; return; }}
  document.getElementById('grupos-content').innerHTML = '<span style="color:#3b82f6">Buscando...</span>';
  try {{
    const data = await api('/admin/groups?phone=' + encodeURIComponent(phone));
    const groups = data.groups || [];
    if (groups.length===0) {{
      document.getElementById('grupos-content').innerHTML = '<p style="color:#9ca3af">Voce nao esta em nenhum grupo com a Jennifer. Entre em contato pelo WhatsApp.</p>';
      return;
    }}
    document.getElementById('grupos-content').innerHTML = groups.map(g => `
      <div style="padding:10px 0;border-bottom:1px solid #f3f4f6;font-size:13px;display:flex;justify-content:space-between;align-items:center">
        <div>
          <span style="font-weight:600">${{g.name||g.group_jid}}</span>
          <span style="color:#9ca3af;margin-left:8px">(${{g.members_count||0}} membros)</span>
        </div>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px">
          <input type="checkbox" ${{g.confirmed?'checked':''}} onchange="toggleGroupConfirm('${{g.group_jid}}', '${{phone}}', this.checked)">
          Permitir acesso
        </label>
      </div>`).join('');
  }} catch(e) {{ document.getElementById('grupos-content').innerHTML = '<span style="color:#dc2626">Erro: '+e.message+'</span>'; }}
}}

async function toggleGroupConfirm(groupJid, phone, checked) {{
  try {{
    await apiPost('/admin/groups/confirm', {{group_jid: groupJid, phone: phone, confirmed: checked}});
    document.getElementById('grupos-content').innerHTML += '<div style="color:#16a34a;font-size:12px;margin-top:6px">Permissao '+(checked?'concedida':'revogada')+' com sucesso!</div>';
  }} catch(e) {{ alert('Erro: '+e.message); }}
}}

loadFluxo();
</script>
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


OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "894828119087-goo6lcl6vgm5bdq5qgafscb8qbr4ueet.apps.googleusercontent.com")
OAUTH_CLIENT_SECRET = (os.getenv("OAUTH_CLIENT_SECRET") or "").strip()
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
OAUTH_REDIRECT_URI = "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/oauth/callback"


@app.get("/oauth/google")
async def oauth_google(request: Request):
    """Redirect to Google OAuth consent screen."""
    import base64, urllib.parse
    state = request.query_params.get("state", "")
    if not state:
        raise HTTPException(status_code=422, detail="state required (base64 phone)")
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
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
    """Handle OAuth callback, exchange code for token, save to Firestore."""
    import base64, requests
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    if not code:
        return HTMLResponse(content="<h2>Erro: codigo de autorizacao nao recebido</h2>", status_code=400)

    phone = ""
    try:
        import base64
        phone = base64.b64decode(state).decode()
    except Exception:
        pass

    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15)
        tok = r.json()
        if "error" in tok:
            return HTMLResponse(content=f"<h2>Erro ao obter token: {tok.get('error')}</h2>", status_code=500)

        token_data = {
            "token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", ""),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "scopes": OAUTH_SCOPES,
            "expiry": str(__import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp() + tok.get("expires_in", 3600)),
        }
        from agent_loader import save_user
        save_user(phone or "oauth-user", {
            "phone": phone or "oauth-user",
            "google_oauth_token": token_data,
            "scopes": OAUTH_SCOPES,
            "registered_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        })
        return HTMLResponse(content=f"""
        <html><body style="font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f9fafb">
        <div style="text-align:center"><h1 style="color:#16a34a">Vinculado com sucesso! 🎉</h1>
        <p style="color:#374151">Sua conta Google foi conectada. A Jennifer ja pode acessar sua agenda e emails.</p>
        <p style="color:#9ca3af;font-size:14px">Feche esta pagina e volte ao WhatsApp.</p></div></body></html>
        """)
    except Exception as e:
        return HTMLResponse(content=f"<h2>Erro: {e}</h2>", status_code=500)