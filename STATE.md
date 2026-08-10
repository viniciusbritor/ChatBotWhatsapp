# STATE.md — Estado da Sessão

> Documento persistente para retomada de sessão após restart da IDE.
> Última atualização: 2026-07-30 04:00 BRT

> **Fonte autoritativa de pendências** (ativas + histórico): este arquivo.
> `docs/GUARDRAILS.md` §11 e `docs/ARQUITETURA.md` §11 foram reduzidos a
> pointers para cá (commit batch dedup 30/07/2026). Pendências técnicas
> só devem ser adicionadas aqui; não duplicar em outros docs.

## Resumo executivo

**Branch atual:** `test`
**Último commit local:** `e82ffbe` (TASK A folder permissions fase 1)
**Último deploy em produção:** `b42ec173` SUCCESS, revision `agents-runtime-test-00237`
**Status:** 13 deploys nesta sessão — bugs críticos + admin + privacy + FinOps + RAG indexes resolvidos

## Pendências ativas (próximas fases)

> Documento vivo. Cada fase termina com gate binário e deploy isolado.

### TASK B RAG — runtime enforcement
- **Status:** ✅ **IMPLEMENTADO** (PT6 F5 + owner bypass 01/08/2026)
- **Resolve:** Tools (drive/gmail/calendar) filtram resultados por folder_permissions
- **Cobertura:** `tools/google_*.py` aplicam `check_folder_permission` (pré) +
  `post_filter_tool_result` (pós) via `core/owner_guard.py`; owner da instância
  tem bypass automático. Tests: `test_folder_permissions_enforcement.py` (9),
  `test_owner_guard.py` (21), `test_folder_permissions.py` (11).

### TASK A Admin — runtime enforcement
- **Status:** ✅ **IMPLEMENTADO** (mesma esteira da TASK B)
- **Resolve:** Tools consultam `get_user_allowed_tools()` antes de retornar resultados

### Pendências externas (bloqueio usuário)
> **Restrição (user 30/07):** rotacao de credenciais NAO sera feita por mim. Quebraria tudo.
> Apenas o user tem acesso ao Secret Manager. Manter as chaves atuais.
- [ ] OAuth Client setup no Google Cloud Console para telefone `+5511966830020` (setup manual user)
- [ ] Backfill embeddings legacy (script não criado)
- [ ] README desatualizado em `agents_runtime/README.md`

### Edge cases pendentes (não-críticos)
- [ ] Anexo + pergunta pessoal — routing híbrido RAG + Drive
- [ ] Multi-intent write race (Fase 4.1)
- [ ] Retry budget granular in-process (Fase 0.5 Patch 4)
- [ ] Audit log assíncrono (Fase 5 — performance)

## Conquistas da sessão 30/07/2026 (DEPLOYADAS em test)

| # | Fase | Commit | Mudança |
|---|---|---|---|
| 0 | Dedup docs | `109410f` | GUARDRAILS/ARQUITETURA/STATE autoritativo |
| 1 | Tick azul | `8dce677` | Cold start 12s vs warm 5s |
| 2 | RAG keywords | `4883d5a` | 28 keywords conversacionais + acento |
| 3 | LLM contexto | `b8ccf48` | Tie-breaker com 2 últimas msgs |
| 4 | Recent indexing | `95f0260` | Auto is_rag por 5min pós-indexing |
| 5 | Scope-aware | `a062456` | phone OU group_jid; keywords user |
| 6 | Filename routing | `789f488` | Bypass defense-in-depth para `.pdf/.docx` |
| 7 | PDF multi-parser | `4e01dd9` | pypdf → pdfplumber → pdfminer |
| 8 | PDF partial | `c3bed1f` | Tolerância página-a-página + logging |
| A | Max tokens | `ee977fa` | Manager 1000 → 1500 via env |
| B | Auto-image RAG | `32a04ef` | knowledge.retrieve → tabela PNG |
| C | Humanização | `60ccee6` | Sazonalidade BRT + tom caloroso |
| D | Privacy audit | `bc0e217` | PRIVACY_AUDIT.md completo |
| E | FinOps pricing | `da6d01b` | core/pricing.py + cost_usd_estimated |
| F | ROADMAP.md | `94aacaf` | ROADMAP.md + STATE.md consolidado |
| **G** | Guard sync | `8710c0e` | **Latência -8s warm (chamada direta)** |
| **H** | RAG indexes | `29c48a0` | **Vector composite indexes (resolve Edital.pdf bug)** |
| **I** | Admin folder perms | `e82ffbe` | **Folder permissions endpoints + storage** |

## Documentos operacionais criados

| Doc | Função |
|---|---|
| `docs/CURRENT_PLAN.md` | Plano detalhado das fases A-F com custos estimados |
| `docs/PRIVACY_AUDIT.md` | Auditoria completa de privacidade (7 camadas) |
| `docs/ROADMAP.md` | Roadmap longo prazo + loop methodology |
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
