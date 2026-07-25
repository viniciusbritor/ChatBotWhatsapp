# Harness do Projeto — ChatBotWhatsapp

> **Ambiente Operacional:** Instrucoes para configurar, executar e depurar o modulo `omnichannel-agentes` + servico `agents_runtime`.

> **Diagrama visual ponta a ponta:** [`ARQUITETURA.md`](./ARQUITETURA.md#0-diagrama-visual-ponta-a-ponta).
> O diagrama mostra o caminho `WhatsApp → Evolution → Cloud Run →
> Pub/Sub → Orchestrator → Evolution → resposta` com Firestore plain
> para histórico de chat e Firestore Vector restrito a documentos.

> **Importante — Evolution API 23/07/2026:** o instance name
> (`INSTANCE=Jennifer`) é case-sensitive. O container resolve
> dinamicamente via `GET /instance/fetchInstances` antes de cada
> chamada. O endpoint de tick azul é o v1 singular
> `POST /chat/markMessageAsRead/{instance}` com payload v2
> `readMessages: [{id, fromMe, remoteJid}]`. Não usar o plural
> `markMessagesAsRead` — esta versão da Evolution retorna 404.

> **Importante — Orquestracao LangGraph 23/07/2026:** a partir da Fase H,
> a orquestração interna usa um grafo `StateGraph` definido em
> `agents_runtime/agent_orchestration/graph.py`. Jennifer e o agente
> mestre; `access_guardian` e o subagente que valida owner + OAuth + scopes
> antes de cada tool Google. Tools Google podem confiar que o guard já
> autorizou. O guard determinístico `core.owner_guard` foi descontinuado.

## GCP Project & Recursos

- **Project:** `coherence-ominichannel-fs`
- **Region:** `us-central1`
- **Service Account operacional do projeto (Guardrail 59 — vigente 25/07/2026):**
  - **SA obrigatória:** `admin-omnichannel@coherence-ominichannel-fs.iam.gserviceaccount.com`.
  - Esta SA e usada por todos os Cloud Build triggers, deploys de Cloud Run, jobs de Cloud Run e scripts locais de manutencao (upload de secrets, Firestore ops, refresh de OAuth per-user).
  - **Nunca usar `894828119087-compute@developer.gserviceagent.com** ou outras SAs default — foram criadas pelo Cloud Build para subir imagens de build (Docker layer cache, Cloud Build service agent), nao para deploy/runtime.
  - Para impersonar localmente: `gcloud config set auth/impersonate_service_account admin-omnichannel@coherence-ominichannel-fs.iam.gserviceaccount.com`. Para revogar: `gcloud config unset auth/impersonate_service_account`.
  - Concessor necessario: o usuario que impersona precisa de `roles/iam.serviceAccountTokenCreator` no escopo da SA. Sem isso, `gcloud ...` retorna `PERMISSION_DENIED: Failed to impersonate`.
- **Isolamento contra projetos vizinhos (Guardrail 60 — vigente 25/07/2026):**
  - **Nada neste repo pode referenciar `coherence-18-plus` ou seu OAuth client.** Aquele projeto hospeda o produto 18+ e tem client/secret totalmente separados.
  - O arquivo `Keys/coherence18plus_oauth_credentials.json` e de outro projeto e NAO deve ser usado aqui — usar apenas `Secrets/google-oauth-token` do projeto `coherence-ominichannel-fs` (client_id `894828119087-...apps.googleusercontent.com`).
  - Verificacao periodica: `grep -ri "coherence-18-plus\|coherence18plus\|410168162390" agents_runtime/ docs/` deve retornar 0 matches.
- **Servicos Cloud Run (DEV / TEST - Scale to Zero Mandatory):**
  - `agents-runtime-test` (2Gi, min=0, max=3, cpu-throttling=true) — ambiente de dev do ChatBotWhatsapp (recebe webhook do Evolution em dev, processa com LLM, retorna resposta)
  - `agents-runtime-prod` — **DELETADO (22/07/2026)** para eliminar duplicidades e custos
  - `coherence-portal` (2Gi, min=0, cpu-throttling=true) — UI do Portal (PROD mobilizado, escala sob demanda)
  - `coherence-portal-test` (2Gi, min=0, cpu-throttling=true) — UI do Portal em homologacao
- **Governança de Custos (Guardrail 57):**
  - É proibido usar `--no-cpu-throttling` (`CPU-THROTTLING: false`) ou `minScale > 0` em ambientes de desenvolvimento ou teste.
  - Todos os serviços Cloud Run devem estar configurados com `minScale: 0` e `cpu-throttling: true` para zerar custos quando ociosos.
- **Jobs Cloud Run:**
  - `ata-worker-test` (geracao de atas)
  - `proactive-worker-test` (mensagens proativas)
- **Pub/Sub topics:**
  - `chatbotwhatsapp-messages` (webhook → agents-runtime; unico topico ativo)
  - `chatbotwhatsapp-dlq` (DLQ nativa para retries > 5)
  - `whatsapp-messages` / `whatsapp-messages-dlq` (legado; service `whatsapp-agente` foi deletado em 23/07/2026 — topicos podem ser removidos na proxima janela)


## Arquitetura consolidada (2026-07-23 — Fase H)

O projeto `viniciusbritor/ChatBotWhatsapp` contém **apenas** o serviço de agentes. O proxy Evolution foi consolidado dentro do próprio `agents-runtime` via endpoint `POST /webhook` que publica no Pub/Sub `chatbotwhatsapp-messages`. A idempotencia e feita por ledger Firestore (`message-processing/{message_id}`) e o retry do Pub/Sub e 503-only.

A partir de 23/07/2026 (Fase H) a orquestração interna usa um grafo
**LangGraph** (`agent_orchestration.graph`) onde Jennifer e o agente mestre
e `access_guardian` e o subagente que decide owner + OAuth + scopes antes
de cada tool Google:

```
Celular
  ↕ (audio/texto)
Evolution API (projeto EvolutionWhatsapp, repo separado)
  ↕ (webhook POST https://agents-runtime-test-...a.run.app/webhook)
agents-runtime-test (Cloud Run, projeto ChatBotWhatsapp)
  - webhook valida payload, sintetiza message_id deterministico,
    registra no ledger e marca mensagem como lida na Evolution
  ↕ (POST /webhook → publish chatbotwhatsapp-messages)
Pub/Sub chatbotwhatsapp-messages
  ↕ (push subscription agents-runtime-consumer → /pubsub/push)
agents-runtime-test (POST /pubsub/push, ledger claim, orchestrate)
  ↕ (LangGraph: jennifier_node -> classify_intent -> guard_node -> manager -> reply)
  ↕ (access_guardian: resolve owner + check google_oauth_token + check scopes)
  ↕ (Whisper local; fallback Gemini 2.5 Flash somente sob consentimento)
  ↕ (LLM cascade MiniMax M2.7-highspeed -> Gemini 2.5 Flash)
Evolution /message/sendText + /chat/markMessagesAsRead
  ↕ (resposta + tick azul)
Celular
```

Os repos `viniciusbritor/EvolutionWhatsapp` (hospeda o Evolution API) e `viniciusbritor/ChatBotWhatsapp` (hospeda o agents-runtime) são **separados** e **independentes**.

## CI/CD (Cloud Build triggers)

> **Modo operacional vigente (25/07/2026):** o trigger
> `deploy-agents-runtime-test` está **ativo** (2nd-gen, região
> `us-central1`). O fluxo correto para deploy em test é:
> `git commit` → `git push origin test` → trigger dispara automaticamente.
> **É proibido executar `gcloud builds submit` manualmente** — ver
> GUARDRAILS.md §10.

| Trigger | Geração | Repo | Branch | Build config | Região | Status |
|---|---|---|---|---|---|---|
| `deploy-agents-runtime-test` | 2nd-gen | ChatBotWhatsapp | `^test$` | `agents_runtime/cloudbuild-test.yaml` | `us-central1` | **ativo** |
| `deploy-agents-runtime-prod` | (a criar) | ChatBotWhatsapp | `^main$` | `agents_runtime/cloudbuild-prod.yaml` | `us-central1` | pendente |
| `EvolutionWhatsapp-test` | 1st-gen | EvolutionWhatsapp | `^test$` | (do repo EvolutionWhatsapp) | global | monitorar |
| `EvolutionWhatsapp-prod` | 1st-gen | EvolutionWhatsapp | `^main$` | (do repo EvolutionWhatsapp) | global | monitorar |
| `deploy-monitoria-whisper-worker` | 1st-gen | `Monitoria_Chamadas` | `^test$` | (externo, fora de escopo) | global | **não modificar** |
| `deploy-monitoria-worker-prod` | 1st-gen | `Monitoria_Chamadas` | `^main$` | (externo, fora de escopo) | global | **não modificar** |
| `deploy-monitoria-prod` | 1st-gen | `Monitoria_Chamadas` | `^main$` | (externo, fora de escopo) | global | **não modificar** |

> **Conexão 2nd-gen:** o trigger `deploy-agents-runtime-test` usa a
> connection `github-connection` (installation ID `138074470`) com o
> repositório `chat-bot-whatsapp` vinculado. A 1st-gen usa o GitHub App
> legado que está instalado apenas no `Monitoria_Chamadas`.

> ⚠️ **Repositórios de Monitoria fora de escopo.** Não tocar nos triggers
> de `Monitoria_Chamadas`; mudanças precisam passar pela coordenação do
> respectivo repositório.

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
# Historico de mensagens SEMPRE em Firestore plain (sem embedding).
RAG_MESSAGE_HISTORY_COLLECTION: "message-history"
RAG_MESSAGE_HISTORY_RETENTION_DAYS: "365"
# Firestore Vector: SOMENTE para documentos (livros, editais, publico).
RAG_PRIVATE_COLLECTION: "agent-knowledge-v2"
RAG_COLLECTIVE_COLLECTION: "collective-knowledge-v2"
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

> ⚠️ Todas as triggers abaixo foram **pausadas** em 23/07/2026 para
> evitar execuções caras durante a fase de estabilização. A reativação
> é responsabilidade do operador após validação local. Triggers legadas
> `ping-whatsapp-agente`, `agents-runtime-ping` e qualquer referência
> ao serviço `whatsapp-agente-test` foram **removidas** (o serviço
> legado foi deletado).

| Job | Frequencia original | Acao | Status atual |
|---|---|---|---|
| `ata-worker-trigger` | `*/10 * * * *` | Chama `ata-worker-test` | pausado |
| `proactive-worker-events-trigger` | `*/15 * * * *` | Chama `proactive-worker-test` (eventos Calendar) | pausado |
| `proactive-worker-topics-trigger` | `0 8 * * 2,5` | Chama `proactive-worker-test` (terca + sexta 8h BRT) | pausado |
| `ping-agents-runtime` | `*/5 * * * *` | GET `/healthz` em agents-runtime-test | pausado |
| `ping-whatsapp-agente` | `*/5 * * * *` | GET `/healthz` em whatsapp-agente-test | **deletado** (serviço removido) |
| `group-sync-trigger` | `0 */6 * * *` | Sincroniza membros dos grupos via Evolution API | pausado |
| `proactive-weekly-eval` | `0 20 * * 0` | Auto-avaliacao semanal (domingo 20h BRT) | pausado |
| `history-cleanup` | `0 3 * * *` | Limpa historico e `conversation-memory-v2` expirados ha mais de 90 dias | pausado |

## Estrutura de Diretorios

```
ChatBotWhatsapp/
├── docs/                              # documentacao canonica (raiz)
│   ├── ARQUITETURA.md                 # visao geral
│   ├── HARNESS.md                     # este arquivo
│   ├── GUARDRAILS.md                  # regras inegociaveis
│   ├── DIARIO_BORDO.md                # historico cronologico
│   ├── PRIVACIDADE.md                 # politica LGPD
│   └── TERMOS.md                      # termos de uso
└── agents_runtime/                    # runtime FastAPI
    ├── main.py                        # webhook / /pubsub/push / /admin/*
    ├── orchestrator.py                # roteamento Jennifer + tool loop legacy
    ├── agent_loader.py                # snapshot Firestore
    ├── deepagent_layer/               # DeepAgents harness (Fase L)
    │   ├── tools.py                   # LangChain @tool wrappers
    │   ├── agents.py                  # factory + cache
    │   └── __init__.py                # export público
    ├── core/
    │   ├── auth.py
    │   ├── evolution_client.py        # sendText + markMessagesAsRead
    │   ├── evolution_webhook.py        # extrator canonico
    │   ├── message_ledger.py           # idempotencia Firestore
    │   ├── pubsub_dispatcher.py        # lease + retry transitorio
    │   ├── pubsub_publisher.py         # publish chatbotwhatsapp-messages
    │   ├── pubsub_consumer.py          # shim de compatibilidade
    │   ├── audio_transcribe.py         # Whisper + Gemini fallback
    │   ├── owner.py / owner_guard.py  # guard Gmail/Drive/Calendar
    │   ├── module_ui.py                # painel /admin/dashboard
    │   ├── rag.py                      # embeddings OpenAI
    │   ├── llm_provider.py
    │   ├── oauth_per_user.py           # tokens OAuth Google
    │   ├── masker.py / logging.py / secrets.py / ...
    ├── tools/
    │   ├── google_gmail.py / google_drive.py / google_calendar.py
    │   ├── audio_transcribe.py / web_search.py / nickname.py ...
    ├── ata_worker/  proactive_worker/
    ├── tests/   scripts/   Dockerfile   cloudbuild-test.yaml
    └── requirements.txt
```

> A copia em `agents_runtime/docs/` foi removida em 22/07/2026 para
> eliminar fonte única de verdade desatualizada. Documentação canônica
> fica somente em `docs/` na raiz.

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

> Trigger `deploy-agents-runtime-test` está **ativo** (2nd-gen, `us-central1`).
> O deploy é automático no push para a branch `test`. NÃO usar
> `gcloud builds submit` — viola GUARDRAILS.md §10.

Fluxo aprovado:

```bash
cd C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp
git checkout test
git add -A
git commit -m "feat(scope): descricao"
git push origin test
# O trigger deploy-agents-runtime-test dispara automaticamente
# Acompanhar: gcloud builds list --region=us-central1 --limit=3
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

### Gate da Fase E — privacy-guard testado + deploy agent-proatividade

A Fase E fechou a cobertura do `agent-privacy-guard` no orchestrator e removeu a dependencia obsoleta `GOOGLE_OAUTH_TOKEN` do job `proactive-worker-test`. O LGPD compliance check agora exige os 3 Dockerfiles (agents-runtime, ata_worker, proactive_worker).

Validacao reproduzivel em Python 3.12, com secrets externos neutralizados:

```powershell
[Environment]::SetEnvironmentVariable("GCP_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("GCLOUD_PROJECT", "", "Process")
[Environment]::SetEnvironmentVariable("FIRESTORE_EMULATOR_HOST", "", "Process")
Remove-Item Env:DEEPSEEK_API_KEY,Env:NVIDIA_API_KEY,Env:MINIMAX_API_KEY,Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
cd agents_runtime
python -m pytest -q tests/
python -m pytest -q tests/test_orchestrator.py::TestPrivacyGuard
python -m ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/
python -m mypy --no-incremental --explicit-package-bases --follow-imports=silent core
python scripts/check_lgpd_compliance.py
```

Resultado do gate isolado: 316 testes aprovados (10 ignorados); zero falhas, zero erros e zero warnings; Ruff sem erros; mypy sem erros em 25 arquivos; LGPD compliance check aprovado. `cloudbuild-proactive-test.yaml` NAO referencia mais `GOOGLE_OAUTH_TOKEN`. Os 4 testes do `TestPrivacyGuard` cobrem: grupo sem confirmacao (pending_action), grupo com confirmacao (executa agent), privado (executa agent) e unregistered user (link Portal).

Para deploy do `proactive-worker-test` no GCP via Cloud Scheduler:
1. Buildar via `cloudbuild-proactive-test.yaml` no push em `test`.
2. Provisionar Cloud Scheduler jobs: `*/15 * * * *` para `python proactive_worker/main.py --mode events`; `0 8 * * 2,5` (Tue+Fri 8h BRT) para `python proactive_worker/main.py --mode topics`.
3. Definir `PROACTIVE_WORKER_PHONES` no Cloud Run env (CSV dos telefones elegiveis).


```bash
cd agents_runtime
pytest -q                                  # backend
```

## Autenticação e Segredos

- **Local dev:** `.env` (gitignored) + fallback para `secrets_manager.py`
- **Cloud Run:** `--set-secrets` em `cloudbuild.yaml` referencia segredos do Secret Manager
- **Nunca:** hardcoded keys em código (regra global + GUARDRAILS)

### Lista de secrets ativos (23/07/2026)

| Secret | Consumer | Status |
|---|---|---|
| `OPENAI_API_KEY` | `agents-runtime` (embeddings RAG) | ativo |
| `agents-runtime-url` | marcado para revisao (Cloud Run identity) | ativo |
| `OAUTH_CLIENT_SECRET` | `agents-runtime` (OAuth per-user) | ativo |
| `OAUTH_STATE_SECRET` | `agents-runtime` (HMAC state) | ativo |
| `PROACTIVE_WORKER_PHONES` | `proactive-worker` (CSV) | ativo |
| `ATA_WORKER_PHONES` | `ata-worker` (CSV) | ativo |
| `evolution-api-key` | `agents-runtime` (envio de mensagens) | **necessita key real** (nao foi exposta) |
| `google-maps-api-key` | `agents-runtime` (locomotion tool) | ativo |
| `youtube-api-key` | `agents-runtime` (youtube tool) | ativo |
| `serper-api-key` | `agents-runtime` (web search) | ativo |
| `GEMINI_API_KEY` | `agents-runtime` (fallback STT somente sob consentimento) | ativo |
| `DEEPSEEK_API_KEY` | LLM cascade (1º recurso apos MiniMax M2.7) | **versao bloqueada — aguardando nova key** |
| `MINIMAX_API_KEY` | LLM cascade (MiniMax-M2.7 highspeed → M3) | **versao bloqueada — aguardando nova key** |
| `NVIDIA_API_KEY` | cascade LLM (legado) | **versao bloqueada — aguardando nova key** |
| `agents-runtime-sa-token` | Bearer SA | **versao bloqueada — aguardando nova key** |

> ⚠️ As chaves com "versao bloqueada" foram desabilitadas no
> Secret Manager após o commit `0a3d6ed` ter exposto o conteúdo
> em `secret_*.txt` e `sa_token.txt` no historico do Git. Para
> reativar, adicione uma nova versao e (se quiser a versao antiga
> tambem) execute `gcloud secrets versions enable N --secret=…`.

### Lista de secrets orfaos (cleanup pendente)

| Secret | Motivo | Procedure |
|---|---|---|
| `whatsapp-agente-url` | URL do `whatsapp-agente` (servico legacy deletado em 23/07/2026) | `gcloud secrets delete whatsapp-agente-url --project=coherence-ominichannel-fs` (proxima janela) |
| `agents-runtime-sa-token-clean` | Duplicata de `agents-runtime-sa-token` | `gcloud secrets delete agents-runtime-sa-token-clean …` (proxima janela) |
| `google-oauth-token` | OAuth global removido na Fase D | deletar quando seguro |

### Troubleshooting OAuth per-user

Sintoma: `RuntimeError("user_google_oauth_required")` no log do Cloud Run.

Checklist:
1. Verificar se o usuario concluiu o fluxo `/oauth/google`:
   ```powershell
   gcloud firestore documents get users/<phone>/google_oauth --project=coherence-ominichannel-fs
   ```
2. Se o campo nao existe, redirecionar o usuario para a URL gerada por
   `core.oauth_per_user.create_oauth_state(phone)` (ver `docs/fases/fase_F/oauth_setup.md`).
3. Se o token esta expirado e o refresh falha, verificar `OAUTH_CLIENT_SECRET`
   no Secret Manager.
4. Se o refresh falha com `invalid_grant`, o `refresh_token` foi revogado pelo
   usuario; repetir o fluxo `/oauth/google`.

Sintoma: `oauth refresh failed: ...` em loop.

Verificar se `OAUTH_CLIENT_SECRET` bate com o valor configurado no
Google Cloud Console.

Sintoma: prefetch retorna `None` para Calendar/Email/Drive.

Verificar se `core.oauth_per_user.get_user_credentials(phone)` retorna
`Credentials` valido. Logs do `_prefetch_*` devem mostrar `"Prefetch X failed: ..."`.

### Pub/Sub retry policy (Guardrail 57 + 58)

**Regra absoluta**: `/pubsub/push` **NUNCA** retorna HTTP 500 para evitar retry-storm.

| Cenario | Resposta | delivered | Log |
|---|---|---|---|
| `send_text` ok | 200 | true | INFO |
| `send_text` falha (Evolution offline) | **200** | false | WARNING `pubsub send_text_skipped` |
| `phone` vazio (payload stale) | **200** | false | WARNING `pubsub reply_dropped_empty_phone` |
| Orchestrator crasha / OOM | 500 | - | (retry legitimo) |

**Por que 200 e nao 500**: Pub/Sub reentrega qualquer mensagem que recebe
status 5xx. Se o Cloud Run retorna 500 (mesmo que por motivo justificado),
o Pub/Sub reentrega ate 5 vezes, multiplicando custo por 5x. Para
`send_text` ou payload invalido, nao ha beneficio de reentregar — a falha
se repete identicamente.

**Configuracao obrigatoria em toda subscription Pub/Sub**:

```powershell
gcloud pubsub subscriptions update <NAME> `
    --dead-letter-topic=projects/coherence-ominichannel-fs/topics/whatsapp-messages-dlq `
    --max-delivery-attempts=5
```

(Pub/Sub exige minimo 5; valor menor e rejeitado pela API.)

**Diagnostico de custo suspeito**: se requests /pubsub/push > 200/dia
para um chatbot com ~100 msgs/dia, ha retry-storm. Auditar:

```powershell
gcloud --project=coherence-ominichannel-fs logging read "resource.type=cloud_run_revision AND resource.labels.service_name=agents-runtime-test AND httpRequest.requestUrl:'/pubsub/push'" --limit=50000 --format='value(timestamp,httpRequest.status)' --freshness=24h | Measure-Object -Line
```

>2000 requests/dia = bug. Investigar logs WARNING `pubsub send_text_skipped` ou `pubsub reply_dropped_empty_phone`.

**Caso real (22/07/2026)**: 9.071 requests /pubsub/push em 24h geraram
~$0.91/dia SO em reentregas. Root cause: mensagens antigas (publicadas
antes do OAuth per-user) reentregadas em loop. Fix: skip de send_text
quando phone vazio + return 200 + log warning (commit `bdda61f`).

### Procedures externas (Fase F)

- `docs/fases/fase_F/oauth_setup.md` — configuracao do OAuth Client no Google
  Cloud Console e execucao manual do fluxo.
- `docs/fases/fase_F/cleanup_secrets.md` — delecao de secrets orfaos.
- `docs/fases/fase_F/cleanup_repo.md` — delecao da pasta local e do repo
  GitHub legados.

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
- `docs/fases/fase_F/` — procedures de cleanup e OAuth (Fase F)
- `docs/fases/fase_{A,B,C,D,E}/` — historico das fases anteriores