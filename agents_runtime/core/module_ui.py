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
  --bg: #f7f9fc;
  --fg: #1f2937;
  --card: #ffffff;
  --border: #e5e7eb;
  --accent: #1d4ed8;
  --muted: #6b7280;
  --good: #16a34a;
  --bad: #dc2626;
  --warn: #d97706;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; background: var(--bg); color: var(--fg); min-height: 100vh; }
header { background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
header h1 { font-size: 18px; font-weight: 600; }
header .status { font-size: 12px; color: var(--muted); }
main { padding: 24px; display: grid; grid-template-columns: 320px 1fr; gap: 24px; }
nav { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
nav h2 { font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: .04em; margin-bottom: 12px; }
nav button { display: block; width: 100%; text-align: left; background: transparent; border: 0; padding: 10px 12px; border-radius: 8px; font-size: 14px; cursor: pointer; color: var(--fg); }
nav button.active, nav button:hover { background: #eef2ff; color: var(--accent); }
section.panel { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
section.panel h2 { font-size: 16px; margin-bottom: 16px; }
.row { display: grid; grid-template-columns: 200px 1fr; gap: 12px; margin-bottom: 12px; align-items: center; }
.row label { font-size: 13px; color: var(--muted); }
.row input, .row textarea, .row select { width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; font-family: inherit; }
.row textarea { min-height: 96px; }
.actions { margin-top: 16px; display: flex; gap: 12px; }
button.primary { background: var(--accent); color: #fff; border: 0; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-weight: 500; }
button.secondary { background: transparent; color: var(--accent); border: 1px solid var(--accent); padding: 10px 16px; border-radius: 8px; cursor: pointer; font-weight: 500; }
.card { border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-bottom: 8px; }
.card .meta { font-size: 12px; color: var(--muted); margin-top: 4px; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e0f2fe; color: #075985; font-size: 11px; margin-right: 6px; }
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi .card { padding: 12px; }
.kpi .card strong { font-size: 22px; display: block; }
.kpi .card span { font-size: 12px; color: var(--muted); }
.flash { margin-top: 8px; font-size: 13px; }
.flash.good { color: var(--good); }
.flash.bad { color: var(--bad); }
.flash.warn { color: var(--warn); }
</style>
</head>
<body>
<header>
  <h1>Agentes Omnichannel</h1>
  <div class="status">commit <code>__COMMIT__</code> · deployed __DEPLOYED__</div>
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
  const r = await fetch(path, { ...options, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (!r.ok) throw new Error('http_' + r.status);
  return r.json();
}
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));
}
function flash(el, message, kind) {
  el.innerHTML = '<div class="flash ' + kind + '">' + esc(message) + '</div>';
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
  root.innerHTML = '<h2>Contas WhatsApp</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.accounts);
    const rows = (data.accounts || []).map(account => `
      <div class="card">
        <strong>${esc(account.name || account.instance)}</strong>
        <div class="meta">instância ${esc(account.instance)} · proprietário ${esc(account.owner_phone)}</div>
        <div class="actions">
          <button class="secondary" data-edit="${esc(account.id)}">Editar</button>
        </div>
      </div>`).join('') || '<p>Nenhuma conta cadastrada.</p>';
    root.innerHTML = '<h2>Contas WhatsApp</h2>' + rows + '<button class="primary" id="new-account">Nova conta</button>';
    document.getElementById('new-account').onclick = () => editAccountForm(root);
    document.querySelectorAll('button[data-edit]').forEach(btn => btn.onclick = () => editAccountForm(root, btn.dataset.edit));
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar contas.</p>';
  }
}
async function editAccountForm(root, accountId = '') {
  const current = accountId ? (await api(ENDPOINTS.accounts + '/' + accountId)).account : { instance: '', owner_phone: '', name: '', status: 'active' };
  root.innerHTML = `
    <h2>${accountId ? 'Editar' : 'Nova'} conta WhatsApp</h2>
    <div class="row"><label>Nome</label><input id="name" value="${esc(current.name)}"></div>
    <div class="row"><label>Instância Evolution</label><input id="instance" value="${esc(current.instance)}"></div>
    <div class="row"><label>Telefone do proprietário</label><input id="owner_phone" value="${esc(current.owner_phone)}"></div>
    <div class="row"><label>Status</label><select id="status">
      <option value="active" ${current.status === 'active' ? 'selected' : ''}>Ativa</option>
      <option value="paused" ${current.status === 'paused' ? 'selected' : ''}>Pausada</option>
      <option value="archived" ${current.status === 'archived' ? 'selected' : ''}>Arquivada</option>
    </select></div>
    <div class="actions">
      <button class="primary" id="save">Salvar</button>
      <button class="secondary" id="cancel">Cancelar</button>
    </div>
    <div id="account-flash"></div>`;
  document.getElementById('cancel').onclick = () => renderAccounts(root);
  document.getElementById('save').onclick = async () => {
    const body = {
      name: document.getElementById('name').value,
      instance: document.getElementById('instance').value,
      owner_phone: document.getElementById('owner_phone').value,
      status: document.getElementById('status').value,
    };
    try {
      await api(ENDPOINTS.accounts + (accountId ? '/' + accountId : ''), { method: accountId ? 'PUT' : 'POST', body: JSON.stringify(body) });
      flash(document.getElementById('account-flash'), 'Conta salva', 'good');
      renderAccounts(root);
    } catch (e) {
      flash(document.getElementById('account-flash'), 'Falha ao salvar', 'bad');
    }
  };
}
async function renderAgents(root) {
  root.innerHTML = '<h2>Agentes</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.agents);
    const rows = (data.agents || []).map(agent => `
      <div class="card">
        <strong>${esc(agent.name || agent.id)}</strong>
        <div class="meta">${esc(agent.role)} · modelo ${esc(agent.model)}</div>
        ${(agent.skills || []).map(s => '<span class="tag">' + esc(s) + '</span>').join('')}
        ${(agent.tools || []).map(t => '<span class="tag">' + esc(t) + '</span>').join('')}
      </div>`).join('') || '<p>Nenhum agente cadastrado.</p>';
    root.innerHTML = '<h2>Agentes</h2>' + rows;
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar agentes.</p>';
  }
}
async function renderSkills(root) {
  root.innerHTML = '<h2>Skills</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.skills);
    const rows = (data.skills || []).map(skill => `
      <div class="card">
        <strong>${esc(skill.name || skill.id)}</strong>
        <div class="meta">${esc(skill.id)}</div>
        <p>${esc((skill.content || '').slice(0, 240))}${(skill.content || '').length > 240 ? '…' : ''}</p>
      </div>`).join('') || '<p>Nenhuma skill cadastrada.</p>';
    root.innerHTML = '<h2>Skills</h2>' + rows;
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar skills.</p>';
  }
}
async function renderTools(root) {
  root.innerHTML = '<h2>Tools</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.tools);
    const rows = (data.tools || []).map(tool => `
      <div class="card">
        <strong>${esc(tool.name || tool.id)}</strong>
        <div class="meta">${esc(tool.implementation || tool.id)}</div>
      </div>`).join('') || '<p>Nenhuma tool cadastrada.</p>';
    root.innerHTML = '<h2>Tools (somente leitura)</h2>' + rows;
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar tools.</p>';
  }
}
async function renderOwners(root) {
  root.innerHTML = '<h2>Proprietários</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.owners);
    const rows = (data.owners || []).map(owner => `
      <div class="card">
        <strong>${esc(owner.display_name || owner.owner_uid)}</strong>
        <div class="meta">uid ${esc(owner.owner_uid)} · telefone ${esc(owner.owner_phone)}</div>
      </div>`).join('') || '<p>Nenhum proprietário cadastrado.</p>';
    root.innerHTML = '<h2>Proprietários</h2>' + rows;
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar proprietários.</p>';
  }
}
async function renderKnowledge(root) {
  root.innerHTML = '<h2>Conhecimento</h2><div id="list">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.knowledge + '?limit=10');
    const rows = (data.documents || []).map(doc => `
      <div class="card">
        <strong>${esc(doc.title || doc.doc_id)}</strong>
        <div class="meta">owner ${esc(doc.owner_id || '-')} · ${esc(doc.collection)}</div>
        <p>${esc((doc.text || '').slice(0, 240))}${(doc.text || '').length > 240 ? '…' : ''}</p>
      </div>`).join('') || '<p>Nenhum documento indexado.</p>';
    root.innerHTML = '<h2>Conhecimento</h2>' + rows;
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar base de conhecimento.</p>';
  }
}
async function renderStatus(root) {
  root.innerHTML = '<h2>Status operacional</h2><div id="kpi">Carregando…</div>';
  try {
    const data = await api(ENDPOINTS.status);
    const kpis = (data.kpis || []).map(kpi => `<div class="card"><strong>${esc(kpi.value)}</strong><span>${esc(kpi.label)}</span></div>`).join('');
    root.innerHTML = '<h2>Status operacional</h2><div class="kpi">' + kpis + '</div><pre>' + esc(JSON.stringify(data, null, 2)) + '</pre>';
  } catch (e) {
    root.innerHTML = '<p>Falha ao carregar status.</p>';
  }
}
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
