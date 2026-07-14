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

## Estado: Fase 1 (Fundacao)

Script `upload_secrets.sh` ja criado.
Estrutura de testes ja criada.

Proximas fases adicionam mais complexidade.