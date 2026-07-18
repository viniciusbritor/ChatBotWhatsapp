# Harness do Projeto — ChatBotWhatsapp

> **Ambiente Operacional:** Instrucoes para configurar, executar e depurar o modulo `omnichannel-agentes` + servico `agents_runtime`.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

## GCP Project & Recursos

- **Project:** `coherence-ominichannel-fs`
- **Region:** `us-central1`
- **Servicos Cloud Run (TEST):**
  - `agents-runtime-test` (2Gi, min=0, ping 5min)
  - `coherence-portal-test` (2Gi, existente)
  - `whatsapp-agente-test` (1Gi, min=0, ping 5min)
- **Jobs Cloud Run:**
  - `ata-worker-test` (geracao de atas)
  - `proactive-worker-test` (mensagens proativas)
- **Pub/Sub topics:**
  - `monitoria-whisper-jobs` (existente, eventual fallback audio)

## Variaveis de Ambiente

### `agents_runtime/.env.runtime.test.yaml`

```yaml
# LLM
DEEPSEEK_BASE_URL: "https://api.deepseek.com"
NVIDIA_BASE_URL: "https://integrate.api.nvidia.com/v1"
MINIMAX_BASE_URL: "https://api.minimax.io/v1/text/chatcompletions"
MINIMAX_MODEL: "MiniMax-M3"

# Embeddings (MiniMax embo-01 via LangChain)
MINIMAX_GROUP_ID: "seu-group-id-aqui"

# Auth
ALLOW_PUBLIC_HEALTHZ: "true"
AGENTS_RUNTIME_SA_TOKEN_SECRET: "agents-runtime-sa-token"

# Proatividade
PROACTIVE_OWNER_PHONES: "+5511966830020"
PROACTIVE_DISABLED: "false"
PROACTIVE_DRY_RUN: "false"
PROACTIVE_MAX_PER_CONTACT_DAY: "2"
PROACTIVE_MAX_GLOBAL_DAY: "5"
PROACTIVE_COOLDOWN_HOURS: "12"
PROACTIVE_QUIET_HOURS_START: "21"
PROACTIVE_QUIET_HOURS_END: "9"
PROACTIVE_MIN_RELEVANCE: "0.75"

# Hot-reload e status operacional
AGENT_RELOAD_INTERVAL_SEC: "120"
AGENT_HEALTH_WINDOW_SEC: "86400"
PENDING_ACTION_TTL_SEC: "300"
RESPONSE_IDEMPOTENCY_TTL_SEC: "86400"

# Firestore
GCP_PROJECT: "coherence-ominichannel-fs"

# Typing effect
TYPING_DELAY_MS_PER_WORD: "600"
TYPING_DELAY_MS_CAP: "15000"

# Escalacao
ESCALATION_THRESHOLD_DEFAULT: "-2"
ESCALATION_MAX_PROBABILITY: "0.20"

# Whisper local e seguranca de audio
WHISPER_MODEL: "base"
WHISPER_DEVICE: "cpu"
WHISPER_COMPUTE_TYPE: "int8"
WHISPER_DOWNLOAD_ROOT: "/app/whisper_models"
AUDIO_MAX_BYTES: "26214400"
AUDIO_MAX_DURATION_SEC: "300"
AUDIO_DOWNLOAD_TIMEOUT_SEC: "30"
AUDIO_URL_ALLOWED_HOSTS: "evolution.coherenceai.com.br"

# RAG Firestore Vector v2
RAG_EMBEDDING_MODEL: "embo-01"
RAG_EMBEDDING_DIM: "1536"
RAG_SCHEMA_VERSION: "2"
RAG_MEMORY_COLLECTION: "conversation-memory-v2"
RAG_PRIVATE_COLLECTION: "agent-knowledge-v2"
RAG_SHARED_COLLECTION: "public-knowledge-v2"
RAG_RETENTION_DAYS: "90"

# Observabilidade
LOG_LEVEL: "INFO"
ENVIRONMENT: "test"
```

### Secrets (Secret Manager `coherence-ominichannel-fs`)

| Secret | Proposito |
|---|---|
| `deepseek-api-key` | LLM primario |
| `nvidia-api-key` | LLM fallback NIM |
| `minimax-api-key` | LLM ultimo recurso |
| `serper-api-key` | Web search |
| `google-oauth-token` | Calendar/Drive/Gmail |
| `agents-runtime-sa-token` | Bearer para Portal/WhatsappAgente chamarem |
| `evolution-api-key` | Evolution API |
| `agents-runtime-url` | URL do servico agents-runtime-test |
| `whatsapp-agente-url` | URL do servico whatsapp-agente-test |

**Upload correto (NUNCA `versions update`, sempre `versions add`):**

