#!/bin/bash
# Deploy end-to-end script.
# - git init each repo (if not already)
# - switch to `test` branch
# - push to remote (triggers Cloud Build)
#
# PREREQUISITE: Configure git remotes first.
#   cd agents_runtime && git remote add origin <URL>
#   cd WhatsappAgente && git remote add origin <URL>
#   cd Coherence_Portal && git remote add origin <URL>
#
# Cloud Build triggers must be configured to deploy on push to `test`.

set -e

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
BRANCH="${BRANCH:-test}"
COMMIT_MSG="${COMMIT_MSG:-deploy: omnichannel-agentes complete + Evolution IP 34.95.181.124 + master phone +5511966830020}"

REPOS=("agents_runtime" "WhatsappAgente" "Coherence_Portal")
REPO_PATHS=(
  "$WORKSPACE_ROOT/ChatBotWhatsapp/agents_runtime"
  "$WORKSPACE_ROOT/WhatsappAgente"
  "$WORKSPACE_ROOT/Coherence_Portal"
)

for i in "${!REPOS[@]}"; do
  REPO="${REPOS[$i]}"
  PATH_REPO="${REPO_PATHS[$i]}"

  if [ ! -d "$PATH_REPO" ]; then
    echo "SKIP: $REPO (path $PATH_REPO not found)"
    continue
  fi

  echo ""
  echo "=========================================="
  echo "Deploying $REPO ($PATH_REPO)"
  echo "=========================================="

  cd "$PATH_REPO"

  if [ ! -d .git ]; then
    echo "  git init"
    git init -q
    git branch -m main 2>/dev/null || true
  fi

  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
  if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo "  git checkout -b $BRANCH (from $CURRENT_BRANCH)"
    git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
  fi

  echo "  git add -A"
  git add -A

  if git diff --cached --quiet; then
    echo "  No changes to commit"
  else
    echo "  git commit"
    git commit -m "$COMMIT_MSG"
  fi

  if git remote get-url origin >/dev/null 2>&1; then
    echo "  git push origin $BRANCH"
    git push origin "$BRANCH" --set-upstream
    echo "  Cloud Build trigger should deploy shortly"
  else
    echo "  SKIP push (no remote configured)"
    echo "  Configure with: git remote add origin <YOUR_REPO_URL>"
  fi
done

echo ""
echo "=========================================="
echo "Deploy complete. Check:"
echo "  gcloud builds list --project=coherence-ominichannel-fs --limit=5"
echo "=========================================="