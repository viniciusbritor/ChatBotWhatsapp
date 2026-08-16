# Jennifer — `agents_runtime`

Runtime FastAPI do modulo **Agentes Omnichannel**. Recebe mensagens do
WhatsApp via Evolution, orquestra capacidades (Gmail/Drive/Calendar/RAG) com
autorização por proprietário e mantém o plano de controle do modulo em
`/admin/dashboard`.

> **Última atualização:** 2026-07-22 — arquitetura mínima, ledger Pub/Sub,
> tick azul, owner-only Google, fallback STT controlado.
> Suite local: **329 passed, 10 skipped** (5,16 s).

## Estrutura

```
agents_runtime/
  main.py                       # FastAPI: webhook, /pubsub/push, /admin/*
  orchestrator.py                # Jennifer: roteamento + LLM + tools
  agent_loader.py                # Snapshot agents/skills/tools do Firestore
  core/
    auth.py                      # Bearer SA / Firebase JWT
    message_ledger.py            # Ledger Firestore para idempotência
    pubsub_dispatcher.py         # Lease + retry control
    pubsub_publisher.py          # publish chatbotwhatsapp-messages
    pubsub_consumer.py           # shim de compatibilidade (usa dispatcher)
    evolution_client.py          # sendText + markMessagesAsRead
    evolution_webhook.py         # normalizador do envelope
    audio_transcribe.py          # Whisper + fallback Gemini controlado
    owner.py / owner_guard.py    # guard Gmail/Drive/Calendar
    module_ui.py                 # plano de controle /admin/dashboard
    rag.py                       # OpenAI embeddings + busca por owner
    secrets.py / masker.py / logging.py / ...
  tools/
    google_gmail.py / google_drive.py / google_calendar.py
    audio_transcribe.py / web_search.py / locomotion.py / nickname.py / ...
  scripts/
    ingest_owner_knowledge.py    # carga de livros/editais via GCS
    seed_initial_data.py / check_lgpd_compliance.py / migrate_rag_v2.py
  tests/                         # 36 arquivos, 329 passed
  cloudbuild-test.yaml
  Dockerfile
```

A documentação canônica vive em `docs/` na raiz do repositório.
`agents_runtime/docs/` foi removido por ser cópia desatualizada.

## Quick start

```bash
cd agents_runtime
pip install -r requirements.txt -r requirements-dev.txt
pytest -q tests/
ruff check core/ main.py orchestrator.py agent_loader.py tool_registry.py
python scripts/check_lgpd_compliance.py
```

Para validar Pub/Sub real use `RUN_PUBSUB_E2E=1 pytest tests/integration/test_pubsub_e2e.py`.

## Pipeline

```
Celular
  ↕ WhatsApp
Evolution API
  ↕ POST /webhook (markMessagesAsRead async)
agents-runtime-test
  ↕ publish chatbotwhatsapp-messages
Pub/Sub + DLQ nativa
  ↕ push /pubsub/push (claim no ledger Firestore)
  ↕ Whisper local → Gemini 2.5 Flash (somente sob consentimento)
  ↕ LLM único DeepSeek V4 Flash (prompt cache ativo)
  ↕ Groq Whisper Large v3 Turbo → OpenAI Whisper-1 → Gemini 2.5 Flash (STT cascade)
  ↕ Tools Google (somente telefone do proprietário)
Evolution /message/sendText
  ↕ resposta + tick azul
Celular
```

## Endpoints

- `POST /webhook` — entrada do Evolution.
- `POST /pubsub/push` — push subscription (OIDC + ledger).
- `POST /chat` — proxy interno usado pelos workers e pelo playground.
- `GET /admin/dashboard` — plano de controle do módulo (Bearer ou Firebase).
- `GET /admin/accounts`, `POST /admin/accounts`, `PUT /admin/accounts/{id}`
- `GET /admin/agents`, `POST /admin/agents`, `DELETE /admin/agents/{id}`
- `GET /admin/skills`, `POST /admin/skills`
- `GET /admin/tools`, `POST /admin/tools`
- `GET /admin/owners`, `GET /admin/knowledge`, `GET /admin/status`
- `GET /admin/users`, `POST /admin/register-user`
- `GET /admin/groups`, `POST /admin/groups/confirm`
- `POST /oauth/google`, `GET /oauth/callback`

## Custos

`agents-runtime-test` (2 vCPU, 2 GiB, min=0, max=3, cpu-throttling): ~$5/mês.
LLM cascade, Whisper e Pub/Sub geram custo variável conforme o tráfego.

## Próximos passos

- Drenar backlog legado com `gcloud pubsub subscriptions seek agents-runtime-consumer --time=<deploy_ts>`.
- Backfill de embeddings para a nova coleção `agent-knowledge-v2` por
  `owner_id`.
- Excluir o proxy `WhatsappAgente` e o serviço `whatsapp-agente-test`.