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
  suporte GCP (confirmado R$ 1.070,71 em vCPU/RAM ociosas)

> **ATENCAO (correcao do usuario 22/07)**: os 4 orcamentos que listei
> (`Alarme Lana 500`, `Lana Safety Limit`, `R$300 Alerta de orcamento mensal`,
> `Alerta Firestore Coherence`) **pertencem ao projeto `brasil-ai`**, NAO ao
> `coherence-ominichannel-fs`. O billing account `0182AB-52893A-9993BE`
> ("projeto jennifer") e compartilhado entre os dois projetos, entao os
> orcamentos aparecem na listagem mas nao refletem gasto do omnichannel.

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

### 1.4. Orcamentos ativos (verificado via API)

**CORRECAO**: os 4 orcamentos que aparecem na API **pertencem ao projeto
`brasil-ai`**, NAO ao `coherence-ominichannel-fs`. O billing account
`0182AB-52893A-9993BE` ("projeto jennifer") e compartilhado entre os
dois projetos, por isso a listagem atraves da API `billingAccounts/.../budgets`
mistura orcamentos de ambos.

Lista bruta (sem filtro de projeto):

```json
[
  {"displayName": "Alarme Lana 500", "amount": "R$ 500/month"},
  {"displayName": "Lana Safety Limit", "amount": "R$ 50/month"},
  {"displayName": "R$300 Alerta de orçamento mensal", "amount": "R$ 300/month"},
  {"displayName": "Alerta Firestore Coherence", "amount": "R$ 10/month", "scope": "Firestore only"}
]
```

**Implicacao**: nao posso afirmar que o chatbotwhatsapp (omnichannel) esta
estourando orcamento. Os orcamentos acima sao de `brasil-ai`. O custo
reportado pelo usuario (R$ 100/dia) precisa ser **revisado** com filtro
apenas no projeto `coherence-ominichannel-fs`.

A contestacao GCP confirmada (R$ 1.070,71) tambem precisa ser revalidada
com o filtro correto. A contestacao pode ter sido aberta para o projeto
errado (brasil-ai) em vez de omnichannel.

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
