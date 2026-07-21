# Plano Detalhado de Correções — ChatBotWhatsapp `test` (2026-07-21)

> **Modo**: build (consolidação final da rodada de esteira de test)
> **Escopo**: esteira de CI/CD, gaps dos agentes, fluxo OAuth, secrets órfãos.
> **Base de referência**: commits `076fbbf9`, `1654c68`, `5bcb488`, `32acd4f`, `e8b0634`, `fa1d707`, `d29e8f1`, `f14aa93`.

---

## 1. Resalvas da esteira de CI/CD (7 gaps)

| # | Gap | Detalhe | Severidade | Esforço | Arquivo/Recurso |
|---|---|---|---|---|---|
| 1 | **Testes de integração** contra Pub/Sub real | Apenas 217 testes (smoke). Não há testes contra `gcloud pubsub` ou `gcloud firestore` no CI. | média | 4h | `tests/integration/test_pubsub_e2e.py` |
| 2 | **Testes de carga** | Pipeline Pub/Sub pode não escalar. Não há teste com 100+ msg/min. | baixa | 2h | `tests/load/test_webhook_load.py` (locust) |
| 3 | **Cobertura do `/webhook`** | Validado com curl único (`messages.upsert`, `fromMe`, `CONNECTION_UPDATE`). Faltam: payload inválido, dados faltando, edge cases. | baixa | 1h | `tests/test_main_webhook.py` |
| 4 | **Logs estruturados** | `/webhook` loga `WARNING` mas com textPayload vazio. Logs não estão totalmente em JSON. | baixa | 1h | `core/logging.py` (structlog) |
| 5 | **Mypy no Cloud Build** | Mypy roda apenas local. Se config local diverge do build, diverge. | baixa | 0.5h | `cloudbuild-test.yaml:7` (já tem, mas validar) |
| 6 | **Teste de carga + cobertura do build** | Build feliz deploya. Build quebrado não (mas o step local não roda no Cloud Build). | baixa | 0.5h | adicionar `pytest tests/integration` no cloudbuild |
| 7 | **Documentação do trigger** em `HARNESS.md` raiz | Resumido. Falta link direto para o console, procedure "como adicionar novo trigger". | baixa | 0.5h | `docs/HARNESS.md` (atualizar) |

---

## 2. Gaps dos agents (5 gaps)

| # | Agent | Gap | Impacto | Solução | Arquivo |
|---|---|---|---|---|---|
| 1 | `manager-calendar` | Depende de OAuth do user. Se `google-oauth-token` global expirar, falha silenciosa. | médio | Implementar OAuth per-user (LGPD) | `core/oauth_per_user.py` (novo), `tools/google_calendar.py` |
| 2 | `manager-drive` | Mesma dependência do OAuth global. | médio | Mesmo | `tools/google_drive.py` |
| 3 | `manager-email` | Mesma dependência do OAuth global. | médio | Mesmo | `tools/google_gmail.py` |
| 4 | `agent-privacy-guard` | Não é invocado automaticamente. Lógica de detecção de intent pessoal em grupo existe, mas sem `pending_action` automática. | média | Implementar trigger no `orchestrator.py` quando `_is_personal_intent(intent) and _is_group_message(payload)`. | `orchestrator.py:_is_personal_intent`, `core/pending_actions.py:set_pending_action` |
| 5 | `agent-proatividade` | Worker não deployado em `test`. | média | Deployar como Cloud Run Job com schedule Cloud Scheduler. | `agents_runtime/proactive_worker/main.py`, `cloudbuild-proactive-test.yaml` |
| 6 | `group-resolver` | Não invocado. | baixa | Trigger manual ou heurística no `orchestrator.py`. | `tools/group.py` |
| 7 | `agent-rag` | Funciona, mas sem `pending_action` para atualizações periódicas. | baixa | Job Cloud Scheduler que sumariza docs antigos em `agent-knowledge-v2`. | `core/memory_manager.py:summarize_recent` (já existe) |

---

## 3. Fluxo OAuth do Google (3 etapas)

### 3.1. Setup do OAuth Client (você)

O `COHERENCE_18_PLUS_OAUTH_CLIENT_ID` está armazenado no Secret Manager do projeto `coherence-ominichannel-fs`. Você precisa:

1. **Acessar Google Cloud Console** → `coherence-ominichannel-fs` → APIs & Services → Credentials.
2. **Verificar o OAuth 2.0 Client ID** (nome: `coherence-18-plus`):
   - **Authorized redirect URIs** deve incluir: `https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/oauth/callback` (e `agents-runtime-prod` para prod).
3. **Scopes configurados no Google Cloud Console** devem ser:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/drive`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.send`
4. **Scopes default no `main.py:1101`** (deve estar alinhado com o que está configurado no Console).

### 3.2. Execução do OAuth pelo user (você)

```powershell
# Gerar URL de auth
$base = 'https://agents-runtime-test-c5nbfc5meq-uc.a.run.app'
$phone = '5511966830020'  # seu número sem + e sem espaços
$state = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($phone))
$url = "$base/oauth/google?state=$state&instance=jennifer"
Write-Host "Abra no browser: $url"
```

Abra a URL no browser, faça login na sua conta Google, autorize os scopes. O callback (`/oauth/callback`) vai salvar os tokens em `users/5511966830020/google_oauth` no Firestore.

### 3.3. Uso automático (já implementado em `core/secrets.py`)

O `core/secrets.py:get_secret("google_oauth_token")` faz:

1. Busca `users/{phone}` no Firestore
2. Verifica se `access_token` ainda é válido
3. Se não, usa `refresh_token` para gerar novo `access_token`
4. Retorna o token válido

