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
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&amp;family=JetBrains+Mono:wght@400;600&amp;display=swap" rel="stylesheet">
<style>
:root {
  color-scheme: light;
  /* Palette — Coherence Clean Light (Google Stitch Spec) */
  --bg: #f9f9ff;
  --surface: #ffffff;
  --surface-alt: #f2f3fd;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --fg: #191b23;
  --fg-soft: #424754;
  --fg-muted: #727785;
  /* Accents — Coherence Brand */
  --accent: #0058be;
  --accent-hover: #004395;
  --accent-soft: #d8e2ff;
  --jade: #196b52;
  --jade-soft: #a3efcf;
  --amber: #924700;
  /* Semantic */
  --good: #16a34a;
  --good-soft: #f0fdf4;
  --bad: #ba1a1a;
  --bad-soft: #ffdad6;
  --warn: #d97706;
  --warn-soft: #fffbeb;
  /* Visual Effects */
  --shadow-sm: 0 1px 3px 0 rgba(25, 27, 35, 0.04);
  --shadow-md: 0 4px 6px -1px rgba(25, 27, 35, 0.06), 0 2px 4px -2px rgba(25, 27, 35, 0.04);
  --shadow-lg: 0 10px 25px -5px rgba(25, 27, 35, 0.08);
  --radius-sm: 8px;
  --radius: 12px;
  --radius-lg: 16px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  line-height: 1.5;
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
  gap: 14px;
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.01em;
  color: var(--fg);
}
.brand svg { display: block; }
.brand-divider {
  width: 1px;
  height: 24px;
  background: var(--border-strong);
}
.brand-title { font-size: 14px; font-weight: 600; color: var(--fg); }
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
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  padding: 9px 12px;
  border-radius: var(--radius);
  font-size: 13.5px;
  color: var(--fg-soft);
  cursor: pointer;
  transition: background .12s, color .12s, transform .12s;
  font-weight: 500;
}
nav button .nav-icon {
  font-size: 20px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  flex-shrink: 0;
  margin-right: 6px;
}
nav button:hover { background: var(--surface-alt); color: var(--fg); }
nav button.active {
  background: var(--accent-soft);
  color: var(--accent);
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

/* Cards & Grid */
#list, #knowledge-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}
@media (max-width: 720px) {
  #list, #knowledge-list {
    grid-template-columns: 1fr;
  }
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
  transition: border-color .15s, box-shadow .15s, transform .15s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
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
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-alt);
  color: var(--fg-soft);
  font-size: 12px;
  font-weight: 500;
  border: 1px solid transparent;
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
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  border: 0;
  padding: 10px 18px;
  border-radius: 10px;
  font-weight: 500;
  font-size: 13.5px;
  transition: box-shadow .15s, transform .15s, filter .15s;
  box-shadow: 0 1px 2px rgba(37, 99, 235, .2);
}
button.primary:hover { filter: brightness(1.05); box-shadow: 0 2px 8px rgba(37, 99, 235, .25); transform: translateY(-1px); }
button.primary:disabled { background: var(--fg-muted); cursor: not-allowed; box-shadow: none; transform: none; }
button.secondary {
  background: var(--surface);
  color: var(--fg);
  border: 1.5px solid var(--border-strong);
  padding: 9px 15px;
  border-radius: 10px;
  font-weight: 500;
  font-size: 13.5px;
  transition: border-color .12s, color .12s, background .12s;
}
button.secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
button.secondary.danger:hover { border-color: var(--bad); color: var(--bad); background: var(--bad-soft); }
button.ghost {
  background: transparent;
  color: var(--fg-soft);
  border: 0;
  padding: 6px 10px;
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

/* Card appear animation */
@keyframes card-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
#list .card, #knowledge-list .card, #conexoes-body .card {
  animation: card-in .25s ease both;
}
#list .card:nth-child(2) { animation-delay: .03s; }
#list .card:nth-child(3) { animation-delay: .06s; }
#list .card:nth-child(4) { animation-delay: .09s; }
#list .card:nth-child(5) { animation-delay: .12s; }
#list .card:nth-child(6) { animation-delay: .15s; }

/* Responsive */
@media (max-width: 960px) {
  main { grid-template-columns: 1fr; padding: 0 16px; }
  nav {
    position: static;
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding: 10px;
    scrollbar-width: thin;
  }
  nav h2 { display: none; }
  nav button { width: auto; white-space: nowrap; flex-shrink: 0; }
  header { padding: 12px 16px; }
  .drawer { width: 100vw; }
}
@media (max-width: 600px) {
  .runtime-info { display: none; }
  .brand small { display: none; }
  section.panel { padding: 18px; }
  section.panel h2 { font-size: 17px; }
  button.primary { padding: 9px 14px; }
  .card { padding: 13px 15px; }
}