```bash
# Script wrapper: scripts/upload_secrets.sh
#!/bin/bash
# Valida UTF-8 antes de upload para evitar bug de encoding (12/07/2026)
set -e
PROJECT="coherence-ominichannel-fs"
SECRET_NAME="$1"
VALUE="$2"

if [ -z "$SECRET_NAME" ] || [ -z "$VALUE" ]; then
  echo "Usage: $0 <secret-name> <value>"
  exit 1
fi

# Validacao UTF-8
echo -n "$VALUE" | iconv -f UTF-8 -t UTF-8 > /dev/null 2>&1 || {
  echo "ERRO: valor nao e UTF-8 valido"
  exit 1
}

# Verifica se secret existe
if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" > /dev/null 2>&1; then
  echo -n "$VALUE" | gcloud secrets versions add "$SECRET_NAME" \
    --project="$PROJECT" --data-file=- --replication-policy=automatic
else
  echo -n "$VALUE" | gcloud secrets create "$SECRET_NAME" \
    --project="$PROJECT" --data-file=- --replication-policy=automatic
fi
```

Uso:
```bash
chmod +x scripts/upload_secrets.sh
./scripts/upload_secrets.sh deepseek-api-key "sk-..."
./scripts/upload_secrets.sh nvidia-api-key "nvapi-..."
./scripts/upload_secrets.sh minimax-api-key "eyJ..."
./scripts/upload_secrets.sh serper-api-key "..."
./scripts/upload_secrets.sh google-oauth-token "$(cat token.json)"
./scripts/upload_secrets.sh agents-runtime-sa-token "$(openssl rand -hex 32)"
./scripts/upload_secrets.sh evolution-api-key "..."
```

## Cloud Scheduler (Triggers)

| Job | Frequencia | Acao |
|---|---|---|
| `ata-worker-trigger` | `*/10 * * * *` | Chama `ata-worker-test` |
| `proactive-worker-events-trigger` | `*/15 * * * *` | Chama `proactive-worker-test` (eventos Calendar) |
| `proactive-worker-topics-trigger` | `0 8 * * 2,5` | Chama `proactive-worker-test` (terca + sexta 8h BRT) |
| `ping-agents-runtime` | `*/5 * * * *` | GET `/healthz` em agents-runtime-test |
| `ping-whatsapp-agente` | `*/5 * * * *` | GET `/healthz` em whatsapp-agente-test |
| `group-sync-trigger` | `0 */6 * * *` | Sincroniza membros dos grupos via Evolution API |
| `proactive-weekly-eval` | `0 20 * * 0` | Auto-avaliacao semanal (domingo 20h BRT) |
| `history-cleanup` | `0 3 * * *` | Limpa historico e `conversation-memory-v2` expirados ha mais de 90 dias |

## Estrutura de Diretorios

```
ChatBotWhatsapp/
├── docs/                              # este workspace
│   ├── PLAN_OMNICHANNEL_AGENTES.md   # plano consolidado
│   ├── ARQUITETURA.md
│   ├── HARNESS.md                    # este arquivo
│   ├── GUARDRAILS.md
│   └── DIARIO_BORDO.md
└── agents_runtime/                    # PROJETO NOVO (Fase 1+)
    ├── main.py
    ├── orchestrator.py
    ├── core/
    │   ├── llm_provider.py
    │   ├── escalation.py
    │   ├── masker.py
    │   ├── delay_calculator.py
    │   ├── proactive_gate.py
    │   ├── auth.py
    │   └── rag.py
    ├── tools/
    │   ├── google_calendar.py
    │   ├── google_drive.py
    │   ├── google_gmail.py
    │   ├── web_search.py
    │   ├── nickname.py
    │   ├── correction.py
    │   ├── proactive.py
    │   ├── group.py
    │   ├── audio_transcribe.py
    │   └── ata_helper.py
    ├── ata_worker/
    ├── proactive_worker/
    ├── docs/
    │   ├── ARQUITETURA.md
    │   ├── HARNESS.md
    │   ├── GUARDRAILS.md
    │   ├── DIARIO_BORDO.md
    │   └── MODULE_INTEGRATION.md
    ├── tests/
    ├── scripts/
    │   ├── upload_secrets.sh
    │   ├── seed_legal_knowledge.py
    │   └── sync_group_members.py
    ├── data/
    │   └── nicknames.json
    ├── requirements.txt
    ├── Dockerfile
    ├── cloudbuild.yaml
    └── .env.runtime.test.yaml
```

## Como Executar e Testar

### Deploy Local (em construcao)

```bash
cd agents_runtime
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows
pip install -r requirements.txt
cp .env.runtime.test.yaml .env
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Local dev com Firestore Emulator

```bash
# Terminal 1: Firestore emulator
firebase emulators:start --only firestore,auth --project coherence-ominichannel-fs

