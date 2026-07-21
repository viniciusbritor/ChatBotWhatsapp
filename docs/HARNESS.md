# Harness do Projeto — ChatBotWhatsapp

> **Ambiente Operacional:** Instrucoes para configurar, executar e depurar o modulo `omnichannel-agentes` + servico `agents_runtime`.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

## GCP Project & Recursos

- **Project:** `coherence-ominichannel-fs`
- **Region:** `us-central1`
- **Servicos Cloud Run (TEST):**
  - `agents-runtime-test` (2Gi, min=0, max=3) — recebe webhook do Evolution, processa com LLM, retorna resposta
  - `coherence-portal-test` (2Gi, existente) — UI do Portal
  - ~~`whatsapp-agente-test`~~ (removido na Fase A 2026-07-21) — webhook consolidado em `agents-runtime`
- **Jobs Cloud Run:**
  - `ata-worker-test` (geracao de atas)
  - `proactive-worker-test` (mensagens proativas)
- **Pub/Sub topics:**
  - `whatsapp-messages` (webhook → agents-runtime, prod e test)
  - `whatsapp-messages-dlq` (DLQ para retries > 5)
  - `monitoria-whisper-jobs` (existente, eventual fallback audio)

## Arquitetura consolidada (2026-07-21)

O projeto `viniciusbritor/ChatBotWhatsapp` contém **apenas** o serviço de agentes. O proxy Evolution foi consolidado dentro do próprio `agents-runtime` via endpoint `POST /webhook` que publica no Pub/Sub `whatsapp-messages`. A pipeline ponta-a-ponta é:

```
Celular
  ↕ (áudio/texto)
Evolution API (projeto EvolutionWhatsapp, repo separado)
  ↕ (webhook POST https://agents-runtime-test-...a.run.app/webhook)
agents-runtime-test (Cloud Run, projeto ChatBotWhatsapp)
  ↕ (POST /webhook → publish whatsapp-messages)
Pub/Sub whatsapp-messages
  ↕ (push subscription agents-runtime-consumer → /pubsub/push)
agents-runtime-test (POST /pubsub/push, dedupe, orchestrate)
  ↕ (Whisper + LLM cascade)
Evolution /message/sendText
  ↕ (resposta)
Celular
```

Os repos `viniciusbritor/EvolutionWhatsapp` (hospeda o Evolution API) e `viniciusbritor/ChatBotWhatsapp` (hospeda o agents-runtime) são **separados** e **independentes**.

## CI/CD (Cloud Build triggers)

| Trigger | Repo | Branch | Build config | Service Account |
|---|---|---|---|---|
| `deploy-agents-runtime-test` | ChatBotWhatsapp | `^test$` | `agents_runtime/cloudbuild-test.yaml` | `894828119087-compute@developer.gserviceaccount.com` (compute default) |
| `deploy-agents-runtime-prod` | ChatBotWhatsapp | `^main$` | `agents_runtime/cloudbuild.yaml` | (compute default) |
| `EvolutionWhatsapp-test` | EvolutionWhatsapp | `^test$` | (do repo EvolutionWhatsapp) | (compute default) |
| `EvolutionWhatsapp-prod` | EvolutionWhatsapp | `^main$` | (do repo EvolutionWhatsapp) | (compute default) |
| `deploy-whatsapp-agente-*` | **deletado 2026-07-21** (proxy consolidado em `agents-runtime`) | — | — | — |
| `chatbotwhatsapp-test` | **deletado 2026-07-21** (duplicado de `deploy-agents-runtime-test`) | — | — | — |

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
RAG_EMBEDDING_MODEL: "text-embedding-3-small"
RAG_EMBEDDING_DIM: "1536"
RAG_EMBEDDING_BASE_URL: "https://api.openai.com/v1/embeddings"
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
| `agents-runtime-sa-token` | Bearer para Portal chamarem `/chat` e `/proactive/send` |
| `evolution-api-key` | Evolution API |
| `agents-runtime-url` | URL do servico agents-runtime-test |
| ~~`whatsapp-agente-url`~~ | **Removido na Fase A** (proxy eliminado) |

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

# Webhook Evolution (publico, NAO requer SA token)
curl -X POST https://agents-runtime-test-XXX-uc.a.run.app/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event":"MESSAGES_UPSERT",
    "instance":"jennifer",
    "data":{
      "key":{"remoteJid":"5511966830020@s.whatsapp.net","fromMe":false,"id":"SMOKE_001"},
      "pushName":"Vinicius",
      "message":{"conversation":"oi smoke test"},
      "messageType":"conversation"
    }
  }'
