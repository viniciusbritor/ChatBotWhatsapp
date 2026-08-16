# STATE.md — Estado da Sessão

> Documento persistente para retomada de sessão após restart da IDE.
> Última atualização: 2026-08-16 03:55 BRT

> **Fonte autoritativa de pendências** (ativas + histórico): este arquivo.
> `docs/GUARDRAILS.md` §11 e `docs/ARQUITETURA.md` §11 foram reduzidos a
> pointers para cá (commit batch dedup 30/07/2026). Pendências técnicas
> só devem ser adicionadas aqui; não duplicar em outros docs.

## Resumo executivo

**Branch atual:** `test` (sync com `origin/test`)
**Último commit deployado:** `dc700bd` (PR #39 — FinOps light theme)
**Último deploy em produção:** revision `agents-runtime-test-00002-wrd` em `southamerica-east1`
**Status:** 9 deploys nesta sessão — FASE 1+2+3 (cleanup MiniMax, BR migration, 6 portal fixes)
**URL atual:** https://agents-runtime-test-c5nbfc5meq-rj.a.run.app

## Pendências ativas (próximas fases)

> Documento vivo. Cada fase termina com gate binário e deploy isolado.

### FASE 1 — Code Optimizations ✅ COMPLETA
- 1.1 mark_read dedup (PR #27) ✅
- 1.2 prefetch conditional (PR #28) ✅
- 1.3 prompt compress (PR #29) ✅
- 1.4 link_shortener opt-in (PR #30) ✅

### FASE 2 — Cloud Run BR Migration ✅ COMPLETA
- 2.1 docs BR region (PR #31) ✅
- 2.2 Firestore location audit script (PR #32) ✅
- 2.3 cloudbuild BR region (PR #33) ✅
- 2.3.1 fix cloud build keywords (PR #34) ✅

### FASE 3 — Portal Issues ✅ COMPLETA (15/08/2026 23:55 BRT)
- 3.1 phone number fix 5511966830020 → 5511967389901 (PR #35) ✅
- 3.2 LLM dropdown → read-only DeepSeek (PR #36) ✅
- 3.3 Owners + WhatsApp Accounts enriched (PR #37) ✅
- 3.4 Composio naming + UI shrink-0 (PR #38) ✅
- 3.5 FinOps dark → light theme (PR #39) ✅

### Pendências externas (bloqueio usuário)
> **Restrição (user 30/07):** rotacao de credenciais NAO sera feita por mim. Quebraria tudo.
> Apenas o user tem acesso ao Secret Manager. Manter as chaves atuais.
- [ ] OAuth Client setup no Google Cloud Console para telefone `+5511967389901` (setup manual user)
- [ ] Rodar `python agents_runtime/scripts/migrate_owner_phone_to_9901.py --apply` no Firestore
- [ ] Backfill embeddings legacy (script não criado)
- [ ] README desatualizado em `agents_runtime/README.md` (suite 1184 → atualizada)

### FASE 4 — Deferida (condicional)
- [ ] **JWT cache in-memory** (>100 users OU receita >$500/mês)
- [ ] **Streaming SSE** chat_with_tools (idem)
- [ ] **Auth middleware skip internal ports** (idem)
- [ ] **Redis OAuth tokens** ($30/mês, idem)
- [ ] **Multi-region (BR + US)** ($60+/mês, idem)

### Edge cases pendentes (não-críticos)
- [ ] Anexo + pergunta pessoal — routing híbrido RAG + Drive
- [ ] Multi-intent write race (Fase 4.1)
- [ ] Retry budget granular in-process (Fase 0.5 Patch 4)
- [ ] Audit log assíncrono (Fase 5 — performance)

## Conquistas consolidadas (15/08/2026 — sessão atual)

| # | Fase | PR | Mudança | Ganho |
|---|---|---|---|---|
| 1.1 | mark_read dedup | #27 | Sliding window 5s por (instance, remote_jid) | -80% chamadas Evolution |
| 1.2 | prefetch conditional | #28 | Cascata híbrida: Firestore (name→push_name) → Evolution | -50% prefetch desnecessário |
| 1.3 | prompt compress | #29 | jennifier.yaml 8.5KB → 3.9KB (-53.9%) | -67% tokens input |
| 1.4 | link_shortener opt-in | #30 | Skip se < 50 chars OU sem http:// | -70% chamadas TinyURL |
| 2.1 | docs BR region | #31 | HARNESS.md Guardrail 59 → southamerica-east1 | Doc-only |
| 2.2 | Firestore audit | #32 | Script de auditoria (idempotente) | Audit-on-demand |
| 2.3 | cloudbuild BR | #33 | --region=southamerica-east1 | -150ms latência BR |
| 2.3.1 | fix cloud build | #34 | Restaura keywords críticos | Build SUCCESS |
| 3.1 | phone number | #35 | 5511966830020 → 5511967389901 | Dados corretos |
| 3.2 | LLM dropdown | #36 | Dropdown → read-only display | UI consistente |
| 3.3 | Owners + Accounts | #37 | Cross-reference badge "WhatsApp:" | Melhor info |
| 3.4 | Composio naming | #38 | Slug-based names (sem random suffix) | UI legível |
| 3.5 | FinOps light theme | #39 | Dark → light tokens | Consistência visual |

## Documentos operacionais criados

| Doc | Função |
|---|---|
| `docs/CURRENT_PLAN.md` | Plano detalhado das fases A-F com custos estimados |
| `docs/PRIVACY_AUDIT.md` | Auditoria completa de privacidade (7 camadas) |
| `docs/ROADMAP.md` | Roadmap longo prazo + loop methodology |
| `agents_runtime/core/owner_name.py` | D3 hybrid name resolver (Firestore → Evolution → mascarado) |
| `agents_runtime/scripts/migrate_owner_phone_to_9901.py` | Migration script (idempotente) |
| `agents_runtime/scripts/audit_firestore_location.py` | Audit script (BR compliance) |
| `agents_runtime/core/link_shortener.py` | Opt-in shortener com 3 providers |
| `scripts/agent_sync/` | Multi-agent coordinator (claims, audit, release, coordinator) |
| `STATE.md` | Este arquivo — fonte autoritativa |

## WhatsappAgente — RESOLVIDO (histórico)

Confirmado pelo usuário em 30/07/2026 que está 100% resolvido:
- Repo `viniciusbritor/WhatsappAgente` no GitHub — deletado
- Service Cloud Run `whatsapp-agente-test` — deletado em 23/07/2026
- Pastas locais (legado) — handled out-of-band pelo usuário
- `agents_runtime/whatsapp_agente_pubsub_reference.py` — deletado em 19/07/2026 (commit `2a926e8`, 481 linhas)

## WhatsappAgente — RESOLVIDO (histórico)

Confirmado pelo usuário em 30/07/2026 que está 100% resolvido:
- Repo `viniciusbritor/WhatsappAgente` no GitHub — deletado
- Service Cloud Run `whatsapp-agente-test` — deletado em 23/07/2026
- Pastas locais (legado) — handled out-of-band pelo usuário
- `agents_runtime/whatsapp_agente_pubsub_reference.py` — deletado em 19/07/2026 (commit `2a926e8`, 481 linhas)

Pasta `WhatsappAgente/` local pode existir como untracked (no .gitignore). Não tocar.

## Pendente de execução (próximas fases)

### Fase 0.5 — Anti-lockup patches
- [x] ~~Patch 1: timeout universal em http_client.py~~ — **DESCARTADO** (todos call-sites já têm timeout)
- [x] Patch 2: asyncio.gather outer timeout — **DEPLOYADO** `5b3d571`
- [x] ~~Patch 3: GET /healthz endpoint dedicado~~ — **JÁ EXISTIA**
- [⚠️] ~~Patch 4: Pub/Sub DLQ + retry budget~~ — **PARCIAL** (DLQ + max-attempts=5 ok; retry budget granular pendente)

### Fase 1 — Otimizações conservadoras
- [ ] 1.1: Guard sync (substituir LangGraph state machine por função sync)
- [ ] 1.2: max_tokens=1500 para manager-*
- [ ] 1.3: Bypass DeepAgent para manager-* com tools

### Fase 2 — Cache LRU
- [ ] 2.1: LRU cache exato (5min TTL, maxsize=512)
- [ ] 2.2: Admin endpoint para invalidação de cache

### Fase 3 — Streaming + Paralelismo
- [ ] 3.1: SSE streaming com timeout por chunk
- [ ] 3.2: Tool calls paralelos (bounded por semáforo)

### Fase 4 — Simplificação
- [ ] 4.1: Orchestrator split (simple vs complex paths)
- [ ] 4.2: Redis rate limit com fallback memory

### Fase 5 — Custo + edge cases
- [ ] 5.1: Batch RAG indexing (60s janela)
- [ ] 5.2: Dedupe tool calls
- [ ] 5.3: Prompt compression
- [ ] Edge cases: anexo + pergunta pessoal, runtime status vs pessoal, drive vs calendar ambíguo

### Fase 6 — RAG Otimizado (F4d.13 → F4d.18)
- [ ] 6.1 (F4d.13): Metadata hierárquico + legal_id + page_number
- [ ] 6.2 (F4d.14): Hybrid search (vector + BM25)
- [ ] 6.3 (F4d.15): Citation format estruturado
- [ ] 6.4 (F4d.16): Domain embeddings (avaliação)
- [ ] 6.5 (F4d.17): Multi-document synthesis
- [ ] 6.6 (F4d.18): Versionamento de documentos

## Recursos para Golden Set (RAG)

**Localização:** `C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\GoldenSet\`

```
cdc-portugues-2013.pdf    (972 KB) - Lei federal
dissertação.pdf          (1.2 MB) - Tese acadêmica
Edital.pdf               (379 KB) - Edital de licitação
```

**Queries:** NÃO há queries pré-existentes. Conforme constraint do user:
> "precisam sempre ser explicito a solicitação a base de conhecimento"

**Estratégia:** gerar queries sintéticas com marcadores RAG fortes:
- "tem alguma coisa sobre [tópico]?"
- "existe algum documento sobre [tópico]?"
- "o que você memorizou sobre [tópico]?"

**Resposta esperada:** qualidade do conteúdo retornado (citation accuracy ≥ 95%).

## Tabela de Intents (referência)

| Intent | O que é | Agent roteado |
|---|---|---|
| `is_runtime_status` | "quantos agentes", "agentes ativos" | `runtime-status` |
| `is_gross` | linguagem vulgar | `agent-morality` |
| `is_assault_related` | assédio/violência | `agent-morality` |
| `is_correction` | "na verdade", "errado" | `agent-learning` |
| `is_intimacy` | "me chame de", "meu apelido" | `agent-intimacy` |
| `is_rag` | "tem alguma coisa sobre", "existe algum documento" | `agent-knowledge-retriever` |
| `is_drive` | "drive", "arquivo", "pasta" | `manager-drive` |
| `is_email` | "email", "gmail" | `manager-email` |
| `is_calendar` | "agenda", "compromisso" | `manager-calendar` |
| `is_web_search` | URL explícita | `manager-web` |
| `is_attachment` | anexo PDF/DOCX | `_handle_attachment` |

## Decisões de arquitetura

| Decisão | Razão |
|---|---|
| Multi-agent paralelo | Permite tools em paralelo (email+calendar) sem runtime overhead |
| Defense-in-depth (retriever excluído com intent pessoal) | Evita misroute via `is_rag=True` em perguntas pessoais |
| Bypass DeepAgent para manager-* | LangGraph state machine adiciona ~2-3s sem benefício |
| Skip prefetch quando agent tem tools | Tools já fazem fetch fresh |
| Cache Evolution instance TTL 60s | Elimina HTTP round-trip em cada send |
| Pre-warm deepagents no boot | Evita 13s cold start |

## Comandos úteis (para retomar)

```powershell
# Status
cd C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp
git log --oneline -5
git status -sb

# Validar deploy atual
gcloud --project=coherence-ominichannel-fs builds list --region=us-central1 --limit=1 --format='value(id,status)'
gcloud --project=coherence-ominichannel-fs run services describe agents-runtime-test --region=us-central1 --format='value(status.latestReadyRevisionName)'

# Health check
Invoke-WebRequest -Uri "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/health" -Method GET -UseBasicParsing

# Testes
cd C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\agents_runtime
$env:PYTHONPATH = "C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\agents_runtime"
python -m pytest tests/test_observability.py tests/test_orchestrator.py -q
```

## Padrão de feature flag (a usar em todas as fases)

```python
# Default off, opt-in via env var
FEATURE_FLAG_NAME = os.getenv("FEATURE_FLAG_NAME", "false").lower() == "true"

# Rollback < 30s: muda env var + redeploy (~3min Cloud Build)
# Canary: 5% → 25% → 100% em 24h
```

## Cronograma estimado (com testes)

| Fase | Duração | Testes | Shadow |
|---|---|---|---|
| 0.5 Anti-lockup | 1 dia | 2h | 1h |
| 1. Otimizações | 2 dias | 1 dia | 1 dia |
| 2. Cache LRU | 3 dias | 1 dia | 2 dias |
| 3. Streaming | 1 sem | 2 dias | 3 dias |
| 4. Orchestrator split | 2 sem | 3 dias | 4 dias |
| 5. Custo | ongoing | 1 dia | 2 dias |
| 6. RAG | 6 sem (sem fine-tune) | 2 sem | 3 sem |

## Padrão de edge cases identificados

| Edge case | Severidade | Status |
|---|---|---|
| Anexo + pergunta pessoal | Média | Pendente Fase 5 |
| RAG vs pessoal | ✅ Corrigido F4d.9 | — |
| Drive vs Calendar ambíguo | Baixa | Pendente Fase 5 |
| Race nick_name_consent | Baixa | Pendente Fase 5 |
| URL não-web-search | Baixa | Pendente Fase 4 |
| Gross vs Correction | Baixa | Pendente Fase 5 |
| Runtime status vs pessoal | Média | Pendente Fase 5 |
| OAuth + group multi-step | Baixa | Pendente Fase 5 |
| Multi-intent write race | Alta (futuro) | Pendente Fase 4.1 |

### Pendências técnicas legadas (carry-over pré-sessão)

- [ ] **RAG backfill embeddings** sob o antigo `_owner_hash(phone)` (era `contatos/.../historico`).
  Owner hash mudou para `sha256(phone_digits)[:32]` em migração F4'. Requer script
  `scripts/backfill_owner_hash_embeddings.py` (não criado).
- [ ] **`agents_runtime/README.md`** ainda menciona contagens antigas de testes/agentes.
  Atualizar após Fase 0.5 estabilizar (próximo batch).
- ~~[x] **Scripts órfãos versionados** (cleanup 31/07/2026)~~ — **RESOLVIDO**: 17 arquivos
  (`create_contact*`, `verify_contact*`, `google_oauth_v*`, `seed_codigo_penal*`, `migrate_rag_v2`)
  removidos. Zero referências em runtime/tests/docs.

## Conta-gotas do que está em produção

- **Cloud Run:** `agents-runtime-test` revision 00216 (F4d.10)
- **Build atual:** disparado por push de `fc9a16a` → aguardando SUCCESS
- **URL:** https://agents-runtime-test-c5nbfc5meq-uc.a.run.app
- **Trigger:** `deploy-agents-runtime-test` (push em `test`)
- **NÃO existe trigger para `main`** — produção não é deploy automática

## Próxima ação sugerida (quando retomar)

```bash
# 1. Verificar status do build atual
gcloud --project=coherence-ominichannel-fs builds list --region=us-central1 --limit=1

# 2. Se SUCCESS, validar observability no health
Invoke-WebRequest -Uri "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/health" -Method GET

# 3. Iniciar Fase 0.5 - Anti-lockup patches
# Criar: agents_runtime/core/http_client.py com timeout wrapper
# Criar: agents_runtime/tests/test_anti_lockup.py
```

## Histórico completo

Ver `docs/DIARIO_BORDO.md` para narrative detalhada por dia.
