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

## Testes

```bash
pytest -q                              # todos os testes
pytest tests/test_llm_provider.py -v   # especifico
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