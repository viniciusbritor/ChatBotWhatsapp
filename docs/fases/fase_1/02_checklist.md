# Fase 1 — Checklist

> **Periodo**: 2026-07-22
> **Status**: CONCLUIDA (acesso a API liberado; custo real exige BigQuery)

## Tasks

- [x] T1.1.1: Identificar gcloud SDK em uso (569.0.0) e versao target (577.0.0)
- [x] T1.1.2: Identificar bloqueio (instalador MSI admin) e propor workaround
- [x] T1.2.1: Re-autenticar com scope `cloud-billing.readonly`
- [x] T1.2.2: Habilitar Cloud Billing Budget API no projeto
- [x] T1.2.3: Setar quota project para ADC
- [x] T1.2.4: Confirmar que GET billing account funciona
- [x] T1.2.5: Confirmar que GET billing info projeto funciona
- [x] T1.2.6: Listar budgets ativos (4 encontrados)
- [x] T1.2.7: Tentar costs:query (4 endpoints - todos 404)
- [x] T1.2.8: Documentar conclusao (custo real via BigQuery ou Console)
- [x] T1.3.1: Listar todos os servicos Cloud Run do projeto
- [x] T1.3.2: Classificar quais sao do chatbot vs outros produtos
- [x] T1.3.3: Confirmar que nao ha servicos `-prod` do chatbot deployados
- [x] T1.4.1: Documentar 6 tipos de auth em uso
- [x] T1.4.2: Documentar fluxo OAuth per-user passo-a-passo
- [x] T1.4.3: Documentar status atual do token (AUSENTE)

## Evidencias

### gcloud SDK
- Versao atual: `569.0.0`
- Versao target: `577.0.0`
- Bloqueio: instalador MSI requer admin

### API de custos
- GET billing account: 200 OK (conta existe, currency BRL)
- GET billing info: 200 OK (billingEnabled=true)
- GET budgets: 200 OK (4 orcamentos listados)
- POST costs:query (v1, v1beta, v1beta1): 404 (metodo nao existe)
- POST billingbudgets costs:query: 404
- GET reports: 404

### Orcamentos ativos
| Nome | Limite |
|---|---|
| Alarme Lana 500 | R$ 500/mes |
| Lana Safety Limit | R$ 50/mes |
| R$300 Alerta de orcamento mensal | R$ 300/mes |
| Alerta Firestore Coherence | R$ 10/mes (apenas Firestore) |

### Servicos do chatbot
- `agents-runtime-test` (Cloud Run, min=1, ~$3.46/dia)
- `ata-worker-test` (Cloud Run Job)
- `proactive-worker-test` (Cloud Run Job)
- `whatsapp-agente` (LEGACY - deletar na Fase F)

### Servicos NAO-chatbot
- `coherence-portal*` (Portal Coherence)
- `monitoria*` (Monitoria IA - 7 servicos)
- `redirect-server` (infra compartilhada)

### Token OAuth
- `google_oauth_token` em Firestore: AUSENTE
- Causa: B.3 do Plano B removeu, re-autorizacao nao completada

## Proxima fase

Fase 2: aplicar min-instances=0 nos servicos de chatbot + auditar Pub/Sub
retry loop + deletar whatsapp-agente (legacy).
