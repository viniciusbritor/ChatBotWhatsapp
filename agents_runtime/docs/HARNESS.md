# Harness — agents_runtime

> Instrucoes para executar, testar e deployar o `agents_runtime`.

> **Documento mestre:** [`ChatBotWhatsapp/docs/HARNESS.md`](../../HARNESS.md)

## Pre-requisitos

- Python 3.12+
- pip
- gcloud CLI (para deploy)
- Firestore (GCP ou emulator local)

## Variaveis de Ambiente (Local)

Copie `.env.runtime.test.yaml` para `.env` e ajuste conforme necessario.

## Setup Local

```bash
cd agents_runtime
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Com Firestore emulator
firebase emulators:start --only firestore --project coherence-ominichannel-fs

# Rodar
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## Setup Local com Firestore Emulator

```bash
# .env
FIRESTORE_EMULATOR_HOST=localhost:8080
GCLOUD_PROJECT=coherence-ominichannel-fs
ALLOW_PUBLIC_HEALTHZ=true
AGENTS_RUNTIME_SA_TOKEN_SECRET=local-dev-token-12345
```

## Audio local

```text
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_DOWNLOAD_ROOT=/app/whisper_models
AUDIO_MAX_BYTES=26214400
AUDIO_MAX_DURATION_SEC=300
AUDIO_DOWNLOAD_TIMEOUT_SEC=30
AUDIO_URL_ALLOWED_HOSTS=evolution.coherenceai.com.br
```

Regras de smoke test:

- Payload somente com `phone` e `extra.has_audio=true` e aceito.
- Base64 tem precedencia sobre URL.
- MIME fora da allowlist e rejeitado.
- Audio maior que o limite ou acima de 5 minutos e rejeitado.
- URL HTTP, host fora da allowlist, IP privado ou redirect e rejeitado.
- A transcricao e mascarada antes de chegar ao orchestrator.
- Nenhuma funcao Gemini participa do fluxo.

Testes locais:

```bash
pytest -q tests/test_audio_transcribe.py tests/test_main_audio.py tests/test_llm_provider.py
```

Resultado de 18/07/2026: 30 passed.

## Status operacional e estado conversacional

```text
AGENT_HEALTH_WINDOW_SEC=86400
PENDING_ACTION_TTL_SEC=300
RESPONSE_IDEMPOTENCY_TTL_SEC=86400
```

Smoke tests obrigatorios:

- `GET /admin/agents/status` retorna as mesmas categorias usadas no WhatsApp.

- "Quantos agentes estao funcionando?" nao chama LLM nem Web Manager.
- "Quais sao e o que eles fazem?" permanece na rota `runtime-status`.
- "Pesquise na internet" continua roteando para `manager-web`.
- "Sim" sem `pending_action` nao grava consentimento.
- Manager executado preserva `response_identity=Jennifer`.
- Agente removido desaparece apos reload bem-sucedido.

## Firestore Vector v2

```text
RAG_EMBEDDING_MODEL=embo-01
RAG_EMBEDDING_DIM=1536
RAG_SCHEMA_VERSION=2
RAG_MEMORY_COLLECTION=conversation-memory-v2
RAG_PRIVATE_COLLECTION=agent-knowledge-v2
RAG_SHARED_COLLECTION=public-knowledge-v2
RAG_RETENTION_DAYS=90
```

Regras operacionais:

- Nao misturar providers ou dimensoes na mesma collection.
- Criar os indices Firestore Vector antes do smoke test integrado.
- Reindexar o corpus quando modelo, dimensao ou schema mudar.
- Persistir apenas texto mascarado na memoria privada.
- O Firestore Emulator nao valida busca vetorial; usar mocks localmente e projeto GCP de teste para integracao.
- Validar o corpus sem escrita com `python scripts/migrate_rag_v2.py --dry-run`.
- Reindexar no projeto de teste somente depois da criacao dos indices com `python scripts/migrate_rag_v2.py`.

## Testes

```bash
pytest -q
pytest tests/test_rag.py -v
pytest tests/test_llm_provider.py -v
```

## Deploy (TEST)

```bash
git checkout test
git add -A
git commit -m "feat(phase-N): ..."
git push origin test
# Cloud Build dispara automaticamente
```

## Secrets (Upload)

```bash
./scripts/upload_secrets.sh deepseek-api-key "sk-..."
./scripts/upload_secrets.sh nvidia-api-key "nvapi-..."
./scripts/upload_secrets.sh minimax-api-key "eyJ..."
./scripts/upload_secrets.sh serper-api-key "..."
./scripts/upload_secrets.sh google-oauth-token "$(cat token.json)"
./scripts/upload_secrets.sh agents-runtime-sa-token "$(openssl rand -hex 32)"
./scripts/upload_secrets.sh evolution-api-key "..."
```

## Estado: Fase 7 (Completo)

Todas as 8 fases implementadas. 152 testes passando, 9 skipped.

### Servicos em Producao (TEST)

| Servico | URL |
|---|---|
| agents-runtime-test | `https://agents-runtime-test-c5nbfc5meq-uc.a.run.app` |
| whatsapp-agente-test | `https://whatsapp-agente-test-c5nbfc5meq-uc.a.run.app` |
| Evolution (Jennifer) | `https://evolution.coherenceai.com.br` (sem SSL ainda) |

### Secrets no GCP (`coherence-ominichannel-fs`)

| Secret | Env Var |
|---|---|
| `DEEPSEEK_API_KEY` | `DEEPSEEK_API_KEY` |
| `NVIDIA_API_KEY` | `NVIDIA_API_KEY` |
| `MINIMAX_API_KEY` | `MINIMAX_API_KEY` |
| `minimax-group-id` | `MINIMAX_GROUP_ID` |
| `serper-api-key` | `SERPER_API_KEY` |
| `google-oauth-token` | `GOOGLE_OAUTH_TOKEN` |
| `agents-runtime-sa-token` | `AGENTS_RUNTIME_SA_TOKEN_SECRET` |
| `google-maps-api-key` | `GOOGLE_MAPS_API_KEY` |
| `youtube-api-key` | `YOUTUBE_API_KEY` |
| `oauth-client-secret` | `OAUTH_CLIENT_SECRET` |

### Troubleshooting

| Sintoma | Causa Provavel | Solucao |
|---|---|---|
| "Nenhum orchestrator disponivel" | Cache de agentes vazio (cold start ou Firestore vazio) | `seed_default_data()` agora cobre esse caso — aguardar ate 120s ou verificar Firestore |
| `/healthz` retorna 404 | Bug de infra do Cloud Run (Google Front End) | Usar `GET /` como health check — retorna `{"service":"agents_runtime"}` |
| Webhook nao recebe mensagens | Evolution webhook URL desatualizada | Verificar `webhook/find/Jennifer` na Evolution API |
| Jennifer responde generica | LLM cascade sem chaves reais | Verificar secrets `DEEPSEEK_API_KEY`, `NVIDIA_API_KEY`, `MINIMAX_API_KEY` |