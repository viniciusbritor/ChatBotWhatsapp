"""HTML template for the ``Agentes Omnichannel`` control-plane.

Renders inside the runtime service. Authentication is performed via a
session cookie set by the server on initial page load. Tokens are never
exposed in the markup or JavaScript globals.

Template variables:
- commit: short git SHA or local placeholder
- deployed_at: timestamp or local placeholder
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict

_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Agentes Omnichannel — Coherence</title>
<style>
:root {
  color-scheme: light;
  --bg: #f6f8fb;
  --bg-elev: #ffffff;
  --fg: #0f172a;
  --fg-soft: #475569;
  --muted: #94a3b8;
  --card: #ffffff;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --accent: #1d4ed8;
  --accent-soft: #dbeafe;
  --accent-fg: #ffffff;
  --good: #16a34a;
  --good-soft: #dcfce7;
  --bad: #dc2626;
  --bad-soft: #fee2e2;
  --warn: #d97706;
  --warn-soft: #fef3c7;
  --shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 4px 16px rgba(15, 23, 42, .04);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  font-size: 14px;
  line-height: 1.5;
}
header {
  background: var(--bg-elev);
  border-bottom: 1px solid var(--border);
  padding: 18px 28px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 10;
  box-shadow: var(--shadow);
}
header h1 { font-size: 17px; font-weight: 600; letter-spacing: -0.01em; color: var(--fg); display: flex; align-items: center; gap: 10px; }
header h1::before {
  content: "";
  display: inline-block;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%);
  position: relative;
}
header h1::after {
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--accent-fg);
  border-radius: 50%;
  margin-left: -16px;
}
header .status { font-size: 12px; color: var(--fg-soft); display: flex; gap: 12px; align-items: center; }
header .status code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; background: var(--bg); padding: 2px 8px; border-radius: 6px; color: var(--fg); }
header .badge {
  background: var(--good-soft);
  color: var(--good);
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
main { padding: 28px; display: grid; grid-template-columns: 280px 1fr; gap: 24px; max-width: 1400px; margin: 0 auto; }
nav { background: var(--bg-elev); border: 1px solid var(--border); border-radius: 14px; padding: 14px; box-shadow: var(--shadow); height: fit-content; position: sticky; top: 96px; }
nav h2 { font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: .08em; font-weight: 700; margin-bottom: 10px; padding: 0 6px; }
nav button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  color: var(--fg);
  transition: background .15s ease;
  font-weight: 500;
}
nav button .icon { width: 18px; height: 18px; opacity: .65; flex-shrink: 0; }
nav button.active, nav button:hover { background: var(--accent-soft); color: var(--accent); }
nav button.active .icon { opacity: 1; }
section.panel { background: var(--bg-elev); border: 1px solid var(--border); border-radius: 14px; padding: 28px; box-shadow: var(--shadow); min-height: 600px; }
section.panel > .panel-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; gap: 16px; flex-wrap: wrap; }
section.panel h2 { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
section.panel .subtitle { font-size: 13px; color: var(--fg-soft); margin-top: 4px; }
.row { display: grid; grid-template-columns: 180px 1fr; gap: 14px; margin-bottom: 14px; align-items: start; }
.row.full { grid-template-columns: 1fr; }
.row label { font-size: 13px; color: var(--fg-soft); font-weight: 500; padding-top: 8px; }
.row input, .row textarea, .row select {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  background: var(--bg-elev);
  color: var(--fg);
  transition: border-color .15s, box-shadow .15s;
}
.row input:focus, .row textarea:focus, .row select:focus {
  outline: 0;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.row textarea { min-height: 96px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 13px; }
.actions { margin-top: 20px; display: flex; gap: 10px; flex-wrap: wrap; }
button.primary {
  background: var(--accent);
  color: var(--accent-fg);
  border: 0;
  padding: 9px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
  transition: background .15s, transform .05s;
}
button.primary:hover { background: #1740b8; }
button.primary:active { transform: scale(0.98); }
button.primary:disabled { background: var(--muted); cursor: not-allowed; }
button.secondary {
  background: var(--bg-elev);
  color: var(--fg);
  border: 1px solid var(--border-strong);
  padding: 9px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
}
button.secondary:hover { border-color: var(--accent); color: var(--accent); }
button.secondary.danger:hover { border-color: var(--bad); color: var(--bad); background: var(--bad-soft); }
button.ghost {
  background: transparent;
  color: var(--fg-soft);
  border: 0;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
}
button.ghost:hover { background: var(--bg); color: var(--accent); }
.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 10px;
  background: var(--bg-elev);
  transition: border-color .15s, box-shadow .15s, transform .05s;
}
.card:hover { border-color: var(--border-strong); box-shadow: 0 2px 8px rgba(15, 23, 42, .04); }
.card.clickable { cursor: pointer; }
.card.clickable:hover { border-color: var(--accent); }
.card .meta { font-size: 12px; color: var(--fg-soft); margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.card .actions-inline { margin-top: 12px; display: flex; gap: 8px; }
.card-title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.card h3 { font-size: 15px; font-weight: 600; color: var(--fg); }
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 500;
  margin-right: 4px;
  margin-top: 4px;
  display: inline-flex;
}
.tag.muted { background: #f1f5f9; color: var(--fg-soft); }
.tag.success { background: var(--good-soft); color: var(--good); }
.tag.warn { background: var(--warn-soft); color: var(--warn); }
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 22px; }
.kpi .card { padding: 16px; }
.kpi .card strong { font-size: 24px; display: block; font-weight: 600; letter-spacing: -0.02em; }
.kpi .card span { font-size: 12px; color: var(--fg-soft); margin-top: 2px; display: block; }
.kpi .card .sub { font-size: 11px; color: var(--muted); margin-top: 6px; }
.flash { margin-top: 12px; font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.flash.good { color: var(--good); background: var(--good-soft); }
.flash.bad { color: var(--bad); background: var(--bad-soft); }
.flash.warn { color: var(--warn); background: var(--warn-soft); }
.flash.info { color: var(--accent); background: var(--accent-soft); }
.status-row { display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--fg-soft); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); display: inline-block; }
.status-dot.ok { background: var(--good); }
.status-dot.bad { background: var(--bad); }
.status-dot.warn { background: var(--warn); }

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, .45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 100;
  animation: fadeIn .15s ease;
}
.modal {
  background: var(--bg-elev);
  border-radius: 16px;
  width: 100%;
  max-width: 720px;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .25);
  animation: pop .2s cubic-bezier(.16, 1, .3, 1);
}
.modal.wide { max-width: 920px; }
.modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.modal-header h3 { font-size: 17px; font-weight: 600; }
.modal-header .close { background: transparent; border: 0; cursor: pointer; color: var(--muted); padding: 4px 8px; border-radius: 6px; font-size: 20px; }
.modal-header .close:hover { background: var(--bg); color: var(--fg); }
.modal-body { padding: 24px; overflow-y: auto; flex: 1; }
.modal-footer { padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; }

@keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
@keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.98) } to { opacity: 1; transform: translateY(0) scale(1) } }

.chunk {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg);
}
.chunk .chunk-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 12px; color: var(--fg-soft); }
.chunk pre { white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 12.5px; color: var(--fg); max-height: 240px; overflow-y: auto; }

.empty-state { text-align: center; padding: 48px 24px; color: var(--muted); }
.empty-state p { margin-top: 8px; font-size: 13px; }
.search-bar { padding: 10px 12px; border: 1px solid var(--border-strong); border-radius: 10px; width: 100%; margin-bottom: 16px; font-size: 14px; }
.toolbar { display: flex; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar input { padding: 9px 12px; border: 1px solid var(--border-strong); border-radius: 8px; font-size: 13px; min-width: 240px; }
.json-view { background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 10px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 12px; overflow-x: auto; max-height: 460px; overflow-y: auto; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } nav { position: static; } }
</style>
</head>
<body>
<header>
  <h1>Agentes Omnichannel</h1>
  <div class="status">
    <span class="badge" id="runtime-badge">runtime</span>
    <span>commit <code id="commit-chip">__COMMIT__</code></span>
    <span>deployed <code id="deployed-chip">__DEPLOYED__</code></span>
  </div>
</header>
<main>
  <nav>
    <h2>Seções</h2>
    <button data-tab="accounts" class="active">Contas WhatsApp</button>
    <button data-tab="agents">Agentes</button>
    <button data-tab="skills">Skills</button>
    <button data-tab="tools">Tools</button>
    <button data-tab="owners">Proprietários</button>
    <button data-tab="knowledge">Conhecimento</button>
    <button data-tab="status">Status</button>
  </nav>
  <section class="panel" id="panel">
    <div id="root">Carregando…</div>
  </section>
</main>
<script>
const ENDPOINTS = {
  accounts: '/admin/accounts',
  agents: '/admin/agents',
  skills: '/admin/skills',
  tools: '/admin/tools',
  owners: '/admin/owners',
  knowledge: '/admin/knowledge',
  status: '/admin/status',
};
async function api(path, options = {}) {
  const opts = { credentials: 'include', ...options };
  opts.headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail || ''; } catch (_) {}
    throw new Error('http_' + r.status + (detail ? ' ' + detail : ''));
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));
}
function flash(el, message, kind) {
  el.innerHTML = '<div class="flash ' + kind + '">' + esc(message) + '</div>';
}
function showModal(html, onMount, extraClass) {
  const back = document.createElement('div');
  back.className = 'modal-backdrop';
  const cls = 'modal' + (extraClass ? ' ' + extraClass : '');
  back.innerHTML = '<div class="' + cls + '" role="dialog" aria-modal="true">' + html + '</div>';
  back.addEventListener('click', ev => { if (ev.target === back) closeModal(); });
  document.body.appendChild(back);
  const closer = back.querySelector('[data-close]');
  if (closer) closer.addEventListener('click', closeModal);
  if (typeof onMount === 'function') onMount(back);
  document.addEventListener('keydown', escHandler);
  function escHandler(e) { if (e.key === 'Escape') closeModal(); }
  function closeModal() { back.remove(); document.removeEventListener('keydown', escHandler); }
  return back;
}
function setActive(tab) {
  document.querySelectorAll('nav button').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tab));
  const root = document.getElementById('root');
  root.dataset.tab = tab;
  switch (tab) {
    case 'accounts': renderAccounts(root); break;
    case 'agents': renderAgents(root); break;
    case 'skills': renderSkills(root); break;
    case 'tools': renderTools(root); break;
    case 'owners': renderOwners(root); break;
    case 'knowledge': renderKnowledge(root); break;
    case 'status': renderStatus(root); break;
  }
}
async function renderAccounts(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Contas WhatsApp</h2><div class="subtitle">Instâncias Evolution conectadas ao runtime</div></div></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.accounts);
    const rows = (data.accounts || []).map(account => `
      <div class="card">
        <div class="card-title-row">
          <div>
            <h3>${esc(account.name || account.instance)}</h3>
            <div class="meta">
              <span class="tag muted">instância ${esc(account.instance)}</span>
              <span class="tag muted">+${esc(account.owner_phone || '-')}</span>
              <span class="tag ${account.status === 'active' ? 'success' : 'warn'}">${esc(account.status || '-')}</span>
            </div>
          </div>
          <button class="ghost" data-edit="${esc(account.id)}">Editar</button>
        </div>
      </div>`).join('') || '<div class="empty-state"><h3>Nenhuma conta cadastrada</h3><p>Cadastre a primeira instância WhatsApp para começar.</p></div>';
    root.innerHTML = '<div class="panel-header"><div><h2>Contas WhatsApp</h2><div class="subtitle">Instâncias Evolution conectadas ao runtime</div></div><button class="primary" id="new-account">Nova conta</button></div>' + rows;
    document.getElementById('new-account').onclick = () => editAccountForm(root);
    root.querySelectorAll('button[data-edit]').forEach(btn => btn.onclick = () => editAccountForm(root, btn.dataset.edit));
  } catch (e) {
    root.innerHTML = '<h2>Contas WhatsApp</h2><div class="empty-state"><h3>Falha ao carregar contas</h3><p>' + esc(e.message) + '</p></div>';
  }
}
async function editAccountForm(root, accountId = '') {
  let current = { instance: '', owner_phone: '', name: '', status: 'active' };
  if (accountId) {
    try {
      const resp = await api(ENDPOINTS.accounts + '/' + accountId);
      current = resp.account || current;
    } catch (_) {}
  }
  root.innerHTML = `
    <div class="panel-header"><h2>${accountId ? 'Editar conta' : 'Nova conta WhatsApp'}</h2><button class="ghost" id="cancel">Voltar</button></div>
    <div class="row"><label>Nome</label><input id="name" value="${esc(current.name)}"></div>
    <div class="row"><label>Instância Evolution</label><input id="instance" value="${esc(current.instance)}" ${accountId ? 'readonly' : ''}></div>
    <div class="row"><label>Telefone do proprietário</label><input id="owner_phone" value="${esc(current.owner_phone)}"></div>
    <div class="row"><label>Status</label><select id="status">
      <option value="active" ${current.status === 'active' ? 'selected' : ''}>Ativa</option>
      <option value="paused" ${current.status === 'paused' ? 'selected' : ''}>Pausada</option>
      <option value="archived" ${current.status === 'archived' ? 'selected' : ''}>Arquivada</option>
    </select></div>
    <div class="actions">
      <button class="primary" id="save">Salvar</button>
      <button class="secondary" id="cancel-btn">Cancelar</button>
    </div>
    <div id="account-flash"></div>`;
  const back = () => renderAccounts(root);
  root.querySelector('#cancel').onclick = back;
  root.querySelector('#cancel-btn').onclick = back;
  root.querySelector('#save').onclick = async () => {
    const body = {
      name: document.getElementById('name').value,
      instance: document.getElementById('instance').value,
      owner_phone: document.getElementById('owner_phone').value,
      status: document.getElementById('status').value,
    };
    try {
      await api(ENDPOINTS.accounts + (accountId ? '/' + accountId : ''), { method: accountId ? 'PUT' : 'POST', body: JSON.stringify(body) });
      flash(document.getElementById('account-flash'), 'Conta salva', 'good');
      setTimeout(back, 600);
    } catch (e) {
      flash(document.getElementById('account-flash'), 'Falha: ' + e.message, 'bad');
    }
  };
}
async function renderAgents(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Agentes</h2><div class="subtitle">Agentes do runtime LLM (jennifier + managers + specialists)</div></div><button class="primary" id="new-agent">Novo agente</button></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.agents);
    const inv = await api('/admin/agents/status').catch(() => ({ agents: [] }));
    const telemetry = {};
    (inv.agents || []).forEach(a => { telemetry[a.agent_id] = a; });
    const rows = (data.agents || []).map(agent => {
      const id = agent.id || agent.name;
      const tel = telemetry[id] || {};
      const status = tel.status || 'unverified';
      const dotClass = status === 'healthy' ? 'ok' : (status === 'disabled' ? 'warn' : 'bad');
      const tags = [];
      (agent.skills || []).forEach(s => tags.push('<span class="tag muted">' + esc(s) + '</span>'));
      (agent.tools || []).forEach(t => tags.push('<span class="tag">' + esc(t) + '</span>'));
      return `
      <div class="card">
        <div class="card-title-row">
          <div>
            <h3>${esc(agent.name || agent.id)} <span style="font-size:12px;color:var(--muted);font-weight:400">(${esc(id)})</span></h3>
            <div class="meta">
              <span class="status-row"><span class="status-dot ${dotClass}"></span>${esc(status)}</span>
              <span class="tag muted">${esc(agent.role || 'specialist')}</span>
              <span class="tag muted">${esc(agent.model || '-')}</span>
              ${agent.enabled === false ? '<span class="tag warn">disabled</span>' : ''}
              ${tel.in_flight ? '<span class="tag">em execução: ' + esc(tel.in_flight) + '</span>' : ''}
            </div>
            ${tags.length ? '<div class="meta">' + tags.join('') + '</div>' : ''}
          </div>
          <div class="actions-inline">
            <button class="ghost" data-edit="${esc(id)}">Editar</button>
            <button class="ghost danger" data-delete="${esc(id)}">Excluir</button>
          </div>
        </div>
      </div>`;
    }).join('') || '<div class="empty-state"><h3>Nenhum agente cadastrado</h3><p>Use “Novo agente” para registrar o primeiro.</p></div>';
    root.innerHTML = '<div class="panel-header"><div><h2>Agentes</h2><div class="subtitle">Agentes do runtime LLM (jennifier + managers + specialists)</div></div><button class="primary" id="new-agent">Novo agente</button></div>' + rows;
    document.getElementById('new-agent').onclick = () => editAgentForm(root);
    root.querySelectorAll('button[data-edit]').forEach(btn => btn.onclick = () => editAgentForm(root, btn.dataset.edit));
    root.querySelectorAll('button[data-delete]').forEach(btn => btn.onclick = () => deleteAgent(root, btn.dataset.delete));
  } catch (e) {
    root.innerHTML = '<h2>Agentes</h2><div class="empty-state"><h3>Falha ao carregar agentes</h3><p>' + esc(e.message) + '</p></div>';
  }
}
async function editAgentForm(root, agentId = '') {
  let current = {
    id: agentId || '',
    name: '',
    role: 'specialist',
    model: 'deepseek-v4-flash',
    enabled: true,
    skills: [],
    tools: [],
    instances: ['jennifer'],
    system_prompt: '',
    execution_mode: 'reactive',
  };
  if (agentId) {
    try {
      const resp = await api(ENDPOINTS.agents + '/' + agentId);
      current = Object.assign(current, resp.agent || {});
      current.skills = current.skills || [];
      current.tools = current.tools || [];
      current.instances = current.instances || ['jennifer'];
    } catch (e) {
      flash(root, 'Falha ao carregar agente: ' + e.message, 'bad');
      return;
    }
  }
  const skillsCsv = Array.isArray(current.skills) ? current.skills.join(', ') : '';
  const toolsCsv = Array.isArray(current.tools) ? current.tools.join(', ');
  const instancesCsv = Array.isArray(current.instances) ? current.instances.join(', ') : 'jennifer';
  root.innerHTML = `
    <div class="panel-header"><h2>${agentId ? 'Editar agente' : 'Novo agente'}</h2><button class="ghost" id="cancel">Voltar</button></div>
    <div class="row"><label>ID (slug)</label><input id="id" value="${esc(current.id)}" ${agentId ? 'readonly' : ''} placeholder="ex: agent-youtube"></div>
    <div class="row"><label>Nome</label><input id="name" value="${esc(current.name)}" placeholder="ex: YouTube Specialist"></div>
    <div class="row"><label>Role</label><input id="role" value="${esc(current.role)}" placeholder="orchestrator | manager | specialist | internal | worker"></div>
    <div class="row"><label>Modelo</label><input id="model" value="${esc(current.model)}" placeholder="deepseek-v4-flash"></div>
    <div class="row"><label>Instâncias</label><input id="instances" value="${esc(instancesCsv)}" placeholder="jennifer"></div>
    <div class="row"><label>Modo de execução</label><select id="execution_mode">
      <option value="reactive" ${current.execution_mode === 'reactive' ? 'selected' : ''}>Reativo</option>
      <option value="internal" ${current.execution_mode === 'internal' ? 'selected' : ''}>Interno</option>
      <option value="worker" ${current.execution_mode === 'worker' ? 'selected' : ''}>Worker</option>
    </select></div>
    <div class="row"><label>Habilitado</label><select id="enabled">
      <option value="true" ${current.enabled !== false ? 'selected' : ''}>Sim</option>
      <option value="false" ${current.enabled === false ? 'selected' : ''}>Não</option>
    </select></div>
    <div class="row"><label>Skills (separadas por vírgula)</label><input id="skills" value="${esc(skillsCsv)}"></div>
    <div class="row"><label>Tools (separadas por vírgula)</label><input id="tools" value="${esc(toolsCsv)}"></div>
    <div class="row full"><label>System prompt</label><textarea id="system_prompt" rows="6">${esc(current.system_prompt || '')}</textarea></div>
    <div class="actions">
      <button class="primary" id="save">Salvar</button>
      <button class="secondary" id="cancel-btn">Cancelar</button>
    </div>
    <div id="agent-flash"></div>`;
  const back = () => renderAgents(root);
  root.querySelector('#cancel').onclick = back;
  root.querySelector('#cancel-btn').onclick = back;
  root.querySelector('#save').onclick = async () => {
    const id = document.getElementById('id').value.trim();
    if (!id) { flash(document.getElementById('agent-flash'), 'ID é obrigatório', 'bad'); return; }
    const body = {
      id,
      name: document.getElementById('name').value.trim(),
      role: document.getElementById('role').value.trim() || 'specialist',
      model: document.getElementById('model').value.trim() || 'deepseek-v4-flash',
      instances: document.getElementById('instances').value.split(',').map(s => s.trim()).filter(Boolean),
      execution_mode: document.getElementById('execution_mode').value,
      enabled: document.getElementById('enabled').value === 'true',
      skills: document.getElementById('skills').value.split(',').map(s => s.trim()).filter(Boolean),
      tools: document.getElementById('tools').value.split(',').map(s => s.trim()).filter(Boolean),
      system_prompt: document.getElementById('system_prompt').value,
    };
    try {
      await api(ENDPOINTS.agents, { method: 'POST', body: JSON.stringify(body) });
      flash(document.getElementById('agent-flash'), 'Agente salvo', 'good');
      setTimeout(back, 600);
    } catch (e) {
      flash(document.getElementById('agent-flash'), 'Falha: ' + e.message, 'bad');
    }
  };
}
async function deleteAgent(root, agentId) {
  showModal(`
    <div class="modal-header"><h3>Excluir agente</h3><button class="close" data-close>×</button></div>
    <div class="modal-body">
      <p>Tem certeza que deseja excluir o agente <strong>${esc(agentId)}</strong>? Esta ação remove o documento da coleção <code>agents</code> no Firestore e força reload do cache.</p>
    </div>
    <div class="modal-footer">
      <button class="secondary" data-close>Cancelar</button>
      <button class="primary" id="confirm-delete" style="background:var(--bad)">Excluir definitivamente</button>
    </div>
  `, (back) => {
    back.querySelector('#confirm-delete').onclick = async () => {
      try {
        await api(ENDPOINTS.agents + '/' + agentId, { method: 'DELETE' });
        document.querySelector('[data-close]').click();
        renderAgents(root);
      } catch (e) {
        alert('Falha: ' + e.message);
      }
    };
  });
}
async function renderSkills(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Skills</h2><div class="subtitle">Snippets injetados no system prompt</div></div></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.skills);
    const rows = (data.skills || []).map(skill => `
      <div class="card">
        <div class="card-title-row">
          <div>
            <h3>${esc(skill.name || skill.id)}</h3>
            <div class="meta"><span class="tag muted">${esc(skill.id)}</span></div>
            <p style="margin-top:8px;color:var(--fg-soft);font-size:13px">${esc((skill.content || '').slice(0, 320))}${(skill.content || '').length > 320 ? '…' : ''}</p>
          </div>
        </div>
      </div>`).join('') || '<div class="empty-state"><h3>Nenhuma skill cadastrada</h3></div>';
    root.innerHTML = '<div class="panel-header"><div><h2>Skills</h2><div class="subtitle">Snippets injetados no system prompt</div></div></div>' + rows;
  } catch (e) {
    root.innerHTML = '<h2>Skills</h2><div class="empty-state"><h3>Falha ao carregar skills</h3><p>' + esc(e.message) + '</p></div>';
  }
}
async function renderTools(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Tools</h2><div class="subtitle">Catálogo (somente leitura) de tools registradas</div></div></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.tools);
    const rows = (data.tools || []).map(tool => `
      <div class="card">
        <div class="card-title-row">
          <div>
            <h3>${esc(tool.name || tool.id)}</h3>
            <div class="meta"><span class="tag muted">${esc(tool.implementation || tool.id)}</span></div>
          </div>
        </div>
      </div>`).join('') || '<div class="empty-state"><h3>Nenhuma tool cadastrada</h3></div>';
    root.innerHTML = '<div class="panel-header"><div><h2>Tools</h2><div class="subtitle">Catálogo (somente leitura) de tools registradas</div></div></div>' + rows;
  } catch (e) {
    root.innerHTML = '<h2>Tools</h2><div class="empty-state"><h3>Falha ao carregar tools</h3><p>' + esc(e.message) + '</p></div>';
  }
}
async function renderOwners(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Proprietários</h2><div class="subtitle">Donos únicos por instância (whatsapp_accounts.owner_phone)</div></div></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.owners);
    const rows = (data.owners || []).map(owner => `
      <div class="card">
        <div class="card-title-row">
          <div>
            <h3>${esc(owner.display_name || owner.owner_uid)}</h3>
            <div class="meta">
              <span class="tag muted">uid ${esc(owner.owner_uid)}</span>
              <span class="tag muted">+${esc(owner.owner_phone || '-')}</span>
              <span class="tag muted">${esc(owner.instance || '-')}</span>
            </div>
          </div>
        </div>
      </div>`).join('') || '<div class="empty-state"><h3>Nenhum proprietário cadastrado</h3></div>';
    root.innerHTML = '<div class="panel-header"><div><h2>Proprietários</h2><div class="subtitle">Donos únicos por instância (whatsapp_accounts.owner_phone)</div></div></div>' + rows;
  } catch (e) {
    root.innerHTML = '<h2>Proprietários</h2><div class="empty-state"><h3>Falha ao carregar proprietários</h3><p>' + esc(e.message) + '</p></div>';
  }
}
async function renderKnowledge(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Conhecimento</h2><div class="subtitle">Documentos indexados no Firestore Vector (Fase F4d)</div></div></div><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.knowledge + '?limit=50');
    const docs = data.documents || [];
    const renderList = (filter) => {
      const norm = (filter || '').toLowerCase();
      const filtered = norm ? docs.filter(d => (d.title || d.doc_id || '').toLowerCase().includes(norm)) : docs;
      return filtered.map(doc => `
        <div class="card clickable" data-doc="${esc(doc.doc_id)}" data-collection="${esc(doc.collection)}">
          <div class="card-title-row">
            <div>
              <h3>${esc(doc.title || doc.doc_id)}</h3>
              <div class="meta">
                <span class="tag muted">owner ${esc(doc.owner_id || '-')}</span>
                <span class="tag">${esc(doc.collection)}</span>
                <span class="status-dot ok"></span><span style="font-size:12px;color:var(--fg-soft)">clique para abrir</span>
              </div>
              <p style="margin-top:10px;color:var(--fg-soft);font-size:13px;max-height:60px;overflow:hidden">${esc((doc.text || '').slice(0, 320))}${(doc.text || '').length > 320 ? '…' : ''}</p>
            </div>
          </div>
        </div>`).join('') || '<div class="empty-state"><h3>Nenhum documento encontrado</h3></div>';
    };
    root.innerHTML = `
      <div class="panel-header"><div><h2>Conhecimento</h2><div class="subtitle">${docs.length} documentos indexados</div></div></div>
      <div class="toolbar"><input id="knowledge-search" placeholder="Buscar por título ou nome de arquivo…"></div>
      <div id="knowledge-list">${renderList('')}</div>`;
    const inp = root.querySelector('#knowledge-search');
    inp.addEventListener('input', () => {
      root.querySelector('#knowledge-list').innerHTML = renderList(inp.value);
      attachCardHandlers(root);
    });
    attachCardHandlers(root);
  } catch (e) {
    root.innerHTML = '<h2>Conhecimento</h2><div class="empty-state"><h3>Falha ao carregar base de conhecimento</h3><p>' + esc(e.message) + '</p></div>';
  }
}
function attachCardHandlers(root) {
  root.querySelectorAll('div.card[data-doc]').forEach(card => {
    card.onclick = () => viewKnowledgeDoc(card.dataset.doc, card.dataset.collection);
  });
}
async function viewKnowledgeDoc(docId, collection) {
  try {
    const resp = await api(ENDPOINTS.knowledge + '/' + encodeURIComponent(docId) + '?collection=' + encodeURIComponent(collection || ''));
    const doc = resp.document || {};
    const chunks = Array.isArray(doc.chunks) ? doc.chunks : [];
    const scores = Array.isArray(doc.scores) ? doc.scores : [];
    const tags = [];
    if (doc.collection) tags.push('<span class="tag">' + esc(doc.collection) + '</span>');
    if (doc.klass) tags.push('<span class="tag muted">' + esc(doc.klass) + '</span>');
    if (doc.group) tags.push('<span class="tag muted">' + esc(doc.group) + '</span>');
    if (doc.theme) tags.push('<span class="tag muted">' + esc(doc.theme) + '</span>');
    if (typeof doc.chunk_count === 'number') tags.push('<span class="tag muted">' + doc.chunk_count + ' chunks</span>');
    const chunksHtml = chunks.length
      ? chunks.map((c, i) => {
          const score = scores[i];
          return `<div class="chunk"><div class="chunk-head"><span>chunk ${i + 1}${score !== undefined ? ' · score ' + Number(score).toFixed(3) : ''}</span><span>${c.chars ? c.chars + ' chars' : ''}</span></div><pre>${esc(typeof c === 'string' ? c : (c.text || c.content || ''))}</pre></div>`;
        }).join('')
      : '<div class="empty-state"><h3>Sem chunks indexados</h3><p>Documento cadastrado sem conteúdo embutido.</p></div>';
    showModal(`
      <div class="modal-header"><div><h3>${esc(doc.title || docId)}</h3><div class="meta" style="margin-top:6px;font-size:12px;color:var(--fg-soft)">${esc(docId)} · ${esc(doc.owner_id || '-')}</div></div><button class="close" data-close>×</button></div>
      <div class="modal-body">
        <div class="meta" style="margin-bottom:16px">${tags.join(' ') || '<span class="tag muted">sem metadados</span>'}</div>
        <div>${chunksHtml}</div>
      </div>
      <div class="modal-footer">
        <button class="secondary" data-close>Fechar</button>
      </div>
    `, null, 'wide');
  } catch (e) {
    showModal(`
      <div class="modal-header"><h3>Erro</h3><button class="close" data-close>×</button></div>
      <div class="modal-body"><div class="flash bad">' + esc(e.message) + '</div></div>
      <div class="modal-footer"><button class="secondary" data-close>Fechar</button></div>
    `);
  }
}
async function renderStatus(root) {
  root.innerHTML = '<div class="panel-header"><div><h2>Status operacional</h2><div class="subtitle">KPIs do runtime e da stack LLM/STT</div></div></div><div id="kpi">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.status);
    const kpis = (data.kpis || []).map(kpi => `<div class="card"><strong>${esc(kpi.value)}</strong><span>${esc(kpi.label)}</span>${kpi.sub ? '<div class="sub">' + esc(kpi.sub) + '</div>' : ''}</div>`).join('');
    const sections = [];
    if (data.llm) sections.push('<div><h3 style="font-size:14px;margin:16px 0 8px">LLM</h3><pre class="json-view">' + esc(JSON.stringify(data.llm, null, 2)) + '</pre></div>');
    if (data.stt) sections.push('<div><h3 style="font-size:14px;margin:16px 0 8px">STT</h3><pre class="json-view">' + esc(JSON.stringify(data.stt, null, 2)) + '</pre></div>');
    if (data.agents_summary) sections.push('<div><h3 style="font-size:14px;margin:16px 0 8px">Agentes</h3><pre class="json-view">' + esc(JSON.stringify(data.agents_summary, null, 2)) + '</pre></div>');
    root.innerHTML = '<div class="panel-header"><div><h2>Status operacional</h2><div class="subtitle">KPIs do runtime e da stack LLM/STT</div></div></div><div class="kpi">' + kpis + '</div>' + sections.join('');
  } catch (e) {
    root.innerHTML = '<h2>Status operacional</h2><div class="empty-state"><h3>Falha ao carregar status</h3><p>' + esc(e.message) + '</p></div>';
  }
}
(async () => {
  try {
    const s = await api(ENDPOINTS.status);
    const badge = document.getElementById('runtime-badge');
    if (badge && s && s.runtime_ok) {
      badge.textContent = 'runtime OK';
      badge.style.background = 'var(--good-soft)';
      badge.style.color = 'var(--good)';
    } else if (badge) {
      badge.textContent = 'runtime off';
      badge.style.background = 'var(--bad-soft)';
      badge.style.color = 'var(--bad)';
    }
  } catch (_) {}
})();
document.querySelectorAll('nav button').forEach(btn => btn.addEventListener('click', () => setActive(btn.dataset.tab)));
setActive('accounts');
</script>
</body>
</html>
"""


def render_dashboard(commit: str, deployed_at: str) -> str:
    payload = {
        "commit": html.escape(commit or "local"),
        "deployed": html.escape(deployed_at or "-"),
    }
    return (
        _TEMPLATE
        .replace("__COMMIT__", payload["commit"])
        .replace("__DEPLOYED__", payload["deployed"])
    )


__all__ = ["render_dashboard"]


def _json_default(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def jsonify(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)
