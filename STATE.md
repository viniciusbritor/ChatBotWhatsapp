# STATE.md — Estado da Sessão

> Documento persistente para retomada de sessão após restart da IDE.
> Última atualização: 2026-07-30

## Resumo executivo

**Branch atual:** `test`
**Último commit local:** `95f0260` (Fase 4 RAG recent indexing)
**Último deploy em produção:** `0f1da60e` SUCCESS, revision `agents-runtime-test-00222-l6l`
**Status:** 4 fases RAG + anti-lockup deployadas, em coleta de feedback

## Conquistas da sessão (DEPLOYADAS em test)

| Fase | Commit | Mudança principal |
|---|---|---|
| Fase 0.5 | `5b3d571` | Anti-lockup patches (per-task asyncio timeouts) |
| **1 — Tick azul** | `8dce677` | **Cold start timeout 12s vs warm 5s** (resolve "não aparece confirmação em cold start") |
| **2 — RAG keywords** | `4883d5a` | **28 keywords conversacionais + normalização de acentos** (resolve "Sobre o que é esse documento?") |
| **3 — LLM contexto** | `b8ccf48` | **Tie-breaker recebe últimas 2 msgs do phone** |
| **4 — Recent indexing** | `95f0260` | **Auto is_rag por 5min após indexing** |

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