# agents_runtime/.env.local
FIRESTORE_EMULATOR_HOST=localhost:8080
GCLOUD_PROJECT=coherence-ominichannel-fs
ALLOW_PUBLIC_HEALTHZ=true
AGENTS_RUNTIME_SA_TOKEN_SECRET=local-dev-token

# Terminal 2: agents_runtime
uvicorn main:app --reload
```

### Testes de inventario e orquestracao

```bash
pytest -q tests/test_agent_status.py tests/test_dialog_runtime_status.py tests/test_pending_actions.py tests/test_agent_loader.py tests/test_tool_registry.py
pytest -q tests/
```

Resultado local da Fase 4 em 18/07/2026: 41 testes especificos e 193 testes totais passaram; 9 foram ignorados.

### Testes de audio

```bash
pytest -q tests/test_audio_transcribe.py tests/test_main_audio.py tests/test_llm_provider.py
pytest -q tests/
```

Resultado local da Fase 5 em 18/07/2026: 30 testes especificos e 212 testes totais passaram; 9 foram ignorados. O teste integrado com audio real do WhatsApp permanece como smoke test do ambiente implantado.

### Deploy Cloud Run (TEST)

```bash
cd agents_runtime
git checkout test
git add -A
git commit -m "feat(phase-N): ..."
git push origin test
# Cloud Build dispara automaticamente
gcloud builds list --project=coherence-ominichannel-fs --limit=1
```

### Smoke Test

```bash
# Health check (publico)
curl https://agents-runtime-test-XXX-uc.a.run.app/healthz

# Chat (requer SA token)
curl -X POST https://agents-runtime-test-XXX-uc.a.run.app/chat \
  -H "Authorization: Bearer $AGENTS_RUNTIME_SA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance":"jennifer","phone":"+5511966830020","text":"oi","sender_name":"Test"}'
```

### Testes Automatizados

```bash
cd agents_runtime
pytest -q                                  # backend
```

## Autenticação e Segredos

- **Local dev:** `.env` (gitignored) + fallback para `secrets_manager.py`
- **Cloud Run:** `--set-secrets` em `cloudbuild.yaml` referencia segredos do Secret Manager
- **Nunca:** hardcoded keys em código (regra global + GUARDRAILS)

## CI/CD

```yaml
# agents_runtime/cloudbuild.yaml (resumo)
steps:
  1. LGPD compliance check (script compartilhado)
  2. pytest -q
  3. docker build + push
  4. gcloud run deploy agents-runtime-test \
       --region=us-central1 \
       --memory=2Gi \
       --cpu=2 \
       --min-instances=0 \
       --max-instances=3 \
       --cpu-boost \
       --no-cpu-throttling
trigger: push em `test`
```

## Scripts Auxiliares

### Firestore Vector v2

Antes do smoke test integrado:

1. Confirmar que `RAG_EMBEDDING_MODEL=embo-01` e `RAG_EMBEDDING_DIM=1536`.
2. Criar indices vetoriais para `conversation-memory-v2`, `agent-knowledge-v2` e `public-knowledge-v2` no projeto de teste.
3. Para collections privadas, incluir o filtro `owner_hash` no indice requerido pelo Firestore.
4. Executar a reindexacao idempotente do corpus publico.
5. Validar que todos os documentos possuem `embedding_model`, `embedding_dim`, `schema_version` e `vector_embedding`.
6. Executar `pytest tests/test_rag.py -v` antes da suite completa.
7. Validar o corpus sem escrita com `python scripts/migrate_rag_v2.py --dry-run`.
8. Reindexar no projeto de teste somente apos os indices estarem ativos com `python scripts/migrate_rag_v2.py`.

O Firestore Emulator nao oferece validacao equivalente para consultas vetoriais. Testes locais usam mocks; o smoke test vetorial utiliza exclusivamente o projeto GCP de teste.

### `scripts/seed_legal_knowledge.py`

Pre-popula `agente-knowledge-{phone}` com ~10 documentos legais essenciais para o RAG juridico:

- Codigo Penal Arts. 146-A (Assedio moral), 147-A (Ameaca), 213 (Estupro)
- Lei 13.185/2015 (Bullying)
- Lei Maria da Penha (Lei 11.340/2006)
- CDC Art. 42 (praticas abusivas)
- ECA (referencia)
- Links Planalto.gov.br, gov.br/mdh

### `scripts/sync_group_members.py`

Sincroniza membros dos grupos via Evolution API. Chamado pelo Cloud Scheduler a cada 6h.

## Referencias

- [PLAN_OMNICHANNEL_AGENTES.md](./PLAN_OMNICHANNEL_AGENTES.md) - Plano completo
- [ARQUITETURA.md](./ARQUITETURA.md) - Arquitetura
- [GUARDRAILS.md](./GUARDRAILS.md) - Regras inegociaveis
- `Coherence_Portal/docs/HARNESS.md` - Harness do Portal
- `WhatsappAgente/docs/HARNESS.md` - Harness do adapter