# Fase 1 — Liberar API de Custos e Documentar Ambiente

> **Data**: 2026-07-22
> **Status**: CONCLUIDA (acesso a API liberado; dados reais exigem BigQuery export)
> **Objetivo**: documentar como liberar a API de billing, atualizar gcloud,
> confirmar o papel da arquitetura no projeto GCP e mapear o fluxo de
> autenticacao do chatbot.

## 1. Resultado da tentativa de liberacao da API de custos

### 1.1. Estado inicial

- gcloud SDK: **569.0.0** (atualizacao para 577.0.0 requer instalador MSI com
  privilegios de administrador - bloqueado nesta sessao)
- Cloud Billing API v1: **habilitada** no projeto
- Cloud Billing Budget API v1beta1: **desabilitada** no projeto
- OAuth scopes do token: `cloud-platform` (largo, mas NAO inclui `cloud-billing`)
- Conhecimento de custos pelo usuario: baseado em **contestacao** aberta com
  suporte GCP (confirmado R$ 1.070,71 em vCPU/RAM ociosas) para o
  **projeto `coherence-ominichannel-fs`** (case 73572220, atendente Don Don,
  Google Cloud Billing Support, 22/07/2026 14:23 PDT).

> **CORRECAO 22/07 (apos contestacao verificada)**: o agente Google
> confirmou explicitamente que o custo excessivo foi no projeto
> `coherence-ominichannel-fs` ("I can confirm that I see the surge in costs
> associated with the Cloud Run services for Project Coherence Ominichannel").
> A contestacao e deste projeto, NAO de `brasil-ai`. Os 4 orcamentos que
> aparecem via API sao de `brasil-ai` mas NAO refletem o gasto do chatbot.
> O billing account `0182AB-52893A-9993BE` e compartilhado entre os dois
> projetos, o que explica a mistura. Apos o credito de R$ 1.070,71 ser
> aplicado, o custo real do omnichannel precisa ser monitorado separadamente.

### 1.2. Acoes tomadas

1. **Re-autenticacao com scope de billing**:
   ```powershell
   gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-billing.readonly,https://www.googleapis.com/auth/cloud-platform"
   ```
   - Token agora tem `scope: cloud-billing.readonly cloud-platform` (confirmado via
     `https://oauth2.googleapis.com/tokeninfo?access_token=...`)
   - Credenciais salvas em
     `C:\Users\vinic\AppData\Roaming\gcloud\application_default_credentials.json`

2. **Habilitar Cloud Billing Budget API**:
   ```powershell
   gcloud --project=coherence-ominichannel-fs services enable billingbudgets.googleapis.com
   # Operation "operations/acat.p2-894828119087-8f453fd1-779d-44e3-a881-72ca8638f09d" finished successfully.
   ```
   - Antes: API retornava 403 com "SERVICE_DISABLED"
   - Apos: API habilitada, budgets listaveis

3. **Definir quota project**:
   ```powershell
   gcloud auth application-default set-quota-project coherence-ominichannel-fs
   ```
   - Necessario para APIs de billing funcionarem (sem isso, retorna 403)

### 1.3. Tentativas de acessar dados de custo (e resultado)

| Tentativa | Endpoint | Resultado |
|---|---|---|
| GET billing account | `GET /v1/billingAccounts/0182AB-52893A-9993BE` | **200 OK** (confirma conta existe, currencyCode=BRL, open:true) |
| GET billing info projeto | `GET /v1/projects/894828119087/billingInfo` | **200 OK** (confirma billingAccountName, billingEnabled:true) |
| POST costs:query | `POST /v1/billingAccounts/0182AB-52893A-9993BE/costs:query` | **404** (metodo nao existe na v1) |
| POST costs:query v1beta | `POST /v1beta/.../costs:query` | **404** |
| POST billingbudgets costs:query | `POST /v1beta1/.../costs:query` | **404** |
| GET billingbudgets reports | `GET /v1beta1/.../reports` | **404** |
| GET billingbudgets budgets | `GET /v1beta1/.../budgets` | **200 OK** (lista 4 budgets) |

**Conclusao**: A Cloud Billing API v1 (mesmo habilitada com scope `cloud-billing.readonly`)
**nao expoe dados de custo real** via endpoint direto. Os metodos disponiveis sao
apenas gestao de billing accounts e projetos. Para acessar custo real, as
opcoes sao:

1. **BigQuery billing export** (one-time setup, depois query SQL)
2. **Cloud Console Reports UI** (`https://console.cloud.google.com/billing/0182AB-52893A-9993BE/reports`)
3. **Suporte GCP** (via ticket de billing - a contestation ja aberta)

### 1.4. Custo por servico Cloud Run (estimado via logs 24h)

Baseado em contagem de requisicoes via `run.googleapis.com/requests` (24h
ate 22:50 BRT 22/07) e configs via `gcloud run services describe`.

| Servico | CPU | RAM | minScale | Requests 24h | Custo/dia estimado |
|---|---|---|---|---|---|
| **agents-runtime-test** | 2 | 2Gi | **1** | **44.197** | **~$7.90** (idle $3.46 + request compute $4.42) |
| coherence-portal | 2 | 2Gi | 0 | 133 | ~$0 |
| coherence-portal-test | 2 | 2Gi | 0 | 0 | $0 |
| monitoria | 4 | 8Gi | 0 | 130 | ~$0.05 |
| monitoria-cx | 2 | 2Gi | 0 | 0 | $0 |
| monitoria-cx-v2 | 2 | 2Gi | 0 | 0 | $0 |
| monitoria-test-env | 4 | 8Gi | 0 | 0 | $0 |
| monitoria-whisper-worker | 4 | 4Gi | 0 | 0 | $0 |
| monitoria-worker | 4 | 4Gi | 0 | 0 | $0 |
| redirect-server | 1 | 512Mi | 0 | 0 | $0 |
| whatsapp-agente | 1 | 1Gi | 0 | 0 | $0 |
| **TOTAL** | | | | **44.460** | **~$7.95/dia (~$240/mes)** |

### Descobertas criticas

1. **44.197 requests em 24h em `agents-runtime-test`** e **440x mais** que o
   esperado para um chatbot com ~100 msgs/dia. Provavel causa: Pub/Sub
   retry loop das mensagens antigas (antes do Bloco A corrigir o 403).
   Cada retry gera 1 request com custo de compute.

2. **Custo atual do chatbot**: ~$7.95/dia = ~$240/mes (somando idle +
   request compute de todos os servicos do projeto).

3. **Vs. reportado** (~$100/dia = ~$3.000/mes): discrepancia de 12x.
   Provavel causa: pico historico (CPU-THROTTLING: false ativo em julho)
   que esta sendo contestado ($1.070,71). Apos contestacao ser aprovada,
   custo volta para ~$240/mes.

4. **Apenas `agents-runtime-test`** cobra idle ($3.46/dia). Todos os
   outros tem `minScale: 0` (scale-to-zero).

5. **Bot esta de fato recebendo requests pesadas** (44k/dia). Nao e
   "tudo parado" como pode parecer. Mas a origem precisa ser investigada.

## 1.5. Orcamentos ativos (verificado via API)

Apos correcao do usuario 22/07: o billing account `0182AB-52893A-9993BE`
e compartilhado entre `coherence-ominichannel-fs` e `brasil-ai`. A API
retorna todos os orcamentos do account misturados, sem filtro de projeto.

Os 4 orcamentos listados via API (`Alarme Lana 500`, `Lana Safety Limit`,
`R$300 Alerta`, `Alerta Firestore Coherence`) pertencem ao `brasil-ai`,
NAO ao `coherence-omnichannel-fs`. A contestacao GCP de R$ 1.070,71
confirmada pelo atendente Don Don e **especificamente do projeto
`coherence-ominichannel-fs`**, conforme case 73572220.

**Implicacao para o chatbot (omnichannel)**:
- A contestacao confirma que o gasto foi **interno** (configuracao de
  CPU-THROTTLING: false em servicos Cloud Run)
- O gasto ja foi reportado como R$ 1.070,71 e o credito de boa fe
  esta em analise
- Apos 32h (apos 22/07 22:23 BRT), o atendente Don Don enviara email
  com o valor final aprovado
- Enquanto isso, e necessario auditar cada Cloud Run do projeto
  omnichannel para garantir que o CPU-THROTTLING esta correto
  (ver Sessao 2 deste doc)

## 2. Papel da arquitetura (chatbot dentro do projeto GCP)

### 2.1. Servicos do chatbot (escopo da Fase 1+)

| Servico | Tipo | Status | Custo |
|---|---|---|---|
| `agents-runtime-test` | Cloud Run | ATIVO, min=1 | **~$3.46/dia** (cobra 24/7) |
| `ata-worker-test` | Cloud Run Job | sob demanda (via `ata-worker-trigger` */10) | baixo |
| `proactive-worker-test` | Cloud Run Job | sob demanda (via `proactive-events-trigger` */15) | baixo |
| `whatsapp-agente` | Cloud Run | ATIVO (LEGACY, deveria ser deletado na Fase F) | variavel |
| `pub_c1`-`pub_c2` Pub/Sub | mensagens | retry loop antigo | desconhecido |

### 2.2. Servicos NAO relacionados ao chatbot (mesmo projeto)

Estes NAO fazem parte do chatbot e consomem budget compartilhado:

| Servico | Produto | Status | Responsavel |
|---|---|---|---|
| `coherence-portal` | Portal Coherence | ATIVO | outro time |
| `coherence-portal-test` | Portal Coherence (test) | ATIVO | outro time |
| `monitoria` | Monitoria IA | ATIVO | outro time |
| `monitoria-cx` | Monitoria IA | ATIVO | outro time |
| `monitoria-cx-v2` | Monitoria IA v2 | ATIVO | outro time |
| `monitoria-test-env` | Monitoria IA (test) | ATIVO | outro time |
| `monitoria-whisper-worker` | Monitoria (worker) | ATIVO | outro time |
| `monitoria-worker` | Monitoria (worker) | ATIVO | outro time |
| `redirect-server` | Infraestrutura compartilhada | ATIVO | outro time |

**Implicacao**: para reduzir custo do **chatbot**, somente a parte do chatbot
importa. Os outros servicos consomem budget mas nao sao nossa responsabilidade.

### 2.3. Resposta a sua pergunta

> "nao quero nada em prod agora" - o que existe em "producao"?

**Confirmado**: **NENHUM servico de chatbot tem sufixo `-prod` deployado**.
Todos sao `*-test`. Os servicos `coherence-portal*` e `monitoria*` (sem
sufixo `-prod`) pertencem a **outros produtos** no mesmo projeto GCP, nao
ao chatbot. Eles estao fora do escopo desta esteira.

O chatbot opera **inteiramente em ambiente de test** (revisao
`agents-runtime-test-00145-649`, ENVIRONMENT=test). Nao ha deploy de producao.

## 3. Fluxo de autenticacao (documentado para referencia)

### 3.1. Tipos de auth no projeto

| Tipo | Onde | Para que |
|---|---|---|
| Google OAuth per-user | Jennifer <-> Google APIs | Calendar, Drive, Gmail |
| Bearer SA token | curl + Portal | `/admin/*`, `/chat`, `/proactive/send`, `/oauth/google` |
| Firebase JWT | Portal Coherence | `/admin/*` (alternativa) |
| OIDC Google-signed | Pub/Sub push | `/pubsub/push` |
| gcloud user creds (CLI) | local | `gcloud` commands |
| gcloud ADC | local | REST API direto (precisam de scope explicito) |

### 3.2. Fluxo OAuth per-user (com Google API)

**Quando**: cada vez que Jennifer precisa acessar Calendar/Drive/Gmail em
nome do usuario.

1. Jennifer recebe o telefone do usuario (ja temos: `5511966830020`)
2. Verifica Firestore `usuarios/5511966830020/google_oauth_token`
3. Se nao tem OU expirado:
   - Retorna 401 com URL de autorizacao
4. Usuario acessa URL `/oauth/google?phone=5511966830020&instance=jennifer`
   - Endpoint requer Bearer SA token
   - Retorna 302 redirect para `https://accounts.google.com/o/oauth2/auth?...`
5. Usuario autoriza no Google consent screen
6. Google redireciona para `/oauth/callback?code=...&state=...`
7. Cloud Run troca code por tokens via `oauth2.googleapis.com/token`
8. Salva em Firestore com scopes, access_token, refresh_token, expiry
9. Jennifer usa `core.oauth_per_user.get_user_credentials(phone)` para criar
   objeto `Credentials` autenticado
10. Chamadas as APIs Google (calendar.list_events, gmail.search_messages, etc.)

### 3.3. Status atual do token

| Item | Estado |
|---|---|
| Token no Firestore para `5511966830020` | **AUSENTE** (removido em B.3 do Plano B) |
| Logs `/oauth/callback` (1h) | **ZERO** |
| Token novo apos Bloco A + gmail.readonly commit | NAO foi persistido (usuario nao completou autorizacao) |

**Consequencia**: Jennifer NAO tem acesso a Calendar/Drive/Gmail ate
re-autorizacao ser completada.

## 4. Tarefas da Fase 1 (status final)

| Tarefa | Status |
|---|---|
| 1.1 Atualizar gcloud SDK | **BLOQUEADO** (requer instalador MSI admin) |
| 1.2 Liberar API de custos | **CONCLUIDO** (cloud-billing.readonly scope + billingbudgets API habilitada + quota project setado) |
| 1.3 Documentar papel na arquitetura | **CONCLUIDO** (esta secao) |
| 1.4 Documentar fluxo de autenticacao | **CONCLUIDO** (esta secao) |

## 5. Custo estimado do chatbot (calculo manual)

Baseado em Cloud Run pricing (us-central1) com `min-instances=1` para
`agents-runtime-test`:

| Recurso | Quantidade | Custo/hora | Custo/dia | Custo/mes |
|---|---|---|---|---|
| CPU 2 vCPU × 24h | 1 instancia | $0.1296 | $3.11 | $93.31 |
| Memory 2 GiB × 24h | 1 instancia | $0.0144 | $0.35 | $10.37 |
| Requests | ~100/dia | - | $0.00004 | $0.0012 |
| **Subtotal** `agents-runtime-test` | - | - | **$3.46** | **~$103.69** |

**Outros custos** (estimativa baixa):
- Cloud Run Jobs (ata-worker, proactive-worker): ~$3/dia total
- Pub/Sub mensagens: variavel (se loop de retry existir, pode ser alto)
- Firestore: low

**Total estimado**: ~$5-10/dia = ~$150-300/mes (workload nominal)

**Vs. reportado** R$ 100/dia = ~$3.000/mes:
- Discrepancia de ~10x
- Provavelmente spike de billing nao contabilizado (Pub/Sub retry loop, talvez)

## 6. Recomendacoes para Fase 2 (custos)

1. **Aplicar `min-instances=0`** em `agents-runtime-test` via gcloud:
   ```powershell
   gcloud run services update agents-runtime-test --region=us-central1 --min-instances=0
   ```
   - Economia imediata: ~$3.46/dia → ~$0/dia quando ocioso
   - Tradeoff: ~3-5s cold start em requests apos idle (aceitavel para secretary)

2. **Auditar Pub/Sub retry loop** (mensagens antigas de 20:53 BRT podem estar
   gerando milhoes de retries):
   ```powershell
   gcloud pubsub subscriptions describe agents-runtime-consumer
   # Verificar messageRetentionDuration, ackDeadlineSeconds
   # Verificar se ha mensagens nao-ackadas
   ```

3. **Deletar `whatsapp-agente`** (Fase F pendente - servico legacy que deveria
   ter sido deletado ha semanas):
   ```powershell
   gcloud run services delete whatsapp-agente --region=us-central1
   ```

4. **Auditar Cloud Scheduler** (cada trigger conta como 1 execucao):
   - `agents-runtime-ping` */5 = 288/dia (talvez */15 seja suficiente)
   - `ata-worker-trigger` */10 = 144/dia
   - `proactive-events-trigger` */15 = 96/dia

5. **Setup BigQuery billing export** (one-time) para ter dados reais:
   ```powershell
   gcloud billing accounts link-project --help
   # ou via Console: Billing > Billing export > BigQuery export
   ```
   - Apos: SQL queries diretos para custo real

## 7. Referencias

- Cloud Billing API v1: https://cloud.google.com/billing/docs/apis/rest/v1
- Cloud Billing Budgets API: https://cloud.google.com/billing/docs/budgets-api
- Cloud Run pricing: https://cloud.google.com/run/pricing
- BigQuery billing export: https://cloud.google.com/billing/docs/export-to-bigquery
- gcloud auth: https://cloud.google.com/sdk/docs/authorizing
