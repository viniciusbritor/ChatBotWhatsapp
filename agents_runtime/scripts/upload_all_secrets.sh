#!/bin/bash
# Upload ALL secrets needed for omnichannel-agentes deployment.
# Run from agents_runtime/ directory.

set -e

PROJECT="${GCP_PROJECT:-coherence-ominichannel-fs}"
SECRETS_PREFIX=""

echo "========================================"
echo "Uploading secrets to $PROJECT"
echo "========================================"

upload() {
  local NAME="$1"
  local VALUE="$2"
  if [ -z "$VALUE" ]; then
    echo "  SKIP: $NAME (no value provided)"
    return 0
  fi
  echo "  UPLOAD: $NAME"
  echo -n "$VALUE" | gcloud secrets versions add "$NAME" \
    --project="$PROJECT" --data-file=- --quiet
}

# 1. LLM providers
# NOTE: MiniMax removido em 15/08/2026 — Fase N consolidou DeepSeek V4 Flash + Groq fallback.
upload "deepseek-api-key" "${DEEPSEEK_API_KEY}"
upload "nvidia-api-key" "${NVIDIA_API_KEY}"

# 2. Tools / External APIs
upload "serper-api-key" "${SERPER_API_KEY}"
upload "google-oauth-token" "${GOOGLE_OAUTH_TOKEN_PATH}"

# 3. Internal auth
upload "agents-runtime-sa-token" "${AGENTS_RUNTIME_SA_TOKEN:-$(openssl rand -hex 32)}"
upload "whatsapp-agente-url" "${WHATSAPP_AGENTE_URL:-https://whatsapp-agente-test-XXX-uc.a.run.app}"
upload "agents-runtime-url" "${AGENTS_RUNTIME_URL:-https://agents-runtime-test-XXX-uc.a.run.app}"
# whatsapp-agente-url removido em F6 (PT6) - proxy morto desde 23/07/2026

# 4. Evolution API (projeto whatsapp-server-fs)
echo ""
echo "----------------------------------------"
echo "Evolution API secrets (projeto whatsapp-server-fs):"
echo "----------------------------------------"
EVOLUTION_PROJECT="whatsapp-server-fs"
upload_to() {
  local PROJECT="$1"
  local NAME="$2"
  local VALUE="$3"
  if [ -z "$VALUE" ]; then
    echo "  SKIP: $NAME (no value)"
    return 0
  fi
  echo "  UPLOAD: $NAME to $PROJECT"
  echo -n "$VALUE" | gcloud secrets versions add "$NAME" \
    --project="$PROJECT" --data-file=- --quiet
}
upload_to "$EVOLUTION_PROJECT" "evolution-server-url" "${EVOLUTION_SERVER_URL:-https://evolution.coherenceai.com.br}"
upload_to "$EVOLUTION_PROJECT" "evolution-api-key" "${EVO_API_KEY:-jennifer_secret_2025}"
upload_to "$EVOLUTION_PROJECT" "evolution-database-uri" "${EVOLUTION_DATABASE_URI}"
upload_to "$EVOLUTION_PROJECT" "evolution-postgres-password" "${EVOLUTION_POSTGRES_PASSWORD}"
upload_to "$EVOLUTION_PROJECT" "evolution-postgres-user" "${EVOLUTION_POSTGRES_USER:-postgres}"

echo ""
echo "========================================"
echo "All secrets uploaded successfully"
echo "========================================"
echo ""
echo "Verify with:"
echo "  gcloud secrets list --project=$PROJECT | grep -E 'deepseek|nvidia|groq|serper|google-oauth|agents-runtime|whatsapp-agente'"
echo "  gcloud secrets list --project=$EVOLUTION_PROJECT | grep -E 'evolution'"