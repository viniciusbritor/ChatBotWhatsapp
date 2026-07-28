#!/usr/bin/env bash
# Verifica que o build mais recente do Cloud Build para o branch test
# esta em status SUCCESS. Falha com codigo 1 se estiver FAILED, PENDING
# ou nao existir.
#
# Uso:
#   ./scripts/check_build_status.sh
#   ./scripts/check_build_status.sh <branch>
#   ./scripts/check_build_status.sh <branch> 5     # ultimos 5 builds
#
# Variaveis de ambiente:
#   PROJECT      GCP project (default: coherence-ominichannel-fs)
#   BRANCH       branch to filter (default: test)
#   MIN_WAIT     seconds to wait for the build (default: 60)
#   POLL         seconds between polls (default: 10)

set -euo pipefail

PROJECT="${PROJECT:-coherence-ominichannel-fs}"
BRANCH="${1:-${BRANCH:-test}}"
LIMIT="${2:-1}"
MIN_WAIT="${MIN_WAIT:-60}"
POLL="${POLL:-10}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud not found in PATH" >&2
  exit 2
fi

echo "Project: ${PROJECT}"
echo "Branch:  ${BRANCH}"
echo "Limit:   ${LIMIT} build(s)"

# Tenta usar a SA admin-omnichannel para ter permissao ampla
SA="admin-omnichannel@${PROJECT}.iam.gserviceaccount.com"
if gcloud config get-value auth/impersonate_service_account 2>/dev/null | grep -q "@"; then
  echo "Impersonation: already configured"
else
  if gcloud config set auth/impersonate_service_account "${SA}" 2>/dev/null; then
    echo "Impersonation: ${SA}"
  else
    echo "Impersonation: failed (continuing with active user)"
  fi
fi

wait_for_build() {
  local elapsed=0
  while [[ "${elapsed}" -lt "${MIN_WAIT}" ]]; do
    local status_json
    status_json=$(gcloud --project="${PROJECT}" builds list \
      --limit="${LIMIT}" \
      --format='value(id,status,createTime,sourceProvenance.resolvedRepoSource.commitSha,sourceProvenance.resolvedRepoSource.branchName)' 2>/dev/null) || return 1
    if [[ -n "${status_json}" ]]; then
      echo "${status_json}"
      return 0
    fi
    sleep "${POLL}"
    elapsed=$((elapsed + POLL))
  done
  return 1
}

raw="$(wait_for_build || true)"
if [[ -z "${raw}" ]]; then
  echo "FAIL: no build found for branch '${BRANCH}' in project '${PROJECT}'"
  echo "Check that the push actually triggered Cloud Build."
  exit 1
fi

echo "---"
echo "Most recent build(s):"
echo "${raw}" | head -n "${LIMIT}"

# Parse status (4th field in gcloud output: id status createTime commit branch)
# We expect format: <id> <STATUS> <createTime> <commit> <branch>
first_line="$(echo "${raw}" | head -n 1)"
status="$(echo "${first_line}" | awk '{print $2}')"
build_id="$(echo "${first_line}" | awk '{print $1}')"

echo "---"
echo "Build ID:  ${build_id}"
echo "Status:    ${status}"

case "${status}" in
  SUCCESS)
    echo "OK: build is SUCCESS"
    exit 0
    ;;
  FAILURE|TIMEOUT|INTERNAL_ERROR|CANCELLED|EXPIRED)
    echo "FAIL: build status is ${status}"
    echo "Run: gcloud --project=${PROJECT} builds log ${build_id}"
    echo "  or open: https://console.cloud.google.com/cloud-build/builds/${build_id}?project=${PROJECT}"
    exit 1
    ;;
  QUEUED|WORKING|PENDING)
    echo "FAIL: build still in progress (${status})"
    echo "Wait for it to complete and re-run this script."
    exit 1
    ;;
  *)
    echo "FAIL: unknown status '${status}'"
    exit 1
    ;;
esac