---

## 4. Secrets órfãos (2 órfãos + 27 ativos)

### 4.1. Secrets órfãos (read-only seu, deletar manualmente)

| Secret | Descrição | Risco ao deletar |
|---|---|---|
| `whatsapp-agente-url` | URL do whatsapp-agente-test (proxy deletado) | nenhum |
| `agents-runtime-sa-token-clean` | Duplicata de `agents-runtime-sa-token` | nenhum (refresh já existe) |

### 4.2. Secrets do outro projeto (avatar-API)

| Secret | Descrição |
|---|---|
| `avatar-api-sa-key` | chave de SA para avatar-api |
| `API_SECRET_KEY` | chave de API do avatar-api |
| `DID_BASIC_AUTH` | basic auth para DID |
| `DOCKERHUB_TOKEN` | token para Docker Hub |
| `ELEVEN_LABS_API_KEY` | chave para ElevenLabs (TTS) |
| `ELEVEN_VOICE_ID` | ID de voz do ElevenLabs |
| `GCP_SA_KEY` | chave de SA do GCP |
| `GEMINI_API_KEY` | chave para Google Gemini |
| `GITHUB_TOKEN` | token do GitHub |
| `RUNPOD_API_KEY` | chave para RunPod |
| `RUNPOD_SA_B64` | SA do RunPod em base64 |
| `MINIMAX_VOICE_ID` | ID de voz do MiniMax |

### 4.3. Secrets ativamente usados (agents-runtime)

| Secret | Função |
|---|---|
| `DEEPSEEK_API_KEY` | LLM primário |
| `NVIDIA_API_KEY` | LLM fallback |
| `MINIMAX_API_KEY` | LLM fallback final |
| `minimax-group-id` | embeddings OpenAI |
| `serper-api-key` | busca web |
| `google-oauth-token` | OAuth global (legacy, será removido quando per-user estiver completo) |
| `agents-runtime-sa-token` | SA token do `agents-runtime` |
| `OPENAI_API_KEY` | embeddings OpenAI |
| `google-maps-api-key` | API do Google Maps |
| `youtube-api-key` | API do YouTube |
| `oauth-client-secret` | client secret do OAuth |
| `COHERENCE_18_PLUS_OAUTH_CLIENT_ID` | client ID do OAuth |
| `COHERENCE_18_PLUS_OAUTH_CLIENT_SECRET` | client secret do OAuth |
| `evolution-api-key` | API key do Evolution |
| `agents-runtime-url` | URL do agents-runtime |

---

## 5. Próximos passos (próxima rodada)

| # | Ação | Tipo | Esforço | Quem |
|---|---|---|---|---|
| 1 | Adicionar `tests/test_main_webhook.py` com edge cases | qualidade | 1h | eu |
| 2 | Adicionar `tests/integration/test_pubsub_e2e.py` | qualidade | 4h | eu |
| 3 | Adicionar `tests/load/test_webhook_load.py` (locust, 100 msg/min) | qualidade | 2h | eu |
| 4 | Implementar `core/oauth_per_user.py` (per-user OAuth, LGPD) | feature | 4h | eu |
| 5 | Refatorar `manager-calendar/drive/email` para usar OAuth per-user | feature | 4h | eu |
| 6 | Implementar trigger de `agent-privacy-guard` no `orchestrator.py` (criar `pending_action`) | feature | 2h | eu |
| 7 | Deployar `agent-proatividade` como Cloud Run Job | feature | 1h | eu |
| 8 | Documentar OAuth no `HARNESS.md` (procedures, scopes, troubleshooting) | docs | 1h | eu |
| 9 | Atualizar `HARNESS.md` raiz com lista de secrets (manter/órfão) | docs | 0.5h | eu |
| 10 | Configurar OAuth no Google Cloud Console (Authorized redirect URIs, scopes) | config | 0.5h | você |
| 11 | Executar OAuth manual para `+5511966830020` | config | 5min | você |
| 12 | Deletar `whatsapp-agente-url` e `agents-runtime-sa-token-clean` | cleanup | read-only | você |
| 13 | Deletar pasta local `C:\Users\vinic\workspace_antigravity\WhatsappAgente` | cleanup | read-only | você |
| 14 | Deletar repo `viniciusbritor/WhatsappAgente` no GitHub | cleanup | read-only | você |

---

## 6. Estimativa de tempo

- **Qualidade** (itens 1-3): 7h
- **Features** (itens 4-7): 11h
- **Docs** (itens 8-9): 1.5h
- **Config** (itens 10-11): 1h (você)
- **Cleanup** (itens 12-14): read-only (você)

**Total: ~21h de trabalho meu + ~1.5h seu**

---

## 7. Status do commit atual

Último build em produção: `00135-v7b` (commit `32acd4f`)
Último commit: `f14aa93` (docs consolidada)
Builds SUCCESS nos últimos 7 runs.

## 8. Critérios de aceite para a próxima rodada

- [ ] Cobertura de testes do `/webhook` ≥ 80%
- [ ] Testes de integração Pub/Sub passando em CI
- [ ] OAuth per-user funcionando (manager-calendar/drive/email acessam dados do user específico)
- [ ] `agent-privacy-guard` invocado automaticamente em grupos
- [ ] `agent-proatividade` deployado em test
- [ ] Pasta local `WhatsappAgente` e repo deletados
- [ ] Secrets órfãos deletados
- [ ] HARNESS.md atualizado com tudo (CI/CD, OAuth, agents, secrets, architecture)