/* Accessibility: visible focus styles */
:focus-visible { outline-offset: 2px; }

/* Hidden but screen-readers */
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0;
  margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap;
  border: 0;
}
.sec-title {
  font-size: 14px;
  color: var(--fg-soft);
  margin: 24px 0 8px;
  font-weight: 600;
}
.status-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.status-table th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-muted);
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.status-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--fg);
}
.status-table tr:hover td {
  background: var(--surface-alt);
}
</style>
</head>
<body>
<header>
  <div class="brand">
    <svg width="26" height="26" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="coh-g" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stop-color="#3b82f6"/>
          <stop offset="1" stop-color="#1a6b52"/>
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#coh-g)"/>
      <path d="M22 11.5a8 8 0 1 0 0 9" stroke="#fff" stroke-width="3.2" stroke-linecap="round" fill="none"/>
      <circle cx="22.5" cy="16" r="2.1" fill="#fff"/>
    </svg>
    <span class="brand-divider"></span>
    <span class="brand-title">Agentes Omnichannel <small>· Coherence</small></span>
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
    __NAV__
  </nav>
  <section class="panel" id="panel" role="region" aria-live="polite">
    <div id="root"></div>
  </section>
</main>
<div id="toast-stack" class="toast-stack" aria-live="polite"></div>
<script>
/* =====================================================
   Coherence Portal — JS limpo (rewrite 2026-08-11)
   Princípios:
   1. Token extraído UMA VEZ no boot
   2. Event delegation para cliques na nav
   3. Cada tab: skeleton → fetch → render || erro inline
   4. Erros NUNCA silenciosos — sempre visíveis no painel
   5. Sem global state que compete com innerHTML do root
===================================================== */

const CALLER_ROLE  = '__ROLE__';
const CALLER_PHONE = '__CALLER_PHONE__';

/* ---------- Token ---------- */
const _tok = (() => {
  try {
    const u = new URLSearchParams(location.search).get('token');
    if (u) { sessionStorage.setItem('_ctok', u); return u; }
    return sessionStorage.getItem('_ctok') || '';
  } catch (_) { return ''; }
})();

/* ---------- API fetch ---------- */
async function api(path, opts = {}) {
  const ctrl = new AbortController();
  const tid  = setTimeout(() => ctrl.abort(), 12000);
  const sep  = path.includes('?') ? '&' : '?';
  const url  = path + (_tok ? sep + 'token=' + encodeURIComponent(_tok) : '');
  try {
    const r = await fetch(url, {
      credentials: 'include',
      signal: ctrl.signal,
      ...opts,
      headers: {
        'Content-Type': 'application/json',
        ...(opts.headers || {}),
        ...(_tok ? { Authorization: 'Bearer ' + _tok } : {}),
      },
    });
    clearTimeout(tid);
    if (!r.ok) {
      let detail = '';
      try { detail = (await r.json()).detail || ''; } catch (_) {}
      const err = new Error(detail || 'HTTP ' + r.status);
      err.status = r.status;
      throw err;
    }
    const ct = r.headers.get('content-type') || '';
    return ct.includes('json') ? r.json() : r.text();
  } catch (e) {
    clearTimeout(tid);
    if (e.name === 'AbortError') throw new Error('Timeout após 12s');
    throw e;
  }
}

/* ---------- Helpers ---------- */
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function skel(n = 3) {
  return Array.from({ length: n }, () =>
    '<div class="skeleton skeleton-card"></div>'
  ).join('');
}

function emptyHtml(title, desc, btnLabel, btnAction) {
  const btn = btnLabel
    ? '<button class="primary" onclick="' + esc(btnAction) + '">' + esc(btnLabel) + '</button>'
    : '';
  return (
    '<div class="empty-state">'
    + '<span class="material-symbols-outlined" style="font-size:56px;color:var(--border-strong)">inbox</span>'
    + '<h3>' + esc(title) + '</h3>'
    + '<p>' + esc(desc) + '</p>'
    + btn
    + '</div>'
  );
}

function errHtml(msg, status) {
  const isAuth = status === 401 || status === 403;
  const icon   = isAuth ? 'lock' : 'error';
  const color  = isAuth ? 'var(--bad)' : 'var(--warn)';
  const extra  = isAuth
    ? '<p style="margin-top:8px"><a href="' + location.origin + '/" style="font-weight:600">Clique aqui para fazer login novamente</a></p>'
    : '';
  return (
    '<div class="empty-state">'
    + '<span class="material-symbols-outlined" style="font-size:56px;color:' + color + '">' + icon + '</span>'
    + '<h3 style="color:' + color + '">' + (isAuth ? 'Sessão expirada' : 'Erro ao carregar') + '</h3>'
    + '<p>' + esc(msg) + '</p>'
    + extra
    + '</div>'
  );
}