# Resposta esperada: {"queued":true,"message_id":"<pubsub-msg-id>","request_id":"SMOKE_001"}
```

### Webhook Evolution (Fase A — 2026-07-21)

Apos a consolidacao da Fase A, a Evolution API aponta **diretamente** para
`agents-runtime-test/webhook`. O extrator canonico em
`agents_runtime/core/evolution_webhook.py` aceita:

- `MESSAGES_UPSERT` (UPPERCASE, formato padrao Evolution)
- `messages.upsert` (lowercase, aceita tambem para tolerancia)

E filtra:

- `fromMe=true` (echo do proprio bot)
- `@broadcast` (status do WhatsApp)
- Eventos nao-message (CONNECTION_UPDATE, QRCODE_UPDATED, etc)
- Mensagens sem phone/instance
- Tipos nao suportados (image/video/document sem texto)

### Gate da Fase B — áudio → Pub/Sub → RAG

A causa raiz corrigida foi o retorno antecipado quando o Whisper falhava sem texto alternativo. O runtime agora grava um marcador de auditoria mascarado no RAG e retorna a mensagem amigável sem armazenar áudio bruto.

Validação reproduzível em Python 3.12, com secrets externos neutralizados:

```powershell
[Environment]::SetEnvironmentVariable("GCP_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("GCLOUD_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("FIRESTORE_EMULATOR_HOST", "", "Process")
Remove-Item Env:DEEPSEEK_API_KEY,Env:NVIDIA_API_KEY,Env:MINIMAX_API_KEY,Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
python -m pytest -q tests/test_audio_pipeline_rag.py tests/test_phase_b_fixes.py
python -m pytest -q tests/
python -m ruff check core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/
python -m mypy --no-incremental --explicit-package-bases --follow-imports=silent core
python scripts/check_lgpd_compliance.py
```

Resultado do gate isolado: 17 testes específicos aprovados; suite geral com 249 aprovados e 9 ignorados; Ruff sem erros; mypy sem erros em 19 arquivos. Os 9 ignorados são testes de proatividade condicionados à allowlist vazia. O warning de tarefa RAG em shutdown foi separado como hardening da Fase C para não misturar escopos.

### Gate da Fase C — Hardening de Confiabilidade

A Fase C consolidou o trabalho em andamento (OAuth per-user, logging estruturado, evolution client, scripts LGPD, testes de Pub/Sub/webhook/oauth), fechou o `ResourceWarning` de event loop e ajustou os testes do cascade LLM para refletir a ordem vigente (`MiniMax-M2.7-highspeed -> MiniMax M3 -> DeepSeek V4 Flash`).

Validação reproduzível em Python 3.12, com secrets externos neutralizados:

```powershell
[Environment]::SetEnvironmentVariable("GCP_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("GCLOUD_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("FIRESTORE_EMULATOR_HOST", "", "Process")
Remove-Item Env:DEEPSEEK_API_KEY,Env:NVIDIA_API_KEY,Env:MINIMAX_API_KEY,Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
cd agents_runtime
python -m pytest -q tests/
python -m pytest -q tests/test_llm_provider.py tests/test_rag.py::TestOpenAIEmbeddingContract tests/test_structured_logging.py
python -m ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/
python -m mypy --no-incremental --explicit-package-bases --follow-imports=silent core
python scripts/check_lgpd_compliance.py
```

Resultado do gate isolado: 303 testes aprovados (10 ignorados pelo allowlist de proatividade); zero falhas, zero erros e zero warnings do projeto; Ruff sem erros; mypy sem erros em 25 arquivos; LGPD compliance check aprovado. As duas `DeprecationWarning` do `google._upb._message` (third-party protobuf 4.25) são filtradas via `pyproject.toml` por estarem fora do código do projeto.

### Gate da Fase D — OAuth per-user obrigatório

A Fase D removeu o fallback global `GOOGLE_OAUTH_TOKEN` nos 3 managers e propagou `phone` em todos os call-sites (`orchestrator`, `tools/ata_helper`, `ata_worker`, `proactive_worker`). A esteira `ata_worker` e `proactive_worker` agora itera por usuario.

Validacao reproduzivel em Python 3.12, com secrets externos neutralizados:

```powershell
[Environment]::SetEnvironmentVariable("GCP_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("GCLOUD_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("FIRESTORE_EMULATOR_HOST", "", "Process")
Remove-Item Env:DEEPSEEK_API_KEY,Env:NVIDIA_API_KEY,Env:MINIMAX_API_KEY,Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
cd agents_runtime
python -m pytest -q tests/
python -m pytest -q tests/test_google_calendar.py tests/test_google_drive.py tests/test_google_gmail.py tests/test_oauth_per_user.py
python -m ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/
python -m mypy --no-incremental --explicit-package-bases --follow-imports=silent core
python scripts/check_lgpd_compliance.py
```

Resultado do gate isolado: 312 testes aprovados (10 ignorados pelo allowlist de proatividade); zero falhas, zero erros e zero warnings do projeto; Ruff sem erros; mypy sem erros em 25 arquivos; LGPD compliance check aprovado. Nenhum dos 3 managers consulta mais `core.secrets.get_secret("GOOGLE_OAUTH_TOKEN")` — o caminho per-user via `core.oauth_per_user.get_user_credentials(phone)` e o unico suportado.

Para configurar os workers no ambiente `test`, defina `ATA_WORKER_PHONES` (CSV) e `PROACTIVE_WORKER_PHONES` (CSV) como variaveis de ambiente do Cloud Run Job.


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