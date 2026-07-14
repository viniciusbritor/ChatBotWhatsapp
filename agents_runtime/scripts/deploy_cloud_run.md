# Cloud Run Services

## Services to deploy

| Service | Region | CPU | Memory | Min/Max | Image |
|---|---|---|---|---|---|
| `agents-runtime-test` | us-central1 | 2 | 2Gi | 0/3 | `gcr.io/coherence-ominichannel-fs/agents-runtime:$COMMIT_SHA` |
| `whatsapp-agente-test` | us-central1 | 1 | 1Gi | 0/2 | `gcr.io/coherence-ominichannel-fs/whatsapp-agente:$COMMIT_SHA` |

## Jobs (Cloud Run Jobs)

| Job | Schedule | CPU | Memory | Timeout |
|---|---|---|---|---|
| `ata-worker-test` | `*/10 * * * *` | 2 | 2Gi | 600s |
| `proactive-worker-test` | `*/15 * * * *` | 1 | 1Gi | 300s |
| `lgpd-cleanup-test` | `0 3 * * *` | 1 | 1Gi | 300s |

## Cloud Scheduler Triggers

```bash
# WhatsApp Agent Ping (warm)
gcloud scheduler jobs create http whatsapp-agente-ping \
  --location=us-central1 \
  --schedule="*/5 * * * *" \
  --uri="https://whatsapp-agente-test-XXX-uc.a.run.app/healthz" \
  --http-method=GET

# Agents Runtime Ping (warm)
gcloud scheduler jobs create http agents-runtime-ping \
  --location=us-central1 \
  --schedule="*/5 * * * *" \
  --uri="https://agents-runtime-test-XXX-uc.a.run.app/healthz" \
  --http-method=GET \
  --headers="Authorization=Bearer $SA_TOKEN"

# Ata Worker (cron a cada 10min)
gcloud scheduler jobs create http ata-worker-trigger \
  --location=us-central1 \
  --schedule="*/10 * * * *" \
  --uri="https://southamerica-east1-run.googleapis.com/google.cloud.run/v1/namespaces/coherence-ominichannel-fs/jobs/ata-worker-test:run" \
  --http-method=POST \
  --oauth-service-account-email=894828119087-compute@developer.gserviceaccount.com

# Proactive Worker (cron a cada 15min)
gcloud scheduler jobs create http proactive-worker-trigger \
  --location=us-central1 \
  --schedule="*/15 * * * *" \
  --uri="https://southamerica-east1-run.googleapis.com/google.cloud.run/v1/namespaces/coherence-ominichannel-fs/jobs/proactive-worker-test:run" \
  --http-method=POST \
  --oauth-service-account-email=894828119087-compute@developer.gserviceaccount.com

# Proactive Topics (terca + sexta 8h BRT)
gcloud scheduler jobs create http proactive-topics-trigger \
  --location=us-central1 \
  --schedule="0 8 * * 2,5" \
  --uri="https://southamerica-east1-run.googleapis.com/google.cloud.run/v1/namespaces/coherence-ominichannel-fs/jobs/proactive-worker-test:run?topics=true" \
  --http-method=POST \
  --oauth-service-account-email=894828119087-compute@developer.gserviceaccount.com

# Group Sync (cada 6h)
gcloud scheduler jobs create http group-sync-trigger \
  --location=us-central1 \
  --schedule="0 */6 * * *" \
  --uri="https://southamerica-east1-run.googleapis.com/google.cloud.run/v1/namespaces/coherence-ominichannel-fs/jobs/group-sync-test:run" \
  --http-method=POST \
  --oauth-service-account-email=894828119087-compute@developer.gserviceaccount.com

# LGPD Cleanup (diario 3h BRT)
gcloud scheduler jobs create http lgpd-cleanup-trigger \
  --location=us-central1 \
  --schedule="0 3 * * *" \
  --uri="https://southamerica-east1-run.googleapis.com/google.cloud.run/v1/namespaces/coherence-ominichannel-fs/jobs/lgpd-cleanup-test:run" \
  --http-method=POST \
  --oauth-service-account-email=894828119087-compute@developer.gserviceaccount.com
```

## Module Registration in Portal

```bash
# Get Firebase JWT (super-admin)
TOKEN=$(gcloud auth print-identity-token)

# Register omnichannel-agentes module
curl -X POST https://coherence-portal-test-XXX-uc.a.run.app/api/admin/modules/omnichannel-agentes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Agentes Omnichannel",
    "url": "https://agents-runtime-test-XXX-uc.a.run.app",
    "description": "Runtime multi-agente (Jennifer + 4 Managers + 3 Specialists). Edite skills/tools sem rebuild.",
    "icon": "Bot"
  }'

# Grant permission to super-admin (viniciusbritor@gmail.com)
curl -X POST https://coherence-portal-test-XXX-uc.a.run.app/api/admin/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_email": "viniciusbritor@gmail.com",
    "module_id": "omnichannel-agentes",
    "role": "super-admin"
  }'
```