function panelHtml(title, subtitle, actions, body) {
  const acts = actions || '';
  const sub  = subtitle ? '<p class="subtitle">' + esc(subtitle) + '</p>' : '';
  return (
    '<div class="panel-header">'
    + '<div><h2>' + esc(title) + '</h2>' + sub + '</div>'
    + (acts ? '<div style="display:flex;gap:8px">' + acts + '</div>' : '')
    + '</div>'
    + '<div id="tab-body">' + body + '</div>'
  );
}

/* ---------- Toast ---------- */
function toast(msg, kind) {
  const stack = document.getElementById('toast-stack');
  if (!stack) return;
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.innerHTML = '<span style="flex:1">' + esc(msg) + '</span>'
    + '<button onclick="this.parentElement.remove()">✕</button>';
  stack.prepend(el);
  setTimeout(() => el.remove(), 5000);
}

/* ---------- setContent helper (safe) ---------- */
function setTabBody(html) {
  const el = document.getElementById('tab-body');
  if (el) el.innerHTML = html;
}

/* ==========================================
   TAB RENDERERS
========================================== */

/* -- Accounts -- */
function renderAccounts(root) {
  const acts = CALLER_ROLE === 'admin'
    ? '<button class="primary" onclick="accountFormNew()">+ Nova Conta</button>'
    : '';
  root.innerHTML = panelHtml('Contas WhatsApp', 'Instâncias Evolution conectadas', acts, skel(3));

  api('/admin/accounts').then(data => {
    const list = data.accounts || [];
    if (!list.length) { setTabBody(emptyHtml('Nenhuma conta', 'Nenhuma instância WhatsApp cadastrada.', 'Nova Conta', 'accountFormNew()')); return; }
    setTabBody(
      '<div id="list">'
      + list.map(a => {
        const state   = a.state || a.connection_status || a.status || 'unknown';
        const stCls   = state === 'open' ? 'ok' : state === 'connecting' ? 'warn' : 'bad';
        const owner   = a.owner_phone || a.owner || '-';
        const created = a.created_at ? new Date(a.created_at).toLocaleDateString('pt-BR') : '-';
        return (
          '<div class="card">'
          + '<div class="card-title-row"><h3>' + esc(a.instance_id || a.id || '—') + '</h3>'
          + '<span class="tag ' + stCls + '">' + esc(state) + '</span></div>'
          + '<div class="meta">'
          + '<span>Owner: <strong>' + esc(owner) + '</strong></span>'
          + '<span>Criado: ' + esc(created) + '</span>'
          + '</div>'
          + (CALLER_ROLE === 'admin'
              ? '<div class="actions-inline" style="margin-top:12px">'
                + '<button class="secondary" onclick="accountEdit(' + JSON.stringify(esc(a.instance_id || a.id)) + ')">Editar</button>'
                + '<button class="secondary danger" onclick="accountDel(' + JSON.stringify(esc(a.instance_id || a.id)) + ')">Excluir</button>'
                + '</div>'
              : '')
          + '</div>'
        );
      }).join('')
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Agents -- */
function renderAgents(root) {
  const acts = CALLER_ROLE === 'admin'
    ? '<button class="primary" onclick="agentFormNew()">+ Novo Agente</button>'
    : '';
  root.innerHTML = panelHtml('Agentes', 'Agentes de IA configurados', acts, skel(3));

  api('/admin/agents').then(data => {
    const list = data.agents || [];
    if (!list.length) { setTabBody(emptyHtml('Nenhum agente', 'Nenhum agente configurado.', CALLER_ROLE === 'admin' ? '+ Novo Agente' : null, 'agentFormNew()')); return; }
    setTabBody(
      '<div id="list">'
      + list.map(a => {
        const skills = (a.skills || []).slice(0, 3).map(s => '<span class="tag">' + esc(s) + '</span>').join('');
        const more   = (a.skills || []).length > 3 ? '<span class="tag">+' + ((a.skills.length - 3)) + '</span>' : '';
        return (
          '<div class="card">'
          + '<div class="card-title-row"><h3>' + esc(a.name || a.agent_id) + '</h3>'
          + '<span class="tag accent">' + esc(a.role || 'agent') + '</span></div>'
          + '<p>' + esc((a.description || '').substring(0, 120)) + '</p>'
          + '<div class="meta" style="margin-top:8px">' + skills + more + '</div>'
          + (CALLER_ROLE === 'admin'
              ? '<div class="actions-inline" style="margin-top:12px">'
                + '<button class="secondary" onclick="agentEdit(' + JSON.stringify(esc(a.agent_id)) + ')">Editar</button>'
                + '<button class="secondary danger" onclick="agentDel(' + JSON.stringify(esc(a.agent_id)) + ')">Excluir</button>'
                + '</div>'
              : '')
          + '</div>'
        );
      }).join('')
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Skills -- */
function renderSkills(root) {
  const acts = CALLER_ROLE === 'admin'
    ? '<button class="primary" onclick="skillFormNew()">+ Nova Skill</button>'
    : '';
  root.innerHTML = panelHtml('Skills', 'Habilidades disponíveis para os agentes', acts, skel(3));

  api('/admin/skills').then(data => {
    const list = data.skills || [];
    if (!list.length) { setTabBody(emptyHtml('Nenhuma skill', 'Nenhuma skill cadastrada.', CALLER_ROLE === 'admin' ? '+ Nova Skill' : null, 'skillFormNew()')); return; }
    setTabBody(
      '<div id="list">'
      + list.map(s => (
        '<div class="card">'
        + '<div class="card-title-row"><h3>' + esc(s.skill_id || s.name) + '</h3>'
        + (s.enabled === false ? '<span class="tag bad">desativada</span>' : '<span class="tag good">ativa</span>')
        + '</div>'
        + '<p>' + esc((s.description || '').substring(0, 120)) + '</p>'
        + (CALLER_ROLE === 'admin'
            ? '<div class="actions-inline" style="margin-top:12px">'
              + '<button class="secondary" onclick="skillEdit(' + JSON.stringify(esc(s.skill_id)) + ')">Editar</button>'
              + '<button class="secondary danger" onclick="skillDel(' + JSON.stringify(esc(s.skill_id)) + ')">Excluir</button>'
              + '</div>'
            : '')
        + '</div>'
      )).join('')
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Tools -- */
function renderTools(root) {
  const acts = CALLER_ROLE === 'admin'
    ? '<button class="primary" onclick="toolFormNew()">+ Nova Tool</button>'
    : '';
  root.innerHTML = panelHtml('Tools', 'Ferramentas registradas', acts, skel(3));

  api('/admin/tools').then(data => {
    const list = data.tools || [];
    if (!list.length) { setTabBody(emptyHtml('Nenhuma tool', 'Nenhuma tool cadastrada.', CALLER_ROLE === 'admin' ? '+ Nova Tool' : null, 'toolFormNew()')); return; }
    setTabBody(
      '<div id="list">'
      + list.map(t => (
        '<div class="card">'
        + '<div class="card-title-row"><h3>' + esc(t.tool_id || t.name) + '</h3>'
        + '<span class="tag jade">' + esc(t.type || 'tool') + '</span></div>'
        + '<p>' + esc((t.description || '').substring(0, 120)) + '</p>'
        + (CALLER_ROLE === 'admin'
            ? '<div class="actions-inline" style="margin-top:12px">'
              + '<button class="secondary" onclick="toolEdit(' + JSON.stringify(esc(t.tool_id)) + ')">Editar</button>'
              + '<button class="secondary danger" onclick="toolDel(' + JSON.stringify(esc(t.tool_id)) + ')">Excluir</button>'
              + '</div>'
            : '')
        + '</div>'
      )).join('')
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Conexões / OAuth -- */
function renderConexoes(root) {
  root.innerHTML = panelHtml('Conexões', 'Autorize o acesso do agente às suas contas', null, skel(2));

  const phone = CALLER_ROLE === 'agent_user' ? CALLER_PHONE : null;
  const endpoint = phone ? '/admin/users/' + encodeURIComponent(phone) : '/admin/users';

  api(endpoint).then(data => {
    let list = data.users || [];
    if (data.user) list = [data.user];
    else if (data.phone) list = [data];
    if (!list.length) { setTabBody(emptyHtml('Nenhum usuário', 'Nenhum usuário encontrado.')); return; }
    setTabBody(
      '<div id="list">'
      + list.map(u => {
        const hasOAuth = !!(u.google_oauth_token);
        return (
          '<div class="card">'
          + '<div class="card-title-row"><h3>' + esc(u.phone || u.id) + '</h3>'
          + '<span class="tag ' + (hasOAuth ? 'good' : 'warn') + '">'
          + (hasOAuth ? 'Google conectado' : 'Google pendente')
          + '</span></div>'
          + '<div class="meta">'
          + '<span>Composio: <strong id="composio-state-' + esc(u.phone) + '">consultando…</strong></span>'
          + (u.name ? '<span>Nome: ' + esc(u.name) + '</span>' : '')
          + '</div>'
          + '<div class="actions-inline" style="margin-top:12px">'
          + (hasOAuth
              ? '<span class="tag good">✓ OAuth Google</span>'
              : '<button class="secondary" onclick="requestOAuth(' + JSON.stringify(esc(u.phone)) + ')">Conectar Google</button>')
          + '<button class="secondary" onclick="conectarComposio(' + JSON.stringify(esc(u.phone)) + ')">Conectar Apps (Composio)</button>'
          + '</div>'
          + '</div>'
        );
      }).join('')
      + '</div>'
    );
    list.forEach(u => { if (u.phone) refreshComposioState(u.phone); });
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

function refreshComposioState(phone) {
  api('/api/v1/composio/status?phone=' + encodeURIComponent(phone))
    .then(data => {
      const el = document.getElementById('composio-state-' + escapeHtml(phone));
      if (!el) return;
      const apps = (data && data.apps) || {};
      const slugs = Object.keys(apps);
      const connected = slugs.filter(s => apps[s] && apps[s].connected).length;
      el.textContent = connected + '/' + slugs.length + ' apps conectados';
    })
    .catch(() => {
      const el = document.getElementById('composio-state-' + escapeHtml(phone));
      if (el) el.textContent = 'erro ao consultar';
    });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

async function conectarComposio(phone) {
  try {
    const res = await api('/api/v1/composio/connect-all', { method: 'POST', body: JSON.stringify({ phone: phone }) });
    const url = (res && res.url) || (res && res.connect_url) || (res && res.session && res.session.redirectUrl) || '';
    if (url) {
      toast('Abrindo conexão Composio…', '');
      window.open(url, '_blank');
    } else {
      const links = (res && res.links) || [];
      if (links.length) {
        toast('Abrindo ' + links.length + ' link(s) de conexão…', '');
        links.forEach(l => window.open(l, '_blank'));
      } else {
        toast('Nenhum app pendente ou resposta inesperada.', 'warn');
      }
    }
  } catch (e) {
    toast('Falha ao iniciar Composio: ' + e.message, 'warn');
  }
}

/* -- Permissões (agent_user) -- */
function renderPermissoes(root) {
  root.innerHTML = panelHtml('Permissões', 'Configuração de acesso aos serviços Google', null, skel(1));
  const phone = CALLER_PHONE;
  if (!phone) { setTabBody(errHtml('Sem telefone de usuário identificado.', null)); return; }
  api('/admin/users/' + encodeURIComponent(phone)).then(data => {
    const fp = data.folder_permissions || {};
    setTabBody(
      '<div class="card">'
      + '<h3>Permissões de Pasta — Google Drive</h3>'
      + '<pre class="json-view">' + esc(JSON.stringify(fp, null, 2)) + '</pre>'
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Knowledge -- */
function renderKnowledge(root) {
  const acts = CALLER_ROLE === 'admin'
    ? '<button class="primary" onclick="uploadKnowledge()">+ Upload</button>'
    : '';
  root.innerHTML = panelHtml('Conhecimento', 'Documentos na base RAG', acts, skel(3));

  api('/admin/knowledge').then(data => {
    const list = data.documents || data.items || [];
    if (!list.length) { setTabBody(emptyHtml('Base vazia', 'Nenhum documento indexado.', CALLER_ROLE === 'admin' ? '+ Upload' : null, 'uploadKnowledge()')); return; }
    setTabBody(
      '<div id="knowledge-list">'
      + list.map(d => (
        '<div class="card">'
        + '<h3>' + esc(d.source_title || d.title || d.id) + '</h3>'
        + '<div class="meta">'
        + (d.class ? '<span class="tag">' + esc(d.class) + '</span>' : '')
        + (d.group ? '<span class="tag">' + esc(d.group) + '</span>' : '')
        + (d.chunk_count ? '<span>' + d.chunk_count + ' chunks</span>' : '')
        + '</div>'
        + (CALLER_ROLE === 'admin'
            ? '<div class="actions-inline" style="margin-top:12px">'
              + '<button class="secondary danger" onclick="delKnowledge(' + JSON.stringify(esc(d.id || d.source_title)) + ')">Excluir</button>'
              + '</div>'
            : '')
        + '</div>'
      )).join('')
      + '</div>'
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

/* -- Status -- */
function renderStatus(root) {
  root.innerHTML = panelHtml('Status', 'Diagnóstico do runtime', null, skel(1));

  api('/admin/status').then(data => {
    const kpis = Array.isArray(data.kpis) ? data.kpis : _statusToKpis(data);
    const cards = kpis.map(k => (
      '<div class="kpi">'
      + '<div class="kpi-value">' + esc(k.value === null || k.value === undefined ? '—' : k.value) + '</div>'
      + '<div class="kpi-label">' + esc(k.label || '') + '</div>'
      + (k.sub ? '<div class="kpi-sub">' + esc(k.sub) + '</div>' : '')
      + '</div>'
    )).join('');

    const rawRows = Object.entries(data)
      .filter(([k]) => k !== 'kpis')
      .map(([k, v]) => (
        '<tr><td><strong>' + esc(k) + '</strong></td>'
        + '<td>' + esc(typeof v === 'object' ? JSON.stringify(v) : String(v)) + '</td></tr>'
      )).join('');

    setTabBody(
      '<div class="kpi-grid">' + cards + '</div>'
      + (rawRows
          ? '<h3 style="margin-top:24px">Detalhes</h3><table class="status-table">'
            + '<thead><tr><th>Chave</th><th>Valor</th></tr></thead>'
            + '<tbody>' + rawRows + '</tbody>'
            + '</table>'
          : '')
    );
  }).catch(e => setTabBody(errHtml(e.message, e.status)));
}

function _statusToKpis(data) {
  const map = [
    ['runtime_ok', 'Runtime'],
    ['llm_provider', 'LLM'],
    ['agents_total', 'Agentes'],
    ['agents_healthy', 'Agentes saudáveis'],
    ['tools_total', 'Tools'],
    ['commit', 'Commit'],
  ];
  const kpis = [];
  map.forEach(([k, label]) => {
    if (k in data) kpis.push({ label: label, value: data[k], sub: typeof data[k] === 'object' ? JSON.stringify(data[k]).slice(0, 60) : undefined });
  });
  return kpis;
}

/* ==========================================
   CRUD STUBS (drawer / forms)
   — mantidos como no-op para não quebrar onclick refs
========================================== */
function accountFormNew() { toast('Em breve: criar conta WhatsApp', 'warn'); }
function accountEdit(id)  { toast('Editar conta: ' + id, 'warn'); }
function accountDel(id)   { toast('Excluir conta: ' + id, 'warn'); }

/* ==========================================
   DRAWER GENÉRICO — edição de agents/skills/tools
   ========================================== */
function openDrawer(title, fields, saveCb) {
  closeDrawer();
  const bd = document.createElement('div');
  bd.className = 'drawer-backdrop';
  bd.id = 'drawer-backdrop';
  bd.onclick = function(e) { if (e.target === bd) closeDrawer(); };

  const dw = document.createElement('div');
  dw.className = 'drawer';
  dw.id = 'drawer';
  dw.innerHTML =
    '<div class="drawer-head"><h3>' + esc(title) + '</h3>'
    + '<button class="close" onclick="closeDrawer()">✕</button></div>'
    + '<div class="drawer-body" id="drawer-body"></div>'
    + '<div class="drawer-foot">'
    + '<button class="secondary" onclick="closeDrawer()">Cancelar</button>'
    + '<button class="primary" id="drawer-save">Salvar</button>'
    + '</div>';

  document.body.appendChild(bd);
  document.body.appendChild(dw);

  const body = dw.querySelector('#drawer-body');
  body.innerHTML = fields.map(f => {
    if (f.type === 'textarea') {
      return '<div class="field-row"><label>' + esc(f.label) + '</label>'
        + '<textarea id="fld-' + f.name + '" rows="' + (f.rows || 8) + '" style="width:100%;font-family:monospace">'
        + esc(f.value || '') + '</textarea></div>';
    }
    return '<div class="field-row"><label>' + esc(f.label) + '</label>'
      + '<input id="fld-' + f.name + '" type="' + (f.type || 'text') + '" value="' + esc(f.value ?? '') + '" style="width:100%"></div>';
  }).join('');

  dw.querySelector('#drawer-save').onclick = function() {
    const data = {};
    fields.forEach(f => {
      const el = document.getElementById('fld-' + f.name);
      if (el) data[f.name] = el.value;
    });
    dw.querySelector('#drawer-save').disabled = true;
    saveCb(data).then(ok => {
      if (ok) { closeDrawer(); toast('Salvo com sucesso', 'good'); }
      else { dw.querySelector('#drawer-save').disabled = false; }
    });
  };
}

function closeDrawer() {
  const bd = document.getElementById('drawer-backdrop');
  const dw = document.getElementById('drawer');
  if (bd) bd.remove();
  if (dw) dw.remove();
}

async function _saveGeneric(type, payload) {
  try {
    const res = await api('/admin/' + type, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return res && (res.status === 'ok' || res.upserted !== false);
  } catch (e) {
    toast('Erro ao salvar: ' + e.message, 'warn');
    return false;
  }
}

function _reloadCurrentTab() {
  const active = document.querySelector('nav button[data-tab].active');
  if (active) setActive(active.dataset.tab);
}

function agentEdit(id) {
  api('/admin/agents/' + encodeURIComponent(id)).then(data => {
    const a = data.agent || {};
    openDrawer('Editar Agente — ' + id, [
      { name: 'id', label: 'ID (agent_id)', value: a.agent_id || id },
      { name: 'name', label: 'Nome', value: a.name },
      { name: 'role', label: 'Role', value: a.role },
      { name: 'model', label: 'Modelo', value: a.model },
      { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: a.system_prompt },
      { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: a.description },
    ], async payload => {
      payload.skills = a.skills || [];
      const ok = await _saveGeneric('agents', payload);
      if (ok) _reloadCurrentTab();
      return ok;
    });
  }).catch(e => toast('Erro ao carregar agente: ' + e.message, 'warn'));
}
function agentFormNew() {
  openDrawer('Novo Agente', [
    { name: 'id', label: 'ID (agent_id)', value: '' },
    { name: 'name', label: 'Nome', value: '' },
    { name: 'role', label: 'Role', value: 'agent' },
    { name: 'model', label: 'Modelo', value: 'deepseek-v4-flash' },
    { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: '' },
    { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: '' },
  ], async payload => {
    if (!payload.id) { toast('ID obrigatório', 'warn'); return false; }
    payload.agent_id = payload.id;
    const ok = await _saveGeneric('agents', payload);
    if (ok) _reloadCurrentTab();
    return ok;
  });
}
function agentDel(id) {
  api('/admin/agents/' + encodeURIComponent(id), { method: 'DELETE' })
    .then(() => { toast('Agente excluído', 'good'); _reloadCurrentTab(); })
    .catch(e => toast('Erro ao excluir: ' + e.message, 'warn'));
}

function skillEdit(id) {
  api('/admin/skills/' + encodeURIComponent(id)).then(data => {
    const s = data.skill || {};
    openDrawer('Editar Skill — ' + id, [
      { name: 'id', label: 'ID (skill_id)', value: s.skill_id || id },
      { name: 'name', label: 'Nome', value: s.name },
      { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: s.description },
      { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: s.system_prompt },
    ], async payload => {
      const ok = await _saveGeneric('skills', payload);
      if (ok) _reloadCurrentTab();
      return ok;
    });
  }).catch(e => toast('Erro ao carregar skill: ' + e.message, 'warn'));
}
function skillFormNew() {
  openDrawer('Nova Skill', [
    { name: 'id', label: 'ID (skill_id)', value: '' },
    { name: 'name', label: 'Nome', value: '' },
    { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: '' },
    { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: '' },
  ], async payload => {
    if (!payload.id) { toast('ID obrigatório', 'warn'); return false; }
    payload.skill_id = payload.id;
    const ok = await _saveGeneric('skills', payload);
    if (ok) _reloadCurrentTab();
    return ok;
  });
}
function skillDel(id) {
  api('/admin/skills/' + encodeURIComponent(id), { method: 'DELETE' })
    .then(() => { toast('Skill excluída', 'good'); _reloadCurrentTab(); })
    .catch(e => toast('Erro ao excluir: ' + e.message, 'warn'));
}

function toolEdit(id) {
  api('/admin/tools/' + encodeURIComponent(id)).then(data => {
    const t = data.tool || {};
    openDrawer('Editar Tool — ' + id, [
      { name: 'id', label: 'ID (tool_id)', value: t.tool_id || id },
      { name: 'name', label: 'Nome', value: t.name },
      { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: t.description },
      { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: t.system_prompt },
    ], async payload => {
      const ok = await _saveGeneric('tools', payload);
      if (ok) _reloadCurrentTab();
      return ok;
    });
  }).catch(e => toast('Erro ao carregar tool: ' + e.message, 'warn'));
}
function toolFormNew() {
  openDrawer('Nova Tool', [
    { name: 'id', label: 'ID (tool_id)', value: '' },
    { name: 'name', label: 'Nome', value: '' },
    { name: 'description', label: 'Descrição', type: 'textarea', rows: 3, value: '' },
    { name: 'system_prompt', label: 'System Prompt', type: 'textarea', rows: 16, value: '' },
  ], async payload => {
    if (!payload.id) { toast('ID obrigatório', 'warn'); return false; }
    payload.tool_id = payload.id;
    const ok = await _saveGeneric('tools', payload);
    if (ok) _reloadCurrentTab();
    return ok;
  });
}
function toolDel(id) {
  api('/admin/tools/' + encodeURIComponent(id), { method: 'DELETE' })
    .then(() => { toast('Tool excluída', 'good'); _reloadCurrentTab(); })
    .catch(e => toast('Erro ao excluir: ' + e.message, 'warn'));
}
function uploadKnowledge() {
  const defaultPhone = (CALLER_ROLE === 'agent_user') ? (CALLER_PHONE || '') : '';
  openDrawer('Upload de Conhecimento (RAG privado)', [
    { name: 'phone', label: 'Telefone do usuário (dono do conhecimento)', value: defaultPhone },
    { name: 'titulo', label: 'Título do documento', value: '' },
    { name: 'conteudo', label: 'Conteúdo (texto a indexar no Firestore Vector)', type: 'textarea', rows: 14, value: '' },
  ], async payload => {
    if (!payload.phone || !payload.titulo || !payload.conteudo) {
      toast('Preencha telefone, título e conteúdo.', 'warn');
      return false;
    }
    try {
      const res = await api('/admin/knowledge/user', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      toast('Indexado: ' + (res.chunks_indexed || 0) + ' chunk(s) no RAG privado', 'good');
      return true;
    } catch (e) {
      toast('Erro ao indexar: ' + e.message, 'warn');
      return false;
    }
  });
}
function delKnowledge(id) { toast('Excluir doc: ' + id, 'warn'); }
function requestOAuth(ph) {
  if (!ph) { toast('Telefone inválido para OAuth.', 'warn'); return; }
  const target = '/oauth/google?phone=' + encodeURIComponent(ph) + (_tok ? '&token=' + encodeURIComponent(_tok) : '');
  toast('Redirecionando para autorização do Google…', '');
  window.open(target, '_blank');
}

/* ==========================================
   NAV ROUTING
========================================== */
function setActive(tab) {
  /* Atualiza destaque da nav */
  document.querySelectorAll('nav button[data-tab]').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === tab)
  );
  const root = document.getElementById('root');
  if (!root) return;

  /* Despacha para o renderer correto */
  switch (tab) {
    case 'accounts':   renderAccounts(root);   break;
    case 'agents':     renderAgents(root);      break;
    case 'skills':     renderSkills(root);      break;
    case 'tools':      renderTools(root);       break;
    case 'conexoes':   renderConexoes(root);    break;
    case 'permissoes': renderPermissoes(root);  break;
    case 'knowledge':  renderKnowledge(root);   break;
    case 'status':     renderStatus(root);      break;
    default:
      root.innerHTML = panelHtml(tab, '', null,
        emptyHtml('Seção não encontrada', 'Tab "' + tab + '" não reconhecida.')
      );
  }
}

/* ---------- Event delegation (click na nav) ---------- */
document.addEventListener('click', function(e) {
  const btn = e.target.closest('nav button[data-tab]');
  if (btn) setActive(btn.dataset.tab);
});

/* ---------- Runtime badge ---------- */
(async function checkRuntime() {
  const badge = document.getElementById('runtime-badge');
  try {
    const s = await api('/admin/status');
    if (badge) {
      badge.textContent = s && s.runtime_ok ? 'runtime ok' : 'runtime off';
      if (!(s && s.runtime_ok)) badge.classList.add('off');
    }
  } catch (_) {
    if (badge) { badge.textContent = 'runtime off'; badge.classList.add('off'); }
  }
})();

/* ---------- Boot: abre tab inicial ---------- */
const _urlTab = new URLSearchParams(location.search).get('tab');
const _initTab = (_urlTab && document.querySelector('nav button[data-tab="' + _urlTab + '"]'))
  ? _urlTab
  : (CALLER_ROLE === 'agent_user' ? 'conexoes' : 'accounts');
setActive(_initTab);
</script>
</body>
</html>
"""

def render_dashboard(commit: str, deployed_at: str, role: str = "admin", caller_phone: str = "") -> str:
    role = role if role in ("admin", "agent_user") else "admin"
    nav_html = (
        _NAV_ADMIN
        if role == "admin"
        else _NAV_AGENT_USER
    )
    payload = {
        "commit": html.escape(commit or "local"),
        "deployed": html.escape(deployed_at or "-"),
        "role": role,
        "caller_phone": html.escape(caller_phone or ""),
    }
    return (
        _TEMPLATE
        .replace("__COMMIT__", payload["commit"])
        .replace("__DEPLOYED__", payload["deployed"])
        .replace("__NAV__", nav_html)
        .replace("__ROLE__", payload["role"])
        .replace("__CALLER_PHONE__", payload["caller_phone"])
    )


_NAV_ADMIN = (
    '<button data-tab="accounts" class="active"><span class="material-symbols-outlined nav-icon">chat</span>Contas WhatsApp</button>\n'
    '    <button data-tab="agents"><span class="material-symbols-outlined nav-icon">smart_toy</span>Agentes</button>\n'
    '    <button data-tab="skills"><span class="material-symbols-outlined nav-icon">psychology</span>Skills</button>\n'
    '    <button data-tab="tools"><span class="material-symbols-outlined nav-icon">build</span>Tools</button>\n'
    '    <button data-tab="conexoes"><span class="material-symbols-outlined nav-icon">hub</span>Conexões</button>\n'
    '    <button data-tab="knowledge"><span class="material-symbols-outlined nav-icon">menu_book</span>Conhecimento</button>\n'
    '    <button data-tab="status"><span class="material-symbols-outlined nav-icon">analytics</span>Status</button>'
)

_NAV_AGENT_USER = (
    '<button data-tab="conexoes" class="active"><span class="material-symbols-outlined nav-icon">hub</span>Conexões</button>\n'
    '    <button data-tab="permissoes"><span class="material-symbols-outlined nav-icon">key</span>Permissões</button>\n'
    '    <button data-tab="status"><span class="material-symbols-outlined nav-icon">analytics</span>Status</button>'
)


__all__ = ["render_dashboard"]


def _json_default(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def jsonify(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)
