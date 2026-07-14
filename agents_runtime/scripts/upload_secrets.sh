#!/bin/bash
# Upload secret to GCP Secret Manager using `versions add` (NOT `update`).
# Validates UTF-8 encoding to prevent the bug from 12/07/2026.
#
# Usage: ./upload_secrets.sh <secret-name> <value>
# Example: ./upload_secrets.sh deepseek-api-key "sk-abc123"

set -e

PROJECT="${GCP_PROJECT:-coherence-ominichannel-fs}"
SECRET_NAME="$1"
VALUE="$2"

if [ -z "$SECRET_NAME" ] || [ -z "$VALUE" ]; then
  echo "Usage: $0 <secret-name> <value>"
  echo "Example: $0 deepseek-api-key 'sk-...'"
  exit 1
fi

echo "[upload_secrets] Project: $PROJECT"
echo "[upload_secrets] Secret:  $SECRET_NAME"

if ! echo -n "$VALUE" | iconv -f UTF-8 -t UTF-8 > /dev/null 2>&1; then
  echo "[upload_secrets] ERRO: valor nao e UTF-8 valido"
  exit 1
fi

if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" > /dev/null 2>&1; then
  echo "[upload_secrets] Secret existe, adicionando nova versao..."
  echo -n "$VALUE" | gcloud secrets versions add "$SECRET_NAME" \
    --project="$PROJECT" \
    --data-file=- \
    --replication-policy=automatic
else
  echo "[upload_secrets] Criando novo secret..."
  echo -n "$VALUE" | gcloud secrets create "$SECRET_NAME" \
    --project="$PROJECT" \
    --data-file=- \
    --replication-policy=automatic
fi

echo "[upload_secrets] OK"