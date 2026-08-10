"""HTML template for the ``Agentes Omnichannel`` control-plane.

Visual: light, white, clean. Sem dark mode. Identidade visual Coherence
aplicada apenas como acento secundario (jade #1A6B52) sobre palette
neutra: branco #ffffff, cinzas 50-900, accent blue #1d4ed8.

Renders dentro do runtime em `/admin/dashboard`. Auth via cookie
``session_token`` (setado pelo servidor na primeira navegação). Nunca
expor tokens em markup JavaScript.

Template variables:
- commit: short git SHA ou placeholder
- deployed_at: timestamp ou placeholder
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict


_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>Agentes Omnichannel — Coherence</title>
<style>
:root {
  color-scheme: light;
  /* Neutrals */
  --bg: #fafbfc;
  --surface: #ffffff;
  --surface-alt: #f7f8fa;
  --border: #e5e7eb;
  --border-strong: #d1d5db;
  --fg: #111827;
  --fg-soft: #4b5563;
  --fg-muted: #9ca3af;
  /* Accents */
  --accent: #1d4ed8;
  --accent-hover: #1740b8;
  --accent-soft: #eff6ff;
  --jade: #1a6b52;
  --amber: #b8962a;
  /* Semantic */
  --good: #16a34a;
  --good-soft: #f0fdf4;
  --bad: #dc2626;
  --bad-soft: #fef2f2;
  --warn: #d97706;
  --warn-soft: #fffbeb;
  /* Effects */
  --shadow-sm: 0 1px 2px rgba(17, 24, 39, .04);
  --shadow-md: 0 1px 2px rgba(17, 24, 39, .04), 0 4px 12px rgba(17, 24, 39, .06);
  --shadow-lg: 0 8px 24px rgba(17, 24, 39, .10);
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 16px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter,
               Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  line-height: 1.55;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
button { font: inherit; cursor: pointer; }

/* Skeleton */
@keyframes skel {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(
    90deg,
    rgba(0, 0, 0, .04) 25%,
    rgba(0, 0, 0, .08) 50%,
    rgba(0, 0, 0, .04) 75%
  );
  background-size: 200% 100%;
  animation: skel 1.4s ease infinite;
  border-radius: var(--radius-sm);
}
.skeleton-line { height: 12px; margin: 8px 0; }
.skeleton-card { height: 88px; margin-bottom: 10px; }

/* Header */
header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 14px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 10;
  box-shadow: var(--shadow-sm);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.01em;
}
.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: linear-gradient(135deg, #1d4ed8 0%, #1a6b52 100%);
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: -0.02em;
}
.brand small { font-weight: 400; color: var(--fg-soft); margin-left: 4px; font-size: 12px; }
.runtime-info { display: flex; gap: 14px; align-items: center; font-size: 12px; color: var(--fg-soft); }
.runtime-info code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--surface-alt);
  padding: 3px 9px;
  border-radius: var(--radius-sm);
  font-size: 11.5px;
  color: var(--fg);
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--good-soft);
  color: var(--good);
}
.badge::before {
  content: "";
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--good);
  box-shadow: 0 0 0 3px rgba(22, 163, 74, .15);
}
.badge.off { background: var(--bad-soft); color: var(--bad); }
.badge.off::before { background: var(--bad); box-shadow: 0 0 0 3px rgba(220, 38, 38, .15); }

/* Layout */
main {
  max-width: 1280px;
  margin: 24px auto;
  padding: 0 24px;
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 24px;
}
nav {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px;
  height: fit-content;
  position: sticky;
  top: 80px;
  box-shadow: var(--shadow-sm);
}
nav h2 {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--fg-muted);
  letter-spacing: 0.08em;
  font-weight: 700;
  margin-bottom: 8px;
  padding: 0 8px;
}
nav button {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  padding: 8px 10px;
  border-radius: var(--radius);
  font-size: 13.5px;
  color: var(--fg-soft);
  cursor: pointer;
  transition: background .12s, color .12s;
  font-weight: 500;
  border-left: 2px solid transparent;
  margin-left: -2px;
}
nav button:hover { background: var(--surface-alt); color: var(--fg); }
nav button.active {
  background: var(--accent-soft);
  color: var(--accent);
  border-left-color: var(--accent);
  font-weight: 600;
}
nav button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

/* Panel */
section.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px 28px 32px;
  box-shadow: var(--shadow-sm);
  min-height: 540px;
}
section.panel > .panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 14px;
  padding-bottom: 18px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
section.panel h2 {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--fg);
}
section.panel .subtitle {
  font-size: 13px;
  color: var(--fg-soft);
  margin-top: 4px;
}

/* Cards */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 10px;
  transition: border-color .12s, box-shadow .12s;
}
.card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}
.card.clickable { cursor: pointer; }
.card.clickable:hover { border-color: var(--accent); }
.card.muted { background: var(--surface-alt); border-color: transparent; }
.card .meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--fg-soft);
}
.card .meta-row + .meta-row { margin-top: 6px; }
.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}
.card h3 { font-size: 15px; font-weight: 600; color: var(--fg); }
.card p {
  margin-top: 8px;
  font-size: 13px;
  color: var(--fg-soft);
  line-height: 1.55;
}
.actions-inline { display: flex; gap: 6px; margin-top: 10px; }

/* Tags */
.tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--surface-alt);
  color: var(--fg-soft);
  font-size: 11.5px;
  font-weight: 500;
}
.tag.accent { background: var(--accent-soft); color: var(--accent); }
.tag.good { background: var(--good-soft); color: var(--good); }
.tag.warn { background: var(--warn-soft); color: var(--warn); }
.tag.bad { background: var(--bad-soft); color: var(--bad); }
.tag.jade { background: rgba(26, 107, 82, .1); color: var(--jade); }

/* Toolbar */
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.toolbar input {
  padding: 8px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface);
  font-size: 13.5px;
  flex: 1;
  min-width: 200px;
}
.toolbar input:focus {
  outline: 0;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

/* Buttons */
button.primary {
  background: var(--accent);
  color: #fff;
  border: 0;
  padding: 9px 16px;
  border-radius: var(--radius);
  font-weight: 500;
  font-size: 13.5px;
  transition: background .12s;
}
button.primary:hover { background: var(--accent-hover); }
button.primary:disabled { background: var(--fg-muted); cursor: not-allowed; }
button.secondary {
  background: var(--surface);
  color: var(--fg);
  border: 1px solid var(--border-strong);
  padding: 8px 14px;
  border-radius: var(--radius);
  font-weight: 500;
  font-size: 13.5px;
  transition: border-color .12s, color .12s;
}
button.secondary:hover { border-color: var(--accent); color: var(--accent); }
button.secondary.danger:hover { border-color: var(--bad); color: var(--bad); background: var(--bad-soft); }
button.ghost {
  background: transparent;
  color: var(--fg-soft);
  border: 0;
  padding: 5px 9px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  font-weight: 500;
}
button.ghost:hover { background: var(--surface-alt); color: var(--accent); }
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* KPI grid */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.kpi {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  transition: border-color .12s, box-shadow .12s;
}
.kpi:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}
.kpi-value {
  font-size: 22px;
  font-weight: 600;
  color: var(--fg);
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.kpi-label {
  font-size: 12px;
  color: var(--fg-soft);
  margin-top: 3px;
  font-weight: 500;
}
.kpi-sub {
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 6px;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 56px 24px;
  color: var(--fg-muted);
}
.empty-state svg { margin-bottom: 12px; }
.empty-state h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--fg-soft);
  margin-top: 10px;
}
.empty-state p {
  font-size: 13px;
  color: var(--fg-muted);
  margin-top: 6px;
  max-width: 380px;
  margin-left: auto;
  margin-right: auto;
}
.empty-state button { margin-top: 18px; }

/* Forms (drawer) */
.field-row {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.field-row label {
  font-size: 13px;
  color: var(--fg);
  font-weight: 500;
  padding-top: 9px;
}
.field-row input,
.field-row textarea,
.field-row select {
  width: 100%;
  padding: 9px 11px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface);
  font-family: inherit;
  font-size: 13.5px;
  color: var(--fg);
  transition: border-color .12s, box-shadow .12s;
}
.field-row textarea { min-height: 96px; resize: vertical; line-height: 1.55; }
.field-row textarea.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}
.field-row input:focus,
.field-row textarea:focus,
.field-row select:focus {
  outline: 0;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.field-row.full { grid-template-columns: 1fr; }
.field-row .hint {
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 4px;
}

/* Drawer (slide-in panel for editing) */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, .30);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  z-index: 90;
  animation: fadein .15s ease;
}
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 480px;
  max-width: 96vw;
  background: var(--surface);
  box-shadow: -8px 0 24px rgba(17, 24, 39, .12);
  z-index: 100;
  display: flex;
  flex-direction: column;
  animation: slidein .22s cubic-bezier(.16, 1, .3, 1);
}
.drawer-head {
  padding: 18px 22px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.drawer-head h3 {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.drawer-head button.close {
  background: transparent;
  border: 0;
  font-size: 20px;
  color: var(--fg-muted);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  line-height: 1;
}
.drawer-head button.close:hover { background: var(--surface-alt); color: var(--fg); }
.drawer-body { flex: 1; overflow-y: auto; padding: 22px; }
.drawer-foot {
  padding: 14px 22px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
@keyframes fadein { from { opacity: 0 } to { opacity: 1 } }
@keyframes slidein { from { transform: translateX(100%); } to { transform: translateX(0) } }

/* Status dot */
.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.status-dot.ok { background: var(--good); box-shadow: 0 0 0 3px rgba(22, 163, 74, .15); }
.status-dot.bad { background: var(--bad); box-shadow: 0 0 0 3px rgba(220, 38, 38, .15); }
.status-dot.warn { background: var(--warn); box-shadow: 0 0 0 3px rgba(217, 119, 6, .15); }
.status-dot.idle { background: var(--fg-muted); }

/* Toast */
.toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 200;
  max-width: 360px;
}
.toast {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius);
  padding: 10px 14px;
  box-shadow: var(--shadow-md);
  font-size: 13px;
  animation: toast-in .2s ease;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.toast.good { border-left-color: var(--good); }
.toast.bad { border-left-color: var(--bad); }
.toast.warn { border-left-color: var(--warn); }
.toast button {
  background: transparent;
  border: 0;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 0 4px;
  margin-left: auto;
}
@keyframes toast-in {
  from { opacity: 0; transform: translateX(40%); }
  to { opacity: 1; transform: translateX(0); }
}

/* Chunk viewer */
.chunk {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--surface-alt);
}
.chunk-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--fg-soft);
  font-weight: 500;
}
.chunk pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  color: var(--fg);
  line-height: 1.55;
  max-height: 240px;
  overflow-y: auto;
  margin: 0;
}

/* Empty filter / no results banner */
.inline-banner {
  background: var(--warn-soft);
  border: 1px solid #fde68a;
  border-radius: var(--radius);
  padding: 12px 14px;
  color: #92400e;
  font-size: 13px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* JSON viewer (status page) */
pre.json-view {
  background: #f8fafc;
  color: #0f172a;
  padding: 14px 16px;
  border-radius: var(--radius);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  border: 1px solid var(--border);
  overflow-x: auto;
  max-height: 360px;
  overflow-y: auto;
  margin: 8px 0 16px;
}

/* Responsive */
@media (max-width: 960px) {
  main { grid-template-columns: 1fr; padding: 0 16px; }
  nav { position: static; }
  header { padding: 12px 16px; }
  .drawer { width: 100vw; }
}
@media (max-width: 600px) {
  .runtime-info { display: none; }
  .brand small { display: none; }
  section.panel { padding: 18px; }
}

/* Accessibility: visible focus styles */
:focus-visible { outline-offset: 2px; }

/* Hidden but screen-readers */
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0;
  margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap;
  border: 0;
}
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="brand-mark">C</div>
    <div>Agentes Omnichannel <small>· Coherence</small></div>
  </div>
  <div class="runtime-info">
    <span class="badge" id="runtime-badge" aria-live="polite">runtime</span>
    <span>commit <code id="commit-chip">__COMMIT__</code></span>
    <span>deployed <code id="deployed-chip">__DEPLOYED__</code></span>
  </div>
</header>
<main>
  <nav aria-label="Seções do módulo">
    <h2>Seções</h2>
    <button data-tab="accounts" class="active">Contas WhatsApp</button>
    <button data-tab="agents">Agentes</button>
    <button data-tab="skills">Skills</button>
    <button data-tab="tools">Tools</button>
    <button data-tab="owners">Proprietários</button>
    <button data-tab="conexoes">Conexões</button>
    <button data-tab="knowledge">Conhecimento</button>
    <button data-tab="status">Status</button>
  </nav>
  <section class="panel" id="panel" role="region" aria-live="polite">
    <div id="root"></div>
  </section>
</main>
<div id="toast-stack" class="toast-stack" aria-live="polite"></div>
<script>
const ENDPOINTS = {
  accounts: '/admin/accounts',
  agents: '/admin/agents',
  skills: '/admin/skills',
  tools: '/admin/tools',
  owners: '/admin/owners',
  knowledge: '/admin/knowledge',
  knowledgeDoc: id => '/admin/knowledge/' + encodeURIComponent(id),
  status: '/admin/status',
  ping: '/admin/ping',
  users: '/admin/users',
  user: phone => '/admin/users/' + encodeURIComponent(phone),
  composioStatus: phone => '/api/v1/composio/status?phone=' + encodeURIComponent(phone),
  composioAuthorize: '/api/v1/composio/authorize',
};
const TOAST_TIMEOUT_MS = 5000;

/* ---- Toasts ---- */
function toast(message, kind) {
  const stack = document.getElementById('toast-stack');
  if (!stack) return;
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || 'info');
  el.innerHTML = '<span>' + esc(message) + '</span><button aria-label="Fechar">×</button>';
  el.querySelector('button').onclick = () => el.remove();
  stack.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }, TOAST_TIMEOUT_MS);
}

/* ---- API helper com timeout ---- */
async function api(path, options) {
  options = options || {};
  const ctrl = new AbortController();
  const timeoutId = setTimeout(() => ctrl.abort(), 12000);
  try {
    const opts = { credentials: 'include', signal: ctrl.signal, ...options };
    opts.headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    const r = await fetch(path, opts);
    clearTimeout(timeoutId);
    if (!r.ok) {
      let detail = '';
      try { detail = ((await r.json()).detail || ''); } catch (_) {}
      throw new Error('http_' + r.status + (detail ? ' ' + detail : ''));
    }
    const ct = r.headers.get('content-type') || '';
    return ct.includes('json') ? r.json() : r.text();
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === 'AbortError') throw new Error('timeout_apos_12s');
    throw e;
  }
}

/* ---- Escape ---- */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

/* ---- Empty state SVG ---- */
function emptyState(title, desc, ctaLabel, ctaHref) {
  const svg = '<svg width="80" height="56" viewBox="0 0 80 56" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    + '<rect x="6" y="10" width="68" height="40" rx="6" stroke="#cbd5e1" stroke-width="1.5" fill="#fff"/>'
    + '<line x1="14" y1="22" x2="56" y2="22" stroke="#e5e7eb" stroke-width="2" stroke-linecap="round"/>'
    + '<line x1="14" y1="30" x2="48" y2="30" stroke="#e5e7eb" stroke-width="2" stroke-linecap="round"/>'
    + '<line x1="14" y1="38" x2="42" y2="38" stroke="#e5e7eb" stroke-width="2" stroke-linecap="round"/>'
    + '</svg>';
  return '<div class="empty-state">' + svg
    + '<h3>' + esc(title) + '</h3>'
    + '<p>' + esc(desc) + '</p>'
    + (ctaLabel && ctaHref ? '<button class="primary" onclick="' + ctaHref + '">' + esc(ctaLabel) + '</button>' : '')
    + '</div>';
}

/* ---- Skeleton ---- */
function skeletonList(n) {
  let html = '';
  for (let i = 0; i < n; i++) {
    html += '<div class="skeleton skeleton-card"></div>';
  }
  return html;
}

/* ---- Active tab management ---- */
function setActive(tab) {
  document.querySelectorAll('nav button').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === tab)
  );
  const root = document.getElementById('root');
  root.dataset.tab = tab;
  switch (tab) {
    case 'accounts': renderAccounts(root); break;
    case 'agents':   renderAgents(root); break;
    case 'skills':   renderSkills(root); break;
    case 'tools':    renderTools(root); break;
    case 'owners':   renderOwners(root); break;
    case 'conexoes': renderConexoes(root); break;
    case 'knowledge':renderKnowledge(root); break;
    case 'status':   renderStatus(root); break;
  }
}

/* ---- Drawer ---- */
function openDrawer(title, body, onSave, saveLabel) {
  closeDrawer();
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.id = 'drawer-back';
  backdrop.onclick = (e) => { if (e.target === backdrop) closeDrawer(); };
  const drawer = document.createElement('div');
  drawer.className = 'drawer';
  drawer.setAttribute('role', 'dialog');
  drawer.setAttribute('aria-modal', 'true');
  drawer.setAttribute('aria-label', title);
  drawer.innerHTML =
    '<div class="drawer-head"><h3>' + esc(title) + '</h3>'
    + '<button class="close" aria-label="Fechar">×</button></div>'
    + '<div class="drawer-body">' + body + '</div>'
    + '<div class="drawer-foot">'
    + '<button class="secondary" data-action="cancel">Cancelar</button>'
    + '<button class="primary" data-action="save">' + esc(saveLabel || 'Salvar') + '</button>'
    + '</div>';
  drawer.querySelector('.close').onclick = closeDrawer;
  drawer.querySelector('[data-action="cancel"]').onclick = closeDrawer;
  drawer.querySelector('[data-action="save"]').onclick = () => {
    if (onSave) onSave(drawer);
  };
  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);
  document.addEventListener('keydown', drawerEscHandler);
  if (typeof onSave === 'function') {
    drawer.querySelector('input,textarea,select')?.focus();
  }
}
function drawerEscHandler(e) { if (e.key === 'Escape') closeDrawer(); }
function closeDrawer() {
  document.getElementById('drawer-back')?.remove();
  document.querySelector('.drawer')?.remove();
  document.removeEventListener('keydown', drawerEscHandler);
}

/* ============================================================
   Renderers
   ============================================================ */

function renderAccounts(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Contas WhatsApp</h2>'
    + '<div class="subtitle">Instâncias Evolution conectadas a este runtime</div></div>'
    + '<button class="primary" id="new-account">Nova conta</button>'
    + '</div><div id="list">' + skeletonList(3) + '</div>';
  api(ENDPOINTS.accounts).then(data => {
    const accounts = data.accounts || [];
    const cards = accounts.length
      ? accounts.map(a => (
          '<div class="card">'
          + '<div class="card-title-row">'
          + '<div>'
          + '<h3>' + esc(a.name || a.instance) + '</h3>'
          + '<div class="meta">'
          + '<span class="tag">instância ' + esc(a.instance) + '</span>'
          + '<span class="tag">+' + esc(a.owner_phone || '-') + '</span>'
          + '<span class="tag ' + (a.status === 'active' ? 'good' : 'warn') + '">' + esc(a.status || '-') + '</span>'
          + '</div></div>'
          + '<button class="ghost" data-edit="' + esc(a.id) + '">Editar</button>'
          + '</div></div>'
        )).join('')
      : emptyState('Nenhuma conta cadastrada',
          'Cadastre a primeira instância WhatsApp para começar a receber mensagens.',
          'Nova conta', "document.getElementById('new-account')?.click()");
    root.querySelector('#list').innerHTML = cards;
    root.querySelectorAll('button[data-edit]').forEach(b =>
      b.onclick = () => editAccountForm(b.dataset.edit));
    root.querySelector('#new-account').onclick = () => editAccountForm('');
  }).catch(e => {
    root.querySelector('#list').innerHTML = emptyState(
      'Falha ao carregar contas',
      e.message + '. Use o botão "tentar de novo" abaixo.',
      'Tentar de novo',
      'renderAccounts(document.getElementById("root"))'
    );
  });
}

function editAccountForm(accountId) {
  const card = accountId
    ? api(ENDPOINTS.accounts + '/' + accountId).then(r => r.account || {}).catch(() => ({}))
    : Promise.resolve({ instance: '', owner_phone: '', name: '', status: 'active' });
  Promise.resolve(card).then(current => {
    const body =
      '<div class="field-row"><label>Nome</label><input id="name" value="' + esc(current.name) + '"></div>'
      + '<div class="field-row"><label>Instância Evolution</label><input id="instance" value="' + esc(current.instance) + '"' + (accountId ? ' readonly' : '') + '><div class="hint">Identificador único da instância no Evolution</div></div>'
      + '<div class="field-row"><label>Telefone do proprietário</label><input id="owner_phone" value="' + esc(current.owner_phone) + '"></div>'
      + '<div class="field-row"><label>Status</label><select id="status">'
      + ['active', 'paused', 'archived'].map(s =>
          '<option value="' + s + '"' + (current.status === s ? ' selected' : '') + '>' + ({
            active: 'Ativa', paused: 'Pausada', archived: 'Arquivada'
          }[s]) + '</option>').join('')
      + '</select></div>'
      + '<div id="account-flash"></div>';
    openDrawer(accountId ? 'Editar conta' : 'Nova conta WhatsApp', body, (drawer) => {
      const payload = {
        name: drawer.querySelector('#name').value.trim(),
        instance: drawer.querySelector('#instance').value.trim(),
        owner_phone: drawer.querySelector('#owner_phone').value.trim(),
        status: drawer.querySelector('#status').value,
      };
      api(ENDPOINTS.accounts + (accountId ? '/' + accountId : ''), {
        method: accountId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      }).then(() => {
        toast('Conta salva', 'good');
        closeDrawer();
        renderAccounts(document.getElementById('root'));
      }).catch(e => {
        drawer.querySelector('#account-flash').innerHTML =
          '<div class="inline-banner">' + esc(e.message) + '</div>';
      });
    });
  });
}

function renderAgents(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Agentes</h2>'
    + '<div class="subtitle">Agentes do runtime LLM (jennifier + managers + specialists)</div></div>'
    + '<button class="primary" id="new-agent">Novo agente</button>'
    + '</div><div id="list">' + skeletonList(4) + '</div>';
  Promise.all([
    api(ENDPOINTS.agents).catch(() => ({ agents: [] })),
    api(ENDPOINTS.agents + '/status').catch(() => ({ agents: [] })),
  ]).then(([aData, sData]) => {
    const agents = aData.agents || [];
    const inv = {};
    (sData.agents || []).forEach(t => { inv[t.agent_id] = t; });
    if (!agents.length) {
      root.querySelector('#list').innerHTML = emptyState(
        'Sem agentes configurados',
        'Crie seu primeiro agente. Você pode editar jennifier e todos os managers.',
        'Novo agente', "document.getElementById('new-agent')?.click()");
      root.querySelector('#new-agent').onclick = () => editAgentForm('');
      return;
    }
    const cards = agents.map(agent => {
      const id = agent.id || agent.name;
      const t = inv[id] || {};
      const status = t.status || 'unverified';
      const dotClass = status === 'healthy' ? 'ok' : status === 'disabled' ? 'warn' : 'bad';
      const tags = [];
      (agent.skills || []).forEach(s => tags.push('<span class="tag accent">' + esc(s) + '</span>'));
      (agent.tools || []).forEach(t => tags.push('<span class="tag">' + esc(t) + '</span>'));
      return '<div class="card">'
        + '<div class="card-title-row">'
        + '<div>'
        + '<h3>' + esc(agent.name || agent.id) + ' <small style="font-size:11px;color:var(--fg-muted);font-weight:400">(' + esc(id) + ')</small></h3>'
        + '<div class="meta">'
        + '<span><span class="status-dot ' + dotClass + '"></span>' + esc(status) + '</span>'
        + '<span class="tag accent">' + esc(agent.role || 'specialist') + '</span>'
        + '<span class="tag jade">' + esc(agent.model || '-') + '</span>'
        + (agent.enabled === false ? '<span class="tag warn">disabled</span>' : '')
        + '</div>'
        + '<div class="meta">' + tags.join('') + '</div>'
        + '</div>'
        + '<div class="actions-inline">'
        + '<button class="ghost" data-edit="' + esc(id) + '">Editar</button>'
        + '<button class="ghost danger" data-delete="' + esc(id) + '">Excluir</button>'
        + '</div>'
        + '</div></div>';
    }).join('');
    root.querySelector('#list').innerHTML = cards;
    root.querySelectorAll('button[data-edit]').forEach(b =>
      b.onclick = () => editAgentForm(b.dataset.edit));
    root.querySelectorAll('button[data-delete]').forEach(b =>
      b.onclick = () => deleteAgent(b.dataset.delete));
    root.querySelector('#new-agent').onclick = () => editAgentForm('');
  }).catch(e => {
    root.querySelector('#list').innerHTML = emptyState(
      'Falha ao carregar agentes', e.message,
      'Tentar de novo', 'renderAgents(document.getElementById("root"))');
  });
}

function editAgentForm(agentId) {
  const cur = agentId
    ? api(ENDPOINTS.agents + '/' + agentId).then(r => Object.assign({
        id: '', name: '', role: 'specialist', model: 'deepseek-v4-flash',
        instances: ['jennifer'], execution_mode: 'reactive', enabled: true,
        skills: [], tools: [], system_prompt: ''
      }, r.agent || {})).catch(() => ({}))
    : Promise.resolve({
        id: '', name: '', role: 'specialist', model: 'deepseek-v4-flash',
        instances: ['jennifer'], execution_mode: 'reactive', enabled: true,
        skills: [], tools: [], system_prompt: ''
      });
  Promise.resolve(cur).then(c => {
    const skillsCsv = Array.isArray(c.skills) ? c.skills.join(', ') : '';
    const toolsCsv = Array.isArray(c.tools) ? c.tools.join(', ');
    const instCsv = Array.isArray(c.instances) ? c.instances.join(', ') : 'jennifer';
    const body =
      '<div class="field-row"><label>ID (slug)</label><input id="id" value="' + esc(c.id) + '"' + (agentId ? ' readonly' : '') + '"></div>'
      + '<div class="field-row"><label>Nome</label><input id="name" value="' + esc(c.name) + '"></div>'
      + '<div class="field-row"><label>Role</label><input id="role" value="' + esc(c.role) + '"></div>'
      + '<div class="field-row"><label>Modelo</label><input id="model" value="' + esc(c.model) + '"></div>'
      + '<div class="field-row"><label>Instâncias</label><input id="instances" value="' + esc(instCsv) + '"></div>'
      + '<div class="field-row"><label>Modo de execução</label><select id="execution_mode">'
      + ['reactive', 'internal', 'worker'].map(m =>
          '<option value="' + m + '"' + (c.execution_mode === m ? ' selected' : '') + '>'
          + { reactive: 'Reativo', internal: 'Interno', worker: 'Worker' }[m] + '</option>').join('')
      + '</select></div>'
      + '<div class="field-row"><label>Habilitado</label><select id="enabled">'
      + '<option value="true"' + (c.enabled !== false ? ' selected' : '') + '>Sim</option>'
      + '<option value="false"' + (c.enabled === false ? ' selected' : '') + '>Não</option>'
      + '</select></div>'
      + '<div class="field-row"><label>Skills (CSV)</label><input id="skills" value="' + esc(skillsCsv) + '"></div>'
      + '<div class="field-row"><label>Tools (CSV)</label><input id="tools" value="' + esc(toolsCsv) + '"></div>'
      + '<div class="field-row full"><label>System prompt</label><textarea id="system_prompt" class="mono" rows="6">' + esc(c.system_prompt || '') + '</textarea><div class="hint">Markdown permitido. Vazio = prompt default do agente.</div></div>'
      + '<div id="agent-flash"></div>';
    openDrawer(agentId ? 'Editar agente' : 'Novo agente', body, (drawer) => {
      const id = drawer.querySelector('#id').value.trim();
      if (!id) {
        drawer.querySelector('#agent-flash').innerHTML =
          '<div class="inline-banner">ID é obrigatório</div>';
        return;
      }
      const payload = {
        id,
        name: drawer.querySelector('#name').value.trim(),
        role: drawer.querySelector('#role').value.trim() || 'specialist',
        model: drawer.querySelector('#model').value.trim() || 'deepseek-v4-flash',
        instances: drawer.querySelector('#instances').value.split(',').map(s => s.trim()).filter(Boolean),
        execution_mode: drawer.querySelector('#execution_mode').value,
        enabled: drawer.querySelector('#enabled').value === 'true',
        skills: drawer.querySelector('#skills').value.split(',').map(s => s.trim()).filter(Boolean),
        tools: drawer.querySelector('#tools').value.split(',').map(s => s.trim()).filter(Boolean),
        system_prompt: drawer.querySelector('#system_prompt').value,
      };
      api(ENDPOINTS.agents, { method: 'POST', body: JSON.stringify(payload) }).then(() => {
        toast('Agente salvo', 'good');
        closeDrawer();
        renderAgents(document.getElementById('root'));
      }).catch(e => {
        drawer.querySelector('#agent-flash').innerHTML =
          '<div class="inline-banner">' + esc(e.message) + '</div>';
      });
    }, 'Salvar agente');
  });
}

function deleteAgent(agentId) {
  openDrawer('Excluir agente',
    '<p>Tem certeza que deseja excluir <strong>' + esc(agentId) + '</strong>? '
    + 'Esta ação remove o documento da coleção <code>agents</code> no Firestore e força reload do cache.</p>'
    + '<div class="inline-banner" style="margin-top:14px">Esta operação é irreversível.</div>',
    () => {
      api(ENDPOINTS.agents + '/' + agentId, { method: 'DELETE' }).then(() => {
        toast('Agente excluído', 'good');
        closeDrawer();
        renderAgents(document.getElementById('root'));
      }).catch(e => toast('Falha: ' + e.message, 'bad'));
    }, 'Excluir definitivamente');
}

function renderSkills(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Skills</h2>'
    + '<div class="subtitle">Snippets injetados no system prompt dos agentes</div></div>'
    + '</div><div id="list">' + skeletonList(3) + '</div>';
  api(ENDPOINTS.skills).then(data => {
    const skills = data.skills || [];
    const cards = skills.length
      ? skills.map(s => (
          '<div class="card"><h3>' + esc(s.name || s.id) + '</h3>'
          + '<div class="meta"><span class="tag jade">' + esc(s.id) + '</span></div>'
          + '<p>' + esc((s.content || '').slice(0, 360)) + ((s.content || '').length > 360 ? '…' : '') + '</p></div>'
        )).join('')
      : emptyState('Nenhuma skill cadastrada',
          'Use o endpoint POST /admin/skills para criar a primeira.');
    root.querySelector('#list').innerHTML = cards;
  }).catch(e => {
    root.querySelector('#list').innerHTML = emptyState(
      'Falha ao carregar skills', e.message,
      'Tentar de novo', 'renderSkills(document.getElementById("root"))');
  });
}

function renderTools(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Tools</h2>'
    + '<div class="subtitle">Catálogo (somente leitura) de tools registradas</div></div>'
    + '</div><div id="list">' + skeletonList(3) + '</div>';
  api(ENDPOINTS.tools).then(data => {
    const tools = data.tools || [];
    const cards = tools.length
      ? tools.map(t => (
          '<div class="card"><h3>' + esc(t.name || t.id) + '</h3>'
          + '<div class="meta"><span class="tag jade">' + esc(t.implementation || t.id) + '</span></div></div>'
        )).join('')
      : emptyState('Nenhuma tool registrada',
          'Tools são carregadas do tool_registry.py em tempo de execução.');
    root.querySelector('#list').innerHTML = cards;
  }).catch(e => {
    root.querySelector('#list').innerHTML = emptyState(
      'Falha ao carregar tools', e.message,
      'Tentar de novo', 'renderTools(document.getElementById("root"))');
  });
}

function renderOwners(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Proprietários</h2>'
    + '<div class="subtitle">Donos únicos por instância (whatsapp_accounts.owner_phone)</div></div>'
    + '</div><div id="list">' + skeletonList(2) + '</div>';
  api(ENDPOINTS.owners).then(data => {
    const owners = data.owners || [];
    const cards = owners.length
      ? owners.map(o => (
          '<div class="card"><h3>' + esc(o.display_name || o.owner_uid) + '</h3>'
          + '<div class="meta">'
          + '<span class="tag jade">uid ' + esc(o.owner_uid) + '</span>'
          + '<span class="tag">+' + esc(o.owner_phone || '-') + '</span>'
          + (o.instance ? '<span class="tag muted">' + esc(o.instance) + '</span>' : '')
          + '</div></div>'
        )).join('')
      : emptyState('Sem proprietários',
          'Cadastre uma conta WhatsApp primeiro.');
    root.querySelector('#list').innerHTML = cards;
  }).catch(e => {
    root.querySelector('#list').innerHTML = emptyState(
      'Falha ao carregar proprietários', e.message,
      'Tentar de novo', 'renderOwners(document.getElementById("root"))');
  });
}

function renderConexoes(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Conexões</h2>'
    + '<div class="subtitle">Serviços que a Jennifer pode acessar por você — conecte sua conta para liberar cada funcionalidade</div></div>'
    + '</div>'
    + '<div class="toolbar">'
    + '<label for="conexoes-user" style="font-size:13px;color:var(--fg-soft)">Usuário:&nbsp;</label>'
    + '<select id="conexoes-user" style="padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface)"></select>'
    + '</div>'
    + '<div id="conexoes-body">' + skeletonList(3) + '</div>';

  api(ENDPOINTS.users).then(data => {
    const users = (data.users || []);
    if (!users.length) {
      root.querySelector('#conexoes-body').innerHTML = emptyState(
        'Nenhum usuário cadastrado',
        'Quando alguém conectar uma conta via WhatsApp, o usuário aparece aqui.');
      return;
    }
    const sel = root.querySelector('#conexoes-user');
    users.forEach(u => {
      const opt = document.createElement('option');
      opt.value = u.phone || '';
      opt.textContent = '+' + (u.phone || '?');
      sel.appendChild(opt);
    });
    sel.addEventListener('change', () => loadConexoes(root, sel.value));
    loadConexoes(root, sel.value);
  }).catch(e => {
    root.querySelector('#conexoes-body').innerHTML = emptyState(
      'Falha ao carregar usuários', e.message,
      'Tentar de novo', 'renderConexoes(document.getElementById("root"))');
  });
}

function loadConexoes(root, phone) {
  if (!phone) {
    root.querySelector('#conexoes-body').innerHTML = emptyState(
      'Selecione um usuário', 'Escolha um usuário no menu acima para ver as conexões.');
    return;
  }
  const body = root.querySelector('#conexoes-body');
  body.innerHTML = skeletonList(2);
  Promise.all([
    api(ENDPOINTS.user(phone)).catch(() => null),
    api(ENDPOINTS.composioStatus(phone)).catch(() => null),
  ]).then(([userData, composioData]) => {
    const google = ((userData && (userData.user || userData)).google_oauth_token) || null;
    const hasGoogle = !!(google && google.token);
    const compApps = (composioData && composioData.apps) || {};

    const googleServices = [
      { key: 'gmail',  icon: '📧', name: 'Email (Gmail)', desc: 'Ler e enviar emails' },
      { key: 'calendar', icon: '📅', name: 'Agenda (Google Calendar)', desc: 'Ver e criar compromissos' },
      { key: 'drive',  icon: '📁', name: 'Arquivos (Google Drive)', desc: 'Buscar e ler seus documentos' },
    ];
    const compServices = [
      { key: 'linkedin',     icon: '💼', name: 'LinkedIn', desc: 'Postar e ler seu perfil' },
      { key: 'youtube',      icon: '▶️', name: 'YouTube', desc: 'Buscar vídeos' },
      { key: 'googledocs',   icon: '📝', name: 'Documentos (Google Docs)', desc: 'Criar e ler documentos' },
      { key: 'googlesheets', icon: '📊', name: 'Planilhas (Google Sheets)', desc: 'Criar e ler planilhas' },
      { key: 'github',       icon: '🐙', name: 'GitHub', desc: 'Repositórios e código' },
      { key: 'notion',       icon: '📓', name: 'Notion', desc: 'Notas e bases de dados' },
      { key: 'google_maps',  icon: '🗺️', name: 'Google Maps', desc: 'Rotas e lugares' },
      { key: 'one_drive',    icon: '☁️', name: 'OneDrive', desc: 'Arquivos na nuvem' },
    ];

    const googleCards = googleServices.map(s => {
      const on = hasGoogle;
      return '<div class="card" style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:20px">' + s.icon + '</span>'
        + '<div><h3 style="margin:0">' + s.name + '</h3>'
        + '<div class="meta" style="margin:2px 0 0">' + s.desc + '</div></div></div>'
        + (on
            ? '<span class="tag jade">● OK</span>'
            : '<button class="primary" onclick="window.open(\'/oauth/google?phone=' + encodeURIComponent(phone) + '\',\'_blank\')">🔗 Conectar</button>')
        + '</div>';
    }).join('');

    const compCards = compServices.map(s => {
      const app = compApps[s.key] || {};
      const on = app.connected;
      const statusLabel = on ? '● OK' : '○ Pendente';
      return '<div class="card" style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:20px">' + s.icon + '</span>'
        + '<div><h3 style="margin:0">' + s.name + '</h3>'
        + '<div class="meta" style="margin:2px 0 0">' + s.desc + '</div></div></div>'
        + (on
            ? '<span class="tag jade">● OK</span>'
            : '<button class="primary" data-comp-key="' + s.key + '">🔗 Conectar</button>')
        + '</div>';
    }).join('');

    body.innerHTML =
      '<div class="subtitle" style="margin:4px 0 8px;font-weight:600">Conta Google</div>'
      + googleCards
      + (hasGoogle
          ? ''
          : '<div class="inline-banner" style="margin-top:8px">Conecte sua conta Google para liberar Email, Agenda e Arquivos de uma vez.</div>')
      + '<div class="subtitle" style="margin:20px 0 8px;font-weight:600">Outros serviços</div>'
      + compCards
      + '<div id="conexoes-comp-result"></div>';

    body.querySelectorAll('[data-comp-key]').forEach(btn => {
      btn.addEventListener('click', () => connectComposioApp(root, phone, btn.dataset.compKey, btn));
    });
  }).catch(e => {
    body.innerHTML = emptyState('Falha ao carregar conexões', e.message,
      'Tentar de novo', 'loadConexoes(document.getElementById("root"), ' + JSON.stringify(phone) + ')');
  });
}

function connectComposioApp(root, phone, appKey, btn) {
  btn.disabled = true;
  btn.textContent = 'Gerando link…';
  api(ENDPOINTS.composioAuthorize, {
    method: 'POST',
    body: JSON.stringify({ phone: phone, toolkit: appKey }),
  }).then(data => {
    const links = data.links || [];
    const match = links.find(l => l.toolkit === appKey);
    const resultBox = root.querySelector('#conexoes-comp-result');
    if (match && match.connect_url) {
      resultBox.innerHTML = '<div class="card">'
        + '<h3>Autorize o app</h3>'
        + '<p style="font-size:13px;color:var(--fg-soft)">Clique no link abaixo para autorizar. O link expira em 10 minutos.</p>'
        + '<a class="primary" href="' + esc(match.connect_url) + '" target="_blank" rel="noopener" style="display:inline-block;padding:10px 14px;border-radius:8px;text-decoration:none">🔗 Abrir autorização</a>'
        + '<div class="meta" style="margin-top:8px">Depois de autorizar, volte aqui e recarregue para ver o status atualizado.</div>'
        + '</div>';
    } else {
      resultBox.innerHTML = '<div class="inline-banner" style="margin-top:8px">' + (match && match.error ? esc(match.error) : 'Link não gerado.') + '</div>';
    }
    btn.disabled = false;
    btn.textContent = '🔗 Conectar';
  }).catch(e => {
    btn.disabled = false;
    btn.textContent = '🔗 Conectar';
    toast('Erro ao gerar link: ' + e.message, 'error');
  });
}

function renderKnowledge(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Conhecimento</h2>'
    + '<div class="subtitle">Documentos indexados no Firestore Vector (Fase F4d)</div></div>'
    + '</div>'
    + '<div class="toolbar">'
    + '<input id="knowledge-search" placeholder="Filtrar por título…">'
    + '</div>'
    + '<div id="knowledge-list">' + skeletonList(3) + '</div>';
  api(ENDPOINTS.knowledge + '?limit=50').then(data => {
    const docs = data.documents || [];
    const renderList = (filter) => {
      const filtered = filter
        ? docs.filter(d => (d.title || d.doc_id || '').toLowerCase().includes(filter.toLowerCase()))
        : docs;
      return filtered.length
        ? filtered.map(d => (
            '<div class="card clickable" data-doc="' + esc(d.doc_id) + '" data-collection="' + esc(d.collection) + '">'
            + '<div class="card-title-row">'
            + '<div>'
            + '<h3>' + esc(d.title || d.doc_id) + '</h3>'
            + '<div class="meta">'
            + '<span class="tag accent">' + esc(d.collection) + '</span>'
            + (d.klass ? '<span class="tag">' + esc(d.klass) + '</span>' : '')
            + (d.group ? '<span class="tag">' + esc(d.group) + '</span>' : '')
            + '<span class="tag jade">' + (d.chunk_count || 0) + ' chunks</span>'
            + '</div>'
            + '<p style="margin-top:8px">' + esc((d.text || '').slice(0, 240)) + ((d.text || '').length > 240 ? '…' : '') + '</p>'
            + '</div></div></div>'
          )).join('')
        : emptyState('Nenhum documento', 'Nenhum documento indexado ainda.');
    };
    root.querySelector('#knowledge-list').innerHTML = renderList('');
    root.querySelector('#knowledge-search').oninput = (e) => {
      root.querySelector('#knowledge-list').innerHTML = renderList(e.target.value);
      attachKnowledgeHandlers();
    };
    attachKnowledgeHandlers();
  }).catch(e => {
    root.querySelector('#knowledge-list').innerHTML = emptyState(
      'Falha ao carregar conhecimento', e.message,
      'Tentar de novo', 'renderKnowledge(document.getElementById("root"))');
  });
}

function attachKnowledgeHandlers() {
  document.querySelectorAll('div[data-doc]').forEach(card => {
    card.onclick = () => viewKnowledgeDoc(card.dataset.doc, card.dataset.collection);
  });
}

function viewKnowledgeDoc(docId, collection) {
  api(ENDPOINTS.knowledgeDoc(docId) + '?collection=' + encodeURIComponent(collection || ''))
    .then(resp => {
      const doc = resp.document || {};
      const chunks = doc.chunks || [];
      const tags = [];
      if (doc.collection) tags.push('<span class="tag accent">' + esc(doc.collection) + '</span>');
      if (doc.klass) tags.push('<span class="tag">' + esc(doc.klass) + '</span>');
      if (doc.group) tags.push('<span class="tag">' + esc(doc.group) + '</span>');
      if (doc.theme) tags.push('<span class="tag jade">' + esc(doc.theme) + '</span>');
      if (typeof doc.chunk_count === 'number') tags.push('<span class="tag muted">' + doc.chunk_count + ' chunks</span>');
      const chunksHtml = chunks.length
        ? chunks.map((c, i) => (
            '<div class="chunk">'
            + '<div class="chunk-head">chunk ' + (i + 1) + ' / ' + chunks.length + '</div>'
            + '<pre>' + esc(typeof c === 'string' ? c : (c.text || c.content || '')) + '</pre>'
            + '</div>'
          )).join('')
        : emptyState('Sem conteúdo', 'Documento cadastrado sem texto.');
      openDrawer(doc.title || docId,
        '<div class="meta" style="margin-bottom:16px">' + tags.join(' ') + '</div>'
        + chunksHtml, null, 'Fechar');
      const saveBtn = document.querySelector('.drawer [data-action="save"]');
      if (saveBtn) saveBtn.style.display = 'none';
    }).catch(e => {
      openDrawer('Erro',
        '<div class="inline-banner">' + esc(e.message) + '</div>',
        null, 'Fechar');
      const saveBtn = document.querySelector('.drawer [data-action="save"]');
      if (saveBtn) saveBtn.style.display = 'none';
    });
}

function renderStatus(root) {
  root.innerHTML =
    '<div class="panel-header">'
    + '<div><h2>Status operacional</h2>'
    + '<div class="subtitle">KPIs do runtime e da stack LLM/STT</div></div>'
    + '</div>'
    + '<div id="kpi-grid" class="kpi-grid">' + skeletonList(6) + '</div>'
    + '<div id="sections"></div>';
  api(ENDPOINTS.status).then(data => {
    const kpis = (data.kpis || []).map(k =>
      '<div class="kpi">'
      + '<div class="kpi-value">' + esc(k.value) + '</div>'
      + '<div class="kpi-label">' + esc(k.label) + '</div>'
      + (k.sub ? '<div class="kpi-sub">' + esc(k.sub) + '</div>' : '')
      + '</div>'
    ).join('');
    root.querySelector('#kpi-grid').innerHTML = kpis || '<p>Nenhum KPI disponível</p>';
    const sections = [];
    if (data.llm) sections.push('<h3 style="font-size:14px;color:var(--fg-soft);margin:24px 0 8px;font-weight:600">LLM</h3><pre class="json-view">' + esc(JSON.stringify(data.llm, null, 2)) + '</pre>');
    if (data.stt) sections.push('<h3 style="font-size:14px;color:var(--fg-soft);margin:16px 0 8px;font-weight:600">STT</h3><pre class="json-view">' + esc(JSON.stringify(data.stt, null, 2)) + '</pre>');
    if (data.agents_summary) sections.push('<h3 style="font-size:14px;color:var(--fg-soft);margin:16px 0 8px;font-weight:600">Agentes</h3><pre class="json-view">' + esc(JSON.stringify(data.agents_summary, null, 2)) + '</pre>');
    root.querySelector('#sections').innerHTML = sections.join('');
  }).catch(e => {
    root.querySelector('#kpi-grid').innerHTML = emptyState(
      'Falha ao carregar status', e.message,
      'Tentar de novo', 'renderStatus(document.getElementById("root"))');
  });
}

/* ---- boot ---- */
(async () => {
  try {
    const s = await api(ENDPOINTS.status);
    const badge = document.getElementById('runtime-badge');
    if (badge) {
      if (s && s.runtime_ok) {
        badge.textContent = 'runtime ok';
      } else {
        badge.textContent = 'runtime off';
        badge.classList.add('off');
      }
    }
  } catch (e) {
    const badge = document.getElementById('runtime-badge');
    if (badge) {
      badge.textContent = 'runtime off';
      badge.classList.add('off');
    }
  }
})();

document.querySelectorAll('nav button').forEach(btn =>
  btn.addEventListener('click', () => setActive(btn.dataset.tab))
);
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
