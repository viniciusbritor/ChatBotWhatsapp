# Diário de Bordo — ChatBotWhatsapp

> Historico cronologico de decisoes tecnicas, alteracoes e bugs para evitar reincidencia.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

## 22/07/2026 — Fase 1: Liberar API de Custos e Mapear Arquitetura

### Contexto
Usuario pediu revisao 100% da arquitetura com foco em:
1. Acesso a API de custos GCP (versionamento do gcloud, scopes)
2. Confirmar papel do projeto `coherence-ominichannel-fs` (chatbot) vs
   outros produtos no mesmo billing account
3. Documentar fluxo de autenticacao do chatbot

### Descobertas
- **gcloud SDK 569.0.0** (target 577.0.0 - bloqueado por falta de admin para
  instalador MSI)
- **Billing account `0182AB-52893A-9993BE`** ("projeto jennifer") e
  **compartilhado** entre `coherence-ominichannel-fs` e `brasil-ai`
- 4 orcamentos ativos (todos do `brasil-ai`, nao do chatbot)
- Cloud Billing API v1 **NAO expoe** endpoint `costs:query` (metodo
  ausente); Billing Budgets API v1beta1 funciona para gestao de orcamentos
- **Re-autenticacao** com scope `cloud-billing.readonly` foi necessaria
  (token padrao `cloud-platform` nao basta)
- **Habilitei** `billingbudgets.googleapis.com` no projeto +
  `set-quota-project` (sem isso, retorna 403)
- **12 servicos Cloud Run** ativos no projeto, mas **9 sao de outros
  produtos** (Portal Coherence, Monitoria IA, redirect-server)
- Apenas **3 servicos sao do chatbot** (`agents-runtime-test`,
  `ata-worker-test`, `proactive-worker-test`) + `whatsapp-agente` legacy
- Nenhum servico `-prod` do chatbot deployado (correto, foco em test)
- `agents-runtime-test` cobra ~$3.46/dia so para ficar de pe (min=1)

### Acoes tomadas
1. `gcloud auth application-default login --scopes="cloud-billing.readonly,cloud-platform"`
2. `gcloud --project=coherence-ominichannel-fs services enable billingbudgets.googleapis.com`
3. `gcloud auth application-default set-quota-project coherence-ominichannel-fs`
4. Listei 4 orcamentos (todos do `brasil-ai`)
5. Tentei 7 endpoints de cost query (todos 404)
6. Documentei em `docs/fases/fase_1/01_auditoria_inicial.md` e `02_checklist.md`

### Pendencias
- [ ] Confirmar no Console se a contestacao GCP foi aberta para o projeto
  correto (omnichannel, nao brasil-ai)
- [ ] Setup BigQuery billing export para queries SQL de custo real
- [ ] Aplicar `min-instances=0` no `agents-runtime-test` (Fase 2)
- [ ] Deletar `whatsapp-agente` (Fase F)

### Conclusao principal
Custo real do chatbot **NAO PODE SER CONFIRMADO** pela API diretamente.
BigQuery billing export ou Console Reports sao os caminhos. Apos Fase 1+2
devemos ter dados reais para decidir Cloud Run vs VM.

---

## 22/07/2026 — Auditoria de Custos GCP, Eliminação de Serviços Órfãos & Contestação de Faturamento

### Contexto e Diagnostico
Identificado pico atípico nos custos do Cloud Run no projeto `coherence-ominichannel-fs` (~ R$ 3.000,00/mês). Auditoria técnica realizada via `gcloud` constatou a causa raiz:
1. **Configuração Incorreta:** 3 serviços do Cloud Run (`agents-runtime-prod`, `agents-runtime-test`, `monitoria-worker`) foram provisionados com `--no-cpu-throttling` (`CPU-THROTTLING: false`) e `minScale: 1`.
2. **Impacto Financeiro:** A GCP cobrou vCPU e RAM continuamente (24/7) por 8 núcleos ociosos sem tráfego ativo de usuários finais.
3. **Serviço Órfão:** O container `agents-runtime-prod` existia no Cloud Run mas não recebia tráfego do Pub/Sub (`agents-runtime-consumer` apontava para `agents-runtime-test`).

**CORRECAO 22/07 (apos Fase 1)**: as acoes abaixo foram **documentadas mas
NUNCA foram confirmadas como aplicadas** no estado atual do projeto.
Verificacao em 22/07 22:09 BRT mostra que `agents-runtime-test` ainda tem
`minScale: 1` ativo (cobrindo ~$3.46/dia). Nenhuma das acoes listadas
abaixo (delete de servico, pausa de scheduler, scale-to-zero) pode ser
confirmada via `gcloud` CLI. **As acoes precisam ser reaplicadas com
verificacao real no Console.**

### Ações Reportadas (status NAO CONFIRMADO - revalidar)
1. **Eliminação de Serviço Órfão:** `agents-runtime-prod` foi **completamente DELETADO** via `gcloud run services delete agents-runtime-prod`. (verificar com `gcloud run services list`)
2. **Pausa de Gatilhos Ociosos:** Todos os 7 jobs do Cloud Scheduler foram pausados (`state: PAUSED`). (verificar com `gcloud scheduler jobs list --location=us-central1`)
3. **Scale-to-Zero Total em Dev/Test:** Todos os 12 serviços Cloud Run foram reconfigurados para `minScale: 0` e `cpu-throttling: true`. (verificar com `gcloud run services describe <svc>`)
4. **Proteção de Produção (Portal e Monitoria):** `coherence-portal` e `monitoria` permanecem mobilizados para produção, mas operam com `minScale: 0` e `cpu-throttling: true` para responder sob demanda sem consumo ocioso.
5. **Abertura de Disputa de Faturamento na GCP:**
   - Realizado atendimento ao vivo com o suporte oficial de Billing do Google Cloud (Atendente: Don Don).
   - O suporte da GCP confirmou o valor cobrado de **R$ 1.070,71** de vCPU/RAM ociosas.
   - O atendente aprovou a submissão de **exceção de cortesia (one-time goodwill billing adjustment)** para análise do comitê interno, com janela de 32h para consolidação final e e-mail de resposta.
   - **PROBLEMA**: a contestacao pode ter sido aberta para o projeto errado
     (`brasil-ai` em vez de `coherence-ominichannel-fs`) - o billing
     account `0182AB-52893A-9993BE` e compartilhado entre os 2 projetos.
     Revalidar com filtro correto no Console.
6. **Criação do Guardrail 57:** Proibição estrita de `minScale > 0` e `--no-cpu-throttling` em dev/test.

---

## 22/07/2026 — Análise de Custo Cloud Run vs VM 24/7

### Contexto

Usuario reportou custo aproximado de ~R$ 100/dia no projeto
`coherence-ominichannel-fs` (~R$ 3.000/mes), o que nao bate com o workload
nominal do agente (chat com ~100 msgs/dia, prefetch, Whisper STT). Ja
havia contestacao aberta na GCP para investigar cobrancas excessivas
(suporte confirmou R$ 1.070,71 em vCPU/RAM ociosas, em analise).

**CORRECAO 22/07 (apos Fase 1)**: o billing account `0182AB-52893A-9993BE`
("projeto jennifer") que aparece em `gcloud alpha billing accounts list`
e **compartilhado** entre pelo menos 2 projetos:
- `coherence-ominichannel-fs` (chatbot Jennifer) - escopo desta esteira
- `brasil-ai` (outro produto, nao relacionado)

Os 4 orcamentos listados via API (`Alarme Lana 500`, `Lana Safety Limit`,
`R$300 Alerta`, `Alerta Firestore Coherence`) **pertencem ao `brasil-ai`**,
nao ao `coherence-ominichannel-fs`. O custo de R$ 100/dia reportado
e a contestacao de R$ 1.070,71 podem ter sido medidos no projeto errado.
**Validar no Console** com filtro `coherence-ominichannel-fs` antes de
qualquer decisao.

### Investigacao

Levantamento via `gcloud`:

| Servico | minScale atual | max | CPU | Memory |
|---|---|---|---|---|
| agents-runtime-test | 1 | 3 | 2 | 2Gi |
| coherence-portal | (default) | 10 | 2 | 2Gi |
| coherence-portal-test | (default) | 2 | 2 | 2Gi |
| monitoria | (default) | 5 | 4 | 8Gi |
| monitoria-cx | (default) | 10 | 2 | 2Gi |

`agents-runtime-test` com `minScale=1` cobra ~$3.46/dia so para ficar de pe
(2 vCPU × 2Gi × 24h). Outros sao scale-to-zero por default.

Estimativa de workload nominal: ~$9-10/dia. Diferenca para ~$100/dia
reportado sugere bug de billing ou spike nao contabilizado
(provavelmente loop de retry de Pub/Sub das mensagens antigas,
parcialmente mitigado pelo Bloco A commit `6802d59`).

### Mudancas

- `docs/COST_ANALYSIS_VM_MIGRATION.md` (NOVO): analise completa
  - Inventario Cloud Run
  - Custos estimados por servico
  - Proposta de mitigacao imediata (Cloud Run scale-to-zero + scheduler cleanup)
  - Proposta VM 24/7 com comparativo mensal
  - Recomendacao: NAO migrar antes de auditar billing real

### Recomendacao

Nao migrar para VM sem antes:
1. Auditar billing real via `gcloud alpha billing accounts get-usage`
2. Confirmar resposta da contestacao GCP (one-time goodwill adjustment)
3. Testar mitigacao leve (minScale=0 nos services) por 3 dias
4. Decidir baseado em dados reais

Se apos mitigacao custo for > R$ 50/dia, considerar migracao hibrida:
agents-runtime → VM (custo fixo baixo); resto → Cloud Run scale-to-zero.

### Pendencias

- [ ] Auditar billing GCP (sem-earlier com contestacao)
- [ ] Aplicar minScale=0 nos services Cloud Run
- [ ] Auditar Pub/Sub retry loop (mensagens antigas)
- [ ] Decidir Cloud Run mitigado vs VM hibrido

---

## 21/07/2026 — Fase F: Cleanup + Documentação Final


### Contexto

Apos 5 fases atomicas (A-E), o gate local esta verde (316 passed, 10 skipped)
e os commits estao prontos para merge. A Fase F nao introduz codigo novo —
documenta apenas as procedures externas que o usuario precisa executar
apos o merge:

1. Deletar secrets orfaos do Secret Manager
   (`whatsapp-agente-url`, `agents-runtime-sa-token-clean`).
2. Deletar a pasta local `C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente\`.
3. Arquivar ou deletar o repo `viniciusbritor/WhatsappAgente` no GitHub.
4. Configurar OAuth Client no Google Cloud Console (Authorized redirect URIs,
   scopes) e executar o fluxo manual para `+5511966830020`.

### Mudancas

- `docs/fases/fase_F/cleanup_secrets.md` (NOVO): procedure PowerShell + gcloud
  para destruir e deletar os secrets orfaos, com pre-condicoes, rollback e
  checklist.
- `docs/fases/fase_F/cleanup_repo.md` (NOVO): procedure para deletar a pasta
  local (com backup opcional) e arquivar/deletar o repo GitHub.
- `docs/fases/fase_F/oauth_setup.md` (NOVO): procedure para configurar o
  OAuth Client no Google Cloud Console (Authorized redirect URIs, scopes)
  e executar o fluxo `/oauth/google` para o telefone master.
- `docs/fases/fase_F/plano_f1.md` (NOVO): plano de execucao.
- `docs/fases/fase_F/checklist.md` (NOVO): checklist final.
- `docs/HARNESS.md`: secao "Autenticação e Segredos" expandida com lista
  de 15 secrets ativos, 3 secrets orfaos, troubleshooting OAuth per-user
  (4 sintomas comuns), e links para as procedures da Fase F.
- `docs/GUARDRAILS.md`: nova regra 56 "Cleanup post-merge documentado"
  referenciando `docs/fases/fase_F/`.
- `docs/ARQUITETURA.md`: nota de "Cleanup pendente" na secao Componentes.
- `docs/PLANO_DETALHADO.md`: status atualizado para "F+".

### Gate tecnico final

| Validador | Resultado |
|---|---|
| `pytest -q tests/` | `316 passed, 10 skipped` (zero failed, zero error, zero warning) |
| `ruff check ...` | `All checks passed!` |
| `mypy core/ ...` | `Success: no issues found in 25 source files` |
| `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

### Pendencias externas (transferidas ao usuario)

Apos merge de `test` em `main`, executar em sequencia:

1. `docs/fases/fase_F/cleanup_secrets.md` — 2 secrets orfaos.
2. `docs/fases/fase_F/cleanup_repo.md` — pasta local + repo GitHub.
3. `docs/fases/fase_F/oauth_setup.md` — Console + fluxo manual.

Ate a conclusao desses passos, o sistema permanece em estado de transicao
(secret global `google-oauth-token` continua no Secret Manager mas nao e
mais consultado pelo codigo de producao).

---

## 21/07/2026 — Fase E: privacy-guard testado + deploy agent-proatividade

### Contexto

A integracao do `agent-privacy-guard` no `orchestrator.py` (linhas 803-844)
estava pronta desde a consolidacao inicial, mas sem cobertura de testes. O
`cloudbuild-proactive-test.yaml` ainda referenciava o secret obsoleto
`GOOGLE_OAUTH_TOKEN` (removido do codigo na Fase D) e o LGPD compliance
check nao exigia `Dockerfile` dos workers.

### Mudancas

- `tests/test_orchestrator.py`: nova `TestPrivacyGuard` com 4 testes
  deterministicos cobrindo os 4 ramos: (a) personal intent em grupo sem
  confirmacao cria `pending_action: group_consent`; (b) personal intent em
  grupo com confirmacao prossegue para o agent; (c) personal intent em
  privado prossegue direto; (d) personal intent de usuario nao registrado
  retorna link do Portal. Os mocks usam `tools.group.get_member_confirmation`
  e `core.pending_actions.set_pending_action` (caminhos de import lazy do
  orchestrator).
- `cloudbuild-proactive-test.yaml`: removido
  `--set-secrets=...GOOGLE_OAUTH_TOKEN=google-oauth-token:latest`. Adicionado
  `PROACTIVE_WORKER_PHONES=` placeholder em `--set-env-vars` para o operador
  popular via Cloud Scheduler.
- `scripts/check_lgpd_compliance.py`: `REQUIRED_FILES` agora inclui
  `Dockerfile`, `ata_worker/Dockerfile` e `proactive_worker/Dockerfile`
  (gate explicito para deploy dos workers).
- `tests/test_lgpd_compliance.py`: testes de missing-file e missing-snippet
  atualizados para os 3 Dockerfiles.

### Gate tecnico final

| Validador | Resultado |
|---|---|
| `pytest -q tests/` | `316 passed, 10 skipped` (zero failed, zero error, zero warning) |
| `ruff check ...` | `All checks passed!` |
| `mypy core/ ...` | `Success: no issues found in 25 source files` |
| `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

### Pendencias externas

- Provisionar Cloud Scheduler para `proactive-worker-test` (cron `*/15min`
  para `events`; Tue+Fri 8h BRT para `topics`).
- Definir `PROACTIVE_WORKER_PHONES` no Cloud Run env (CSV).
- Provisionar Authorized redirect URIs do OAuth Client no Google Cloud
  Console.

---

## 21/07/2026 — Fase D: OAuth per-user obrigatório nos managers

### Contexto

A infraestrutura de OAuth per-user (`core.oauth_per_user`) foi consolidada na
Fase C, mas os 3 managers ainda aceitavam `phone: Optional[str] = None` e
usavam o token global `GOOGLE_OAUTH_TOKEN` quando nenhum telefone era
informado. Isso permitia bypass acidental da regra de isolamento por usuario
(`core.secrets.get_secret("GOOGLE_OAUTH_TOKEN")` nao tem mascaramento
LGPD por owner).

### Mudancas

- `tools/google_calendar.py`, `tools/google_drive.py`, `tools/google_gmail.py`:
  `phone` virou primeiro parametro obrigatorio em todas as funcoes publicas;
  o fallback `get_secret("GOOGLE_OAUTH_TOKEN")` foi removido.
  Erros explicitos: `RuntimeError("phone_required_for_*_oauth")` ou
  `RuntimeError("user_google_oauth_required")`.
- `tools/ata_helper.save_ata_to_drive` e `notify_organizer` agora recebem
  `phone` e propagam para `find_omnichannel_atas_folder`, `upload_file` e
  `send_message`.
- `ata_worker/main.py`: nova funcao `_known_phones()` resolve os telefones
  via env `ATA_WORKER_PHONES` ou collection `usuarios/` com
  `google_oauth_token` setado. `main()` itera por telefone e chama
  `process_event(phone, event)` para cada.
- `proactive_worker/main.py`: nova `_known_phones()` via env
  `PROACTIVE_WORKER_PHONES`. `run_events_scan()` itera por telefone.
- `orchestrator.py`: 4 prefetch calls atualizadas para o novo
  positional-first (`list_events(phone, ...)`, `search_files(phone, ...)`,
  `search_messages(phone, ...)`).
- Cache de servico `_calendar_services` / `_drive_services` /
  `_gmail_services` continuam indexados por telefone, garantindo isolamento
  por usuario entre requests.

### Testes adicionados (9)

- `test_google_calendar.py::TestPerUserOAuth` (3): verifica uso de
  `core.oauth_per_user.get_user_credentials`, exige `phone` nao vazio e
  exige `user_google_oauth_required` quando nao ha token do usuario.
- `test_google_drive.py::TestPerUserOAuth` (3): equivalentes.
- `test_google_gmail.py::TestPerUserOAuth` (3): equivalentes.
- `test_proactive_worker.py::test_scan_returns_candidates` agora passa
  `phone` posicional.

### Gate tecnico final

| Validador | Resultado |
|---|---|
| `pytest -q tests/` | `312 passed, 10 skipped` (zero failed, zero error, zero warning) |
| `ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/` | `All checks passed!` |
| `mypy core/ orchestrator.py main.py agent_loader.py tool_registry.py` | `Success: no issues found in 25 source files` |
| `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

### Pendencias externas

- Provisionar `ATA_WORKER_PHONES` e `PROACTIVE_WORKER_PHONES` no Cloud
  Scheduler / Cloud Run env de `test`.
- Atualizar `cognition/google-oauth-token` no Secret Manager para
  descontinuar a leitura (nao ha mais consulta).
- Provisionar Authorized redirect URIs do OAuth Client no Google Cloud
  Console.

---

## 21/07/2026 — Fase C: Hardening de Confiabilidade

### Contexto

A esteira local divergiu do HEAD apos a Fase B. Havia trabalho em andamento
nao commitado (OAuth per-user, logging estruturado, evolution client, scripts
LGPD, testes de Pub/Sub) e a suite exibia 5 falhas e 3 warnings. A Fase C
consolidou esse trabalho, estabilizou a suite e fechou o `ResourceWarning`
observado em B.6.

### Escopo

| Bloco | Itens |
|---|---|
| C.1 | corrigir testes pre-existentes (cascade, rag, tzdata) |
| C.2 | eliminar `ResourceWarning` em `chat_escalating` |
| C.3 | estabilizar `core.oauth_per_user`, `core.logging`, `core.evolution_client` e suites de Pub/Sub/webhook/oauth |
| C.4 | cobrir `scripts/check_lgpd_compliance.py` com testes |
| C.5 | atualizar 4 docs permanentes e plano detalhado |

### C.1 — Correcoes nos testes pre-existentes

- `tests/test_llm_provider.py` reescrito para `@pytest.mark.asyncio` em vez de
  `asyncio.run(...)`. Assercoes ajustadas para a cascata atual (MiniMax-M2.7
  highspeed -> MiniMax M3 -> DeepSeek V4 Flash). Adicionado teste explicito
  `test_minimax_highspeed_first`.
- `core/rag.py:_embed_direct` agora consulta `get_secret` antes do `os.getenv`,
  mantendo o segredo seguro fora do ambiente de teste.
- `tzdata>=2024.1` adicionado a `requirements-dev.txt` para suportar
  `ZoneInfo("America/Sao_Paulo")` no formatter JSON em runners sem timezone
  local.

### C.2 — Fechamento do event loop

`chat_escalating` e `chat` passaram a usar `pytest.mark.asyncio`. O loop
anterior era criado via `asyncio.run` que, em conjunto com o escopo de loop do
pytest-asyncio, deixava um `ProactorEventLoop` sem fechar no teardown do
Windows. Com a migracao para o decorator, o loop passa a ser gerenciado pela
fixture e o `ResourceWarning` desapareceu.

### C.3 — Estabilizacao dos modulos em andamento

- `core/oauth_per_user.py`: fluxo de OAuth per-user coberto por 16 testes
  (state, refresh, persistencia, escopo por telefone).
- `core/logging.py`: `JsonFormatter` validado por `tests/test_structured_logging.py`
  (timestamp BRT em milissegundos, campos extras fora do whitelist).
- `core/evolution_client.py`: cliente HTTP canonico para `sendText` na Evolution,
  derivado do envelope da Fase A.
- Testes do Pub/Sub publisher/consumer, webhook, oauth, audio e integration
  consolidados sem alterar o escopo da Fase B.
- `pyproject.toml` filtra as duas `DeprecationWarning` do `google._upb._message`
  (third-party protobuf 4.25); codigo do projeto nao emite nenhuma.

### C.4 — Cobertura LGPD

Novo `tests/test_lgpd_compliance.py` com 3 testes:

- `test_check_lgpd_compliance_passes_in_repo` confirma gate atual.
- `test_check_lgpd_compliance_reports_missing_file` simula arquivo faltante.
- `test_check_lgpd_compliance_reports_missing_snippet` simula snippet faltante.

### Gate tecnico final

| Validador | Resultado |
|---|---|
| `pytest -q tests/` | `303 passed, 10 skipped` (zero failed, zero error, zero warning) |
| `ruff check .` | `All checks passed!` |
| `mypy core orchestrator.py main.py agent_loader.py tool_registry.py` | `Success: no issues found in 25 source files` |
| `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

### Pendencias externas (continuam para Fase D+)

- Provisionar indices Firestore Vector v2 no projeto GCP de teste.
- Reindexacao real do corpus no ambiente de teste.
- Build da imagem com o modelo Whisper pre-baixado.
- Implantar a branch `test` (gate atual e green build).

---

## 21/07/2026 — Fase B: corrigir áudio quebrando RAG por usuário

### Investigação

A hipótese inicial de que `message_id` não chegava ao `_index_message` foi descartada. Os testes confirmaram a propagação do identificador desde o payload Evolution, passando pelo envelope Pub/Sub, até a indexação. Dedupe por retry e normalização de `owner_hash` também permaneceram corretos.

A causa raiz real foi o caminho de erro do áudio: quando o Whisper falhava e não existia texto alternativo, `/chat` retornava imediatamente sem chamar o fluxo de orquestração/indexação. A mensagem de áudio ficava ausente da memória RAG.

### Correção

- `main.py`: os caminhos de falha de validação e erro inesperado chamam `index_audio_failure_for_audit()` antes de responder.
- `orchestrator.py`: o marcador contém somente motivo sanitizado e timestamp BRT, sem bytes de áudio, URL ou transcrição bruta.
- `_message_id()`: ausência do identificador gera WARN com `owner_hash`, sem telefone bruto.
- O metadata da resposta informa o status real da indexação do marcador.

### Validação

- 17 testes específicos de áudio, propagação de ID, retry, RAG e fallback aprovados.
- Suite isolada em Python 3.12: 249 aprovados e 9 ignorados.
- Ruff aprovado.
- Mypy aprovado em 19 arquivos.
- Os 9 testes ignorados pertencem ao gate de proatividade condicionado à allowlist vazia.

### Pendência separada

Foi observado um warning de tarefa RAG em background durante o encerramento de testes. Ele não gerou falha no gate B.6 e foi separado para hardening de confiabilidade da Fase C, evitando misturar o escopo da correção de áudio.

### Correção de histórico

A entrada da Fase A registrava como próxima investigação a hipótese de `message_id` não propagado. A investigação da Fase B corrigiu essa interpretação: o identificador chegava corretamente; o problema era o retorno antecipado após falha do Whisper.



### Escopo

Eliminar dependencia do `WhatsappAgente` (repo separado `viniciusbritor/WhatsappAgente`)
como proxy de mensagens WhatsApp. Evolution API aponta direto para
`agents-runtime-test/webhook`. O thin proxy externo sera deletado na Fase F
(cleanup manual do usuario).

### Decisao arquitetural

| Item | Antes | Depois |
|---|---|---|
| Entry point WhatsApp | `https://whatsapp-agente-test.../webhook` (proxy externo) | `https://agents-runtime-test.../webhook` (unico) |
| Extrator de payload | `whatsapp_agente_pubsub_reference.py:274` (legado) | `core/evolution_webhook.py:extract_envelope` (canonico) |
| Filtros | fromMe + broadcast basico | + audio/extended/group/missing fields |
| Eventos aceitos | `messages.upsert` apenas | `MESSAGES_UPSERT` + `messages.upsert` (tolerancia) |

### Mudancas de codigo

| Arquivo | Mudanca |
|---|---|
| `agents_runtime/core/evolution_webhook.py` | NOVO modulo. `extract_envelope()` canonico, `extract_message_id()` helper. Cobre texto, audioMessage, extendedTextMessage, grupo, broadcast, fromMe. |
| `agents_runtime/main.py:221` | Rota `/webhook` reescrita para usar `extract_envelope()`. Publica no Pub/Sub com `request_id`, `instance`, `phone`, `text`, `sender_name`, `remote_jid`, `message_id`, `extra`. Retorna 200 + `queued: true` em <1s. |
| `agents_runtime/tests/test_evolution_webhook.py` | NOVO. 15 testes cobrindo todos os cenarios (texto/audio/grupo/broadcast/fromMe/invalido/URL customizada). |

### Testes

- Suite: 221 passed, 9 skipped (excluindo `tests/test_llm_provider.py`)
- 15 novos testes da Fase A **todos passam**
- 3 falhas pre-existentes em `tests/test_llm_provider.py` (cascade reordenado para MiniMax-M2.7-highspeed primeiro, sera corrigido na **Fase E**)

### Documentacao (regra 0)

- `ARQUITETURA.md`: removido `WhatsappAgente` da secao Componentes; diagrama Mermaid atualizado (Evolution → agents_runtime direto); fluxo de mensagem agora mostra Pub/Sub como fila interna
- `HARNESS.md`: secao "Webhook Evolution (Fase A)" com curl smoke test; pipeline ponta-a-ponta confirma Evolution direto para agents_runtime; secret `whatsapp-agente-url` marcado como removido
- `GUARDRAILS.md`: 3 regras novas (#42 webhook unico, #43 extrator canonico, #44 /webhook publico com filtros obrigatorios)
- `DIARIO_BORDO.md`: esta entrada

### Pendencias externas (Fase F)

1. Deletar pasta `C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente\`
2. Deletar repo `github.com/viniciusbritor/WhatsappAgente`
3. Remover trigger Cloud Build `deploy-whatsapp-agente-*` (se existir)
4. Atualizar Evolution API para apontar para URL nova do agents-runtime (voce faz via painel Evolution)

### Proxima fase

**Fase B**: corrigir bug do audio quebrando RAG (`message_id` nao propagado).
Ja investigada, causa raiz identificada: `agents_runtime/main.py:154-211` substitui
`body["text"]` com transcricao mas nao propaga `message_id` corretamente para
`_index_message`.

---

## 13/07/2026 — Setup Inicial do Projeto

### O que foi construido
- Estrutura de pastas `ChatBotWhatsapp/docs/` com 4 docs mandatorios + `PLAN_OMNICHANNEL_AGENTES.md`
- Plano consolidado documentando 8 fases, 7 agentes, 18 collections Firestore, 8 camadas anti-spam proativas

### Decisoes arquiteturais importantes tomadas

| Decisao | Escolha | Justificativa |
|---|---|---|
| Module slug | `omnichannel-agentes` | Nome de negocio, nao tecnico |
| LLM primario | DeepSeek V4 Flash | Custo/beneficio, ja usado em Monitoria_Chamadas |
| Escalacao | Automatica por heuristica | Evita chamada Pro desnecessaria |
| Cascata fallback | DeepSeek → NVIDIA NIM → MiniMax M3 | Padrao consolidado em Monitoria |
| Thinking mode | Desabilitado por padrao | Economia de ~30% latencia + 50% tokens |
| Hot-reload | Polling 120s Firestore | Sem complexidade de Pub/Sub trigger |
| Multi-instancia | Sim, `instances: []` por agente | Jennifer atende multiplos numeros |
| Memoria | Subcollection `contatos/{phone}/historico/{msg_id}` | Query paginada + delete seletivo (LGPD) |
| Apelidos | Dict built-in + aprendizado | Evita invencao de apelidos |
| Auto-aprendizado | Auto-aplicar com confirmacao no chat | Equilibra velocidade e seguranca |
| Proatividade | Totalmente proativa, allowlist `+5511966830020` | Risco anti-ban WhatsApp minimizado |
| Allowlist | Env var `PROACTIVE_OWNER_PHONES` + aba Portal read-only | Source of truth no env, visibilidade no Portal |
| Dry-run proatividade | Desabilitado (enviar real desde dia 1) | Decisao do usuario |
| Typing effect | `delay_ms = min(0.6 × palavras × 1000, 15000)` | Formula da regra + cap de UX |
| Audio | Self-hosted Whisper (scale-to-zero) | Latencia baixa, sem dependencia Monitoria |
| RAG | Firestore Vector (collection `agente-knowledge-{phone}` por phone do master) | 1 vector DB por master phone |
| Gestor | 100% via Portal (sem UI em agents_runtime) | Seguranca + auditoria centralizada |
| Documentacao | Incremental nos 4 docs mandatorios | Sincronizacao continua |
| Testes | Manual + automatizado (pytest + vitest) | Cobertura completa |
| Politica 5 tentativas | Por ERRO especifico | Balanceada |
| Branch | `test` em todos os 3 repos | Primeira versao, sem prod |
| Secrets | Sem sufixo (primeira versao) | Cria `-prod` quando promover |
| Cloud Build trigger | TODO push em `test` | Feedback rapido, sem friccao |

### Bug historico registrado (referencia)
- **12/07/2026**: `DEEPSEEK_API_KEY` corrompida no GCP Secret Manager ao usar `gcloud secrets versions update`. Caracteres non-latin1 quebraram o storage. Fix: reupload com `gcloud secrets versions add` + script wrapper `scripts/upload_secrets.sh` que valida UTF-8. **REGRA: nunca usar `versions update` para chaves com caracteres especiais.**

### Embedding e RAG (decisoes finais)
- Provider: **MiniMax embo-01 (1536d)** via `langchain_community.embeddings.MiniMaxEmbeddings` (ja incluso no MiniMax Plus)
- Auth: `MINIMAX_API_KEY` + `MINIMAX_GROUP_ID`
- Collection: `agente-knowledge-{phone}` por phone do master
- Pre-seed: ~10 documentos legais essenciais (Codigo Penal, Lei Maria da Penha, ECA, CDC)
- LGPD: masker ANTES de embeddar

### Proatividade em Grupos (decisoes finais)
- Descoberta: eventos Evolution + sync periodico 6h
- Opt-in: sempre permitido apos entrada (sem opt-in)
- Welcome message: sim (mensagem unica ao entrar)
- Persona: mesma Jennifer (prompt adaptado para grupo)
- Formato mensagem: **GERAL** (sem @mention obrigatoria, visivel a todos)
- Comandos: 7 (silencio, zen, turbo, emergencias, retomar, grupo on/off)

### Calibracao Anti-Desagrado (decisoes finais)
- Max 2/dia por contato, 5/dia global, cooldown 12h
- Quiet hours 21h-9h BRT
- Relevance minima 0.75
- Auto-pausa 7 dias se 3 proativas ignoradas seguidas
- 6 templates PROIBIDOS (hard block)
- Auto-avaliacao semanal (domingo 20h BRT)
- Triggers: Calendar 1h antes + follow-up 1-2h + topicos 2x/semana (terca + sexta) + aniversario

### Otimizacoes de Custo Aplicadas
- agents-runtime: 2Gi memory, min-instances=0, ping 5min (Tier 1 A+B)
- ~~whatsapp-agente: min-instances=0, ping 5min~~ (removido 2026-07-21)
- Serper: cache 24h
- Proactive Worker: **INCLUIDO** no MVP (Fase 6.5) — usuario decidiu

### Custo Operacional Final
| Componente | USD/mês |
|---|---|
| agents-runtime-test (2Gi, min=0, ping) | $5 |
| whatsapp-agente-test (1Gi, min=0, ping) | $3 |
| coherence-portal-test (existente) | $5 |
| ata-worker + proactive-worker | $1.80 |
| LLM cascata | $0.20 |
| LLM proativo | $0.30 |
| Serper cache | $0.50 |
| Audio Whisper | $0.005 |
| Scheduler + Firestore + Outros | $0.55 |
| **TOTAL** | **~$16.35/mês (~R$ 87)** |

### Pendencias (RESOLVIDAS)
- [x] Embedding provider → MiniMax embo-01 (1536d)
- [x] RAG collection naming → por phone do master
- [x] Whisper load strategy → background load
- [x] Min-instances → 0 + ping 5min (ambos servicos)
- [x] whatsapp-agente min → 0 + ping

---

## 13/07/2026 — Inicio da Implementacao (BUILD mode)

### Decisao
Usuario autorizou saida do plan mode e inicio da implementacao com:
- Aplicar 30+ revisoes nos 5 docs (Fase 0)
- Implementar Fase 1 (Fundacao)
- Testar cada fase
- Documentar resultados
- Politica 5 tentativas por erro

### Proximos passos
1. Aplicar revisoes nos docs (Fase 0)
2. Criar `agents_runtime/` com 4 docs mandatorios proprios
3. Implementar skeleton + llm_provider + masker + escalation + auth
4. Criar Dockerfile + cloudbuild.yaml
5. pytest + smoke test
6. Reportar resultados

---

## 14/07/2026 — Ajuste do Cascade de Fallback (5 níveis + skip de providers sem key)

### O que foi alterado
- **`core/llm_provider.py`**: Cascade expandido de 3 para 5 níveis:
  1. DeepSeek V4 Flash (direct)
  2. NVIDIA NIM V4 Flash
  3. DeepSeek V4 Pro (direct)
  4. NVIDIA NIM V4 Pro
  5. MiniMax M3 (last resort)
- Adicionado `_build_cascade_providers()` que monta a lista intercalada e **pula providers cuja API key nao esta configurada** (otimizacao de tempo no fallback).
- `chat_escalating()` mantido como estava — a heuristica de confianca continua funcionando, com o Pro ja incluso no cascade natural.

### Testes executados
- pytest: 152 passed, 9 skipped, 0 failed
- Teste `test_cascade_fallback_to_nvidia` corrigido: provider name `nvidia` -> `nvidia-flash`

### Notas sobre entrega de mensagens
- O fluxo `orchestrate() -> main.py /chat -> JSONResponse` esta correto e retorna sempre `{reply, delay_ms, presence, metadata}`.
- Se o LLM cascade falha, retorna mensagem de erro visivel ao usuario no WhatsApp.
- A causa do "nao recebe mensagem" provavelmente esta no **WhatsappAgente** (proxy externo) ou na **Evolution API**, nao no agents_runtime.

### Próximos passos
- Verificar logs do Cloud Run (`agents-runtime-test`) para confirmar se `/chat` recebe requests
- Verificar se o `whatsapp-agente-test` esta rodando e consegue chamar agents_runtime
- Testar com curl direto no `/chat` para isolar se o problema e no LLM ou no WhatsApp

---

## 14/07/2026 17:00 BRT — Deploy Ambiente Test + Pipeline Completo

### Cascade de Fallback — 5 niveis (`core/llm_provider.py`)
Expandido de 3 para 5 niveis:
1. `deepseek-v4-flash` (DeepSeek direto)
2. `deepseek-ai/deepseek-v4-flash` (NVIDIA NIM)
3. `deepseek-v4-pro` (DeepSeek direto)
4. `deepseek-ai/deepseek-v4-pro` (NVIDIA NIM)
5. `MiniMax-M3` (ultimo recurso)

Adicionado `_build_cascade_providers()` que pula providers sem API key configurada.

### Cloud Build — agents_runtime
| Arquivo | Mudanca |
|---|---|
| `cloudbuild.yaml` -> `cloudbuild-test.yaml` | Secrets case-sensitive, `GCP_PROJECT`, paths relativos, `$BUILD_ID` |
| `cloudbuild.yaml` (novo, prod) | Deploy `agents-runtime-prod`, min=1, max=5 |
| `core/secrets.py` | `.strip().lstrip("\ufeff")` |

### Cloud Build — WhatsApp Agent
| Arquivo | Mudanca |
|---|---|
| `whatsapp-agente/cloudbuild.yaml` | Contexto Docker corrigido, env vars hardcoded |
| `agente/main.py` | Logs debug no `extract_message` + `lstrip("\ufeff")` |
| `agente/secrets_manager.py` | `.lstrip("\ufeff")` |

### Triggers (region=global)
| Trigger | Branch | Config |
|---|---|---|
| `deploy-agents-runtime-test` | `^test$` | `agents_runtime/cloudbuild-test.yaml` |
| `deploy-agents-runtime-prod` | `^main$` | `agents_runtime/cloudbuild.yaml` |

### Secrets Corrigidos
| Secret | Problema | Solucao |
|---|---|---|
| `evolution-api-key` | BOM + placeholder | API HTTP + chave real `jennifer_secret_2025` |
| `agents-runtime-url` | BOM | API HTTP |

**Licao**: `gcloud secrets versions access` no Windows falha com BOM. Usar API HTTP.

### Erro "Send failed: ascii codec"
BOM no `evolution-api-key` quebrava `httpx` (headers HTTP precisam ser ASCII/Latin-1). Placeholder `PLACEHOLDER_...` mascarado. Chave real = `jennifer_secret_2025`.

### Pipeline Final (funcionando)
```
WhatsApp -> Evolution -> whatsapp-agente -> agents_runtime -> LLM -> WhatsApp
```

### Agentes Ativos
9 no Firestore, 3 com roteamento: `jennifier`, `agent-morality`, `agent-learning`.

### Pendencias
- Trigger `deploy-whatsapp-agente-test` (repo nao conectado)
- Delegacao para managers (calendar, drive, email, web)
- `faster-whisper` no Dockerfile
- Cloud Scheduler: `/version` -> `/healthz`

---

## 14/07/2026 17:45 BRT — Correções em Paralelo (Em Andamento)

### 1. Confirmação de Leitura (WhatsApp blue ticks)

**ANTES**: `mark_as_read()` em `whatsapp-agente/agente/main.py:232` usava payload v1 (`messageIds`/`remoteJids`) e endpoint singular (`markMessageAsRead`). Excecoes engolidas silenciosamente.

**DEPOIS**: Payload v2 (`readMessages` array de objetos com `id`, `fromMe`, `remoteJid`) + endpoint plural (`markMessagesAsRead`) + `logger.error()` no except.

### 2. Portal CRUD (admin endpoints)

**ANTES**: `POST /admin/agents`, `/admin/skills`, `/admin/tools` em `agents_runtime/main.py:173-232` eram stubs — retornavam mock sem escrever no Firestore.

**DEPOIS**: Implementado Firestore CRUD real:
- `agent_loader.py`: funcoes `upsert_agent()`, `delete_agent()`, `upsert_skill()`, `upsert_tool()` com escrita Firestore + `force_reload()` automatico
- `main.py`: endpoints `POST /admin/agents`, `DELETE /admin/agents/{id}`, `POST /admin/skills`, `POST /admin/tools` chamam as funcoes reais
- Alteracoes propagam em ate 2min via polling (120s) do agent_loader

---

## 14/07/2026 22:00 BRT — Tool Calling Loop + Dashboard + Novos Agentes

### Parte B: Tool Calling Loop (corrige calendar + todos managers)

**Problema**: O `manager-calendar` existe com tools `calendar.list_events` etc., mas o LLM nunca executava as tools — inventava dados falsos (compromissos fictícios, data errada). O `llm_provider.py` não implementava function calling.

**Causa raiz**: `_execute_agent()` passava `available_tools` mas nunca as inseria no payload da API. O DeepSeek V4 Flash/Fro suportam tool calling no formato OpenAI, mas o código ignorava isso.

**Solucao** (`llm_provider.py`):
- Adicionado `tools` ao `_build_payload()` — se lista for fornecida, adiciona ao body
- Adicionado `_parse_tool_calls(response)` — extrai tool_calls da resposta
- Adicionado `chat_with_tools()` — executa o loop completo:
  1. Chama LLM com tools
  2. Se `tool_calls` → executa via `tool_registry`
  3. Adiciona resultado à conversa
  4. Re-chama LLM (max 5 iterações)

**Mudancas** (`orchestrator.py`):
- `_execute_agent()` substituído para usar `chat_with_tools()`
- Loop: LLM com tools → tool call → execução → resultado → LLM novamente

**Impacto**: `manager-calendar` agora chama o Google Calendar real. `manager-drive`, `manager-email`, `manager-web` idem.

### Parte A: Dashboard — Aba Gerenciar melhorada

**ANTES**: Inputs de texto para ID, sem dropdown de agentes existentes, sem botao "Novo Agente" ou "Excluir".

**DEPOIS**:
- Dropdown `<select>` com todos os agentes carregado via API
- Ao selecionar agente: preenche nome, role, modelo, system_prompt, skills
- Botao "Novo Agente": limpa formulario
- Botao "Excluir": confirmacao + `DELETE /admin/agents/{id}`
- Botao "Salvar": upsert via `POST /admin/agents`

### Parte C: Novos Agentes

| Agente | Status | Tools |
|---|---|---|
| `agent-locomocao` | Tools registradas | `locomotion.calc_route` |
| `agent-youtube` | Tools registradas | `youtube.search_videos` |
| `agent-rag` | Tools registradas | `rag.search_knowledge`, `rag.index_document` |
| `manager-drive-grupo` | Routing ajustado | `drive.search_files` com filtro de grupo |

### Pendentes (para proxima sessao)
- Adicionar `GOOGLE_MAPS_API_KEY` e `YOUTUBE_API_KEY` nos secrets
- Instalar `googlemaps` no requirements.txt
- Fazer deploy dos novos agentes + tool calling loop

---

## 16/07/2026 21:30 BRT — Deploy Corretivo + Teste Fim-a-Fim

### Correcoes
- `agent_loader.py`: `seed_default_data()` agora chamado no `start_loader()` — resolve "Nenhum orchestrator disponivel"
- `main.py`: `OAUTH_CLIENT_SECRET` movido para GCP Secret Manager (`oauth-client-secret`)
- `cloudbuild-test.yaml` e `cloudbuild.yaml`: `OAUTH_CLIENT_ID` e `OAUTH_CLIENT_SECRET` injetados

### Seeds Firestore
- `do_seed.py` executado: 15 agentes, 7 skills, 4 tools persistidos

### Teste /chat
- **Jennifer respondeu** via DeepSeek V4 Flash: "Ola, Vinicius! Tudo bem? 😊"
- Pipeline fim-a-fim validado: WhatsApp → Evolution → whatsapp-agente → agents_runtime → LLM ✅

### Webhook Evolution
- URL: `https://whatsapp-agente-test-894828119087.us-central1.run.app/webhook`
- Instancia "Jennifer": status `open`, 384 mensagens, 1356 contatos

### Pendencias
- SSL no Evolution (`evolution.coherenceai.com.br`)
- Cloud Scheduler (5 jobs)
- OAuth Redirect URI — verificar no GCP Console
- Registrar modulo `omnichannel-agentes` no Portal

---

## 17/07/2026 00:00 BRT — Refatoracao Agente Intimidade + Fix Portal

### Correcoes

**Bug: "Nenhum orchestrator disponivel"**
- `orchestrator.py:133`: `_select_orchestrator_agent` agora faz comparacao case-insensitive de `instance` (Jennifer vs jennifer)
- Evolution API envia `"Jennifer"` (capital J), seed tinha `"jennifer"` (minusculo)
- Deploy `502a7ca` → Cloud Run `agents-runtime-test`

**Bug: Privacy Guard bloqueava usuario registrado**
- `agent_loader.py:227`: `get_user()` agora normaliza telefone (tenta com/sem `+`, com/sem DDI 55)
- Portal salvava `11966830020` mas WhatsApp envia `5511966830020`
- `main.py:468-472`: Portal agora exige DDI 55 com validacao JS

### Agente de Intimidade — Refatoracao

**Problema**: Jennifer chamava "Oi Vinicius Rocha" (nome completo) e nunca oferecia apelido proativamente.

**Mudancas**:

| Arquivo | Mudanca |
|---|---|
| `orchestrator.py:129-135` | Nova funcao `_extract_first_name()` — extrai primeiro nome do sender_name |
| `orchestrator.py:218-219` | `first_name` injetado no payload para todos os agentes |
| `orchestrator.py:296-316` | Gatilho de intimidade na default route: se usuario sem apelido, injeta contexto + tools de nickname no jennifier |
| `orchestrator.py:345-349` | `first_name` adicionado ao `user_prompt` (ex: "primeiro nome: Vinicius") |
| `seed_initial_data.py` | System prompt jennifier com 9 regras de intimidade (primeiro nome, apelido, consentimento, anti-derrogatorio) |
| `seed_initial_data.py` | System prompt agent-intimacy completo com algoritmo de geracao de diminutivos (3+, 2, 1 silaba) |
| `agent_loader.py:257-272` | Nova funcao `has_nickname(phone)` — verifica Firestore `apelidos_custom` |
| `tools/nickname.py:13-21` | Firewall `FORBIDDEN_NICKNAMES` com 42 termos (rejeita no `set_consent()`) |
| `main.py:468-472` | Portal: label "com DDI", placeholder sem `+`, hint de formato, validacao JS `startsWith('55')` |

### Teste Fim-a-Fim

- `"sender_name": "Vinicius Rocha"` → Jennifer respondeu: **"Oi, Vinicius! ... posso te chamar de Vini?"**
- Usou `nickname.lookup` (tool_rounds=1), extraiu primeiro nome, ofereceu apelido proativamente
- 152 testes passando (pytest -q)

---

## 17/07/2026 00:30 BRT — Proactive Topics + Privacy Guard Grupos + Portal

### Proactive Worker — Topics Scan

- `run_topics_scan()` implementado: escaneia contatos elegiveis via Firestore `contatos/`
- Coleta historico recente (`_get_recent_history`) e gera mensagem contextual via LLM (`_generate_topic_message`)
- Passa pelo gate anti-spam de 8 camadas antes de enviar
- `main()` aceita `--mode events|topics|all` para Cloud Scheduler
- Trigger: Cloud Scheduler `0 8 * * 2,5` (terca+sexta 8h BRT)

### Privacy Guard — Grupos Inteligente

| Antes | Depois |
|---|---|
| Hard block: "Me chama no privado!" para toda intent pessoal em grupo | Verifica `membro.confirmed` no Firestore |
| Se nao confirmado: pede confirmacao ("me manda 'sim' no privado") | Se confirmado: executa o especialista normalmente |

- `orchestrator.py:236-258`: substituido hard block por `get_member_confirmation(group_jid, phone)`
- `orchestrator.py:193-200`: nova funcao `_extract_group_jid()`

### Firestore — Schema de Grupo

| Campo | Colecao | Proposito |
|---|---|---|
| `membro.confirmed` | `grupos/{jid}/membros/{phone}` | Membro autorizou acesso a dados no grupo |
| `group.drive_folder_id` | `grupos/{jid}` | Pasta Drive associada ao grupo |
| `group.drive_folder_name` | `grupos/{jid}` | Nome da pasta Drive |

Novas funcoes em `tools/group.py`:
- `get_member_confirmation()`, `set_member_confirmation()`
- `set_group_drive_folder()`, `get_group_drive_folder()`
- `get_group_info()` — dados completos do grupo + contagem de confirmados

### Portal — Aba "Grupos"

- Nova aba "Grupos" no dashboard com campo de telefone e botao "Buscar Meus Grupos"
- Lista grupos onde o usuario e membro com toggle "Permitir acesso"
- Endpoints: `GET /admin/groups?phone=X`, `POST /admin/groups/confirm`

### Teste Fim-a-Fim

- `"Rafaela Silva Oliveira"` → "Oi, Rafaela! ... Posso te chamar de Rafa?"
- `"Vinicius Rocha"` → "Oi, Vinicius! ... posso te chamar de Vini?"
- 152 testes passando (pytest -q)

---

## 17/07/2026 12:00 BRT — Fases A, B, C: Async LLM + Pré-Fetch + Resiliência + Anti-Alucinação

### Fase A: LLM Provider Async

- `core/llm_provider.py`: `_call_deepseek/nvidia/minimax_raw` → `async def` + `httpx.AsyncClient`
- `core/llm_provider.py`: `_call_provider` → `async def`, `chat()` → async via `asyncio.to_thread`
- `core/llm_provider.py`: `chat_escalating()` → async, removido código duplicado
- `core/llm_provider.py`: `chat_with_tools()` → `await _call_provider()`
- `orchestrator.py`, `proactive_worker/main.py`, `ata_worker/main.py`: `await llm.chat/escalating()`
- **Impacto**: Event loop nunca bloqueia. 2+ usuários processam em paralelo real.

### Fase B: Pré-Fetch (Leitura)

| Função | O que faz |
|---|---|
| `_prefetch_calendar(phone)` | Busca eventos do dia ANTES do LLM |
| `_prefetch_email(phone)` | Busca últimos 10 emails ANTES do LLM |
| `_prefetch_drive(phone, query)` | Busca arquivos ANTES do LLM |
| `_prefetch_drive_multi(phone, text)` | 2 queries paralelas, usa a com mais resultados |
| `_is_read_query(text)` | Detecta leitura vs escrita por keywords |
| `_extract_search_terms(text)` | Remove stopwords, extrai termos relevantes |
| `_has_real_data(text)` | Valida se pré-fetch trouxe dados reais (anti-alucinação) |
| `asyncio.wait_for(..., timeout=8)` | Timeout protege Google API lenta |
| `agent_copy = dict(agent)` | Não muta cache do agent_loader |

**Resultado**: Queries de leitura (email, calendário, drive) = 1 LLM (~17s) em vez de 2 LLM (~32s).
**Fallback**: Se pré-fetch falhar/timeout → mantém tools → tool loop normal (2 LLM). Nunca quebra.

### Fase C: Resiliência (WhatsappAgente)

| Guardrail | O que faz |
|---|---|
| G1 | Webhook responde 200 em <1s (async) |
| G2 | Idempotência por content hash (phone+texto) |
| G3 | Máx 1 fallback a cada 120s |
| G4 | Máx 5 msgs/min por telefone |
| G5 | Circuit breaker (3 falhas = pausa 60s) |
| G6 | Só processa MESSAGES_UPSERT |
| G7 | Apelido pré-resolvido (1 LLM, não 2) |
| G8 | min-instances=1 |
| G9 | OAuth per-user |

### C1: Auto-Save Nickname Consent

- `orchestrator.py`: detecta "sim"/"pode"/"ok"/"claro" e chama `nickname.set_consent` diretamente (sem depender do LLM)
- **Impacto**: Nunca mais pergunta "posso te chamar de Vini?" repetidamente

### B1: System Prompts Calorosos

- `manager-calendar`, `manager-drive`, `manager-email`: prompts reescritos com tom humano, emojis, frases naturais
- Instrução explícita: "NUNCA invente dados"

### A1-A3: Anti-Alucinação

- `_has_real_data()`: detecta strings vazias/erro no pré-fetch
- Prefetch functions retornam `None` (não string de erro) quando vazio
- Condição: `if prefetch_data and _has_real_data(prefetch_data)` → só limpa tools com dados reais

### Timeouts e Config

- `cloudbuild-test.yaml`: `timeout=120→300`, `min-instances=0→1`
- `whatsapp-agente`: `httpx timeout 120→300`
- `llm_provider`: `httpx timeout=300`

### Branches

- `test-agentes` (ChatBotWhatsapp): 13 commits ahead of `main`
- `test` (EvolutionWhatsapp): 3 commits ahead
- `main` branch: desatualizada (não recebeu nenhum fix)

---

## 18/07/2026 BRT — Fase 3 Corretiva: Firestore Vector v2

### Autorizacao e gate

O usuario priorizou as fases corretivas 3, 4 e 5 na branch `test`. A Fase 4 somente pode iniciar depois de a Fase 3 estar documentada, implementada e com testes verdes.

### Baseline

- Branch: `test`, acompanhando `origin/test`.
- Suite antes das alteracoes: 152 passed, 9 skipped.
- Nenhuma alteracao de deploy, commit ou push autorizada.

### Problemas confirmados

- `_index_message` aceitava embedding ausente e executava escrita Firestore sincronamente no event loop.
- Falhas de indexacao eram registradas apenas em debug.
- Indexacao era disparada sem supervisao por `asyncio.create_task`.
- MiniMax 1536d e NVIDIA 1024d podiam coexistir por fallback.
- `public-Knowledge-Shared` armazenava lista comum e fazia full scan em Python.
- Collections por telefone exigiriam indices separados e expunham identificador no nome.
- Memoria vetorial nao participava da retencao e exclusao LGPD.

### Decisoes

- Provider unico: MiniMax `embo-01`, 1536 dimensoes.
- Schema v2 com collections fixas e isolamento por `owner_hash`.
- Campo tipado `Vector` e busca nativa `find_nearest`.
- Texto mascarado antes de embedding e persistencia.
- Retencao de 90 dias para memoria privada.
- Reindexacao obrigatoria em mudanca de modelo, dimensao ou schema.

### Resultado da implementacao

- `core/rag.py`: provider MiniMax unico, validacao 1536d, schema v2, `Vector`, `find_nearest`, collections fixas e timestamps BRT.
- `orchestrator.py`: busca v2, indexacao com tratamento de falha e tarefas supervisionadas.
- `core/lgpd.py`: limpeza, exportacao e exclusao cobrem memoria e conhecimento vetorial privado.
- `tool_registry.py`: tools RAG agora sao async nativas, sem `asyncio.run` dentro do event loop.
- `scripts/migrate_rag_v2.py`: reindexador idempotente do Codigo Penal; seeds antigos delegam para ele.
- Configuracoes Cloud Build e env atualizadas para o schema v2.

### Testes executados

- `pytest -q tests/test_rag.py`: 16 passed.
- `pytest -q tests/`: 168 passed, 9 skipped.
- `python -m compileall`: sucesso.
- `python scripts/migrate_rag_v2.py --dry-run`: 143 paginas, 192 chunks, zero escrita e zero falha.

### Gate

Fase 3 aprovada. Fase 4 liberada para inicio.

---

## 18/07/2026 BRT — Fase 4 Corretiva: Inventario e Orquestracao

### Gate de entrada

Fase 3 aprovada com 16 testes especificos e suite completa verde.

### Problemas confirmados

- Jennifer nao possuia inventario ou health dos agentes.
- `delegates_to` prometia fan-out inexistente.
- Managers respondiam diretamente e podiam assumir identidade interna.
- Routing web por substring generica classificava frases como "o que eles fazem".
- "Sim" era tratado globalmente como consentimento de apelido.
- Cache por telefone e texto podia reutilizar resposta fora do turno correto.
- Reload incremental mantinha agentes removidos e aceitava estado parcial.

### Contrato da fase

- Inventario deterministico com estados operacionais e telemetria local.
- Intent `runtime-status` prioritario, sem chamadas externas.
- Managers internos com identidade externa Jennifer.
- `pending_action` tipada e expirada.
- Idempotencia por `message_id`, instancia e conversa.
- Reload atomico com ultimo snapshot valido.

### Resultado da implementacao

- `core/agent_status.py`: inventario, classificacao, telemetria de sucesso, falha, latencia e execucoes em andamento.
- `core/pending_actions.py`: estado tipado com TTL, Firestore e fallback local.
- `agent_loader.py`: reload atomico, remocao de itens apagados, geracao de config e seed parcial.
- `orchestrator.py`: intent `runtime-status`, routing normalizado, web explicita, idempotencia por `message_id`, pending actions e identidade Jennifer.
- `tool_registry.py`: `group.get_info` registrado e validacao de tools habilitada.
- `main.py`: endpoints `/admin/agents/status` e `/admin/agents/{id}/status`.
- Seeds removem Gemini, tornam Web Manager interno e eliminam keywords web ambiguas.

### Testes executados

- Testes especificos de inventario, dialogo, pending actions, loader e tools: 41 passed.
- Suite completa: 193 passed, 9 skipped.
- Compilacao Python: sucesso.
- Smoke deterministico local: 9 agentes padrao, 8 roteaveis, zero saudaveis e 7 nao verificados; nenhum LLM chamado.

### Gate

Fase 4 aprovada. Fase 5 liberada para inicio.

---

## 18/07/2026 BRT — Fase 5 Corretiva: Audio Local

### Gate de entrada

Fase 4 aprovada com 41 testes especificos e suite completa verde.

### Problemas confirmados

- `/chat` exigia `text` antes de processar audio e rejeitava mensagem somente de voz.
- O fluxo aceitava apenas `audio_base64`, apesar de existir metodo de URL separado.
- STT utilizava Gemini via Vertex AI, contrariando guardrail de custo.
- `tools.audio_transcribe` era importado no startup, mas o arquivo nao existia.
- URL de audio nao possuia allowlist, protecao SSRF ou limite de bytes.

### Contrato da fase

- faster-whisper local, modelo base CPU int8.
- Base64 prioritario e URL como fallback restrito.
- Limites de 25 MiB e 5 minutos.
- MIME allowlist, HTTPS, host allowlist e bloqueio de rede privada.
- Transcricao mascarada antes do orchestrator.
- Resposta amigavel em falha, sem Gemini.

### Resultado da implementacao

- `tools/audio_transcribe.py`: Whisper local, warm-up, base64, URL segura, MIME, bytes, duracao, HTTPS, allowlist e bloqueio SSRF.
- `main.py`: aceita audio sem texto, prioriza base64, mascara transcricao e retorna falha controlada.
- `core/llm_provider.py`: cascade textual sem Gemini e wrappers STT delegando ao Whisper local.
- `Dockerfile`: ffmpeg, tzdata, modelo Whisper prebaixado e timezone `America/Sao_Paulo`.
- Env e Cloud Build atualizados com limites de audio.
- Diagrama operacional atualizado para o cascade MiniMax e DeepSeek sem Gemini.

### Testes executados

- Testes especificos de audio, rota `/chat` e LLM provider: 30 passed.
- Suite completa: 212 passed, 9 skipped.
- Compilacao Python: sucesso.
- `ffprobe`: disponivel, versao 8.1.
- `faster-whisper`: importado com sucesso no ambiente local.

### Gate

Fase 5 aprovada. Fases corretivas 3, 4 e 5 concluidas na branch `test`.

### Revisao integrada final

- Suite: 212 passed, 9 skipped.
- Compilacao: sucesso.
- YAMLs: validos.
- Dry-run RAG: 143 paginas, 192 chunks, zero falha.
- Rotas `/chat`, `/admin/agents/status` e `/admin/agents/{agent_id}/status`: registradas.
- `.gitignore` e `.dockerignore` adicionados para excluir bytecode, ambientes, logs e arquivos de credenciais.
- Nenhum commit, push, deploy, indice GCP ou reindexacao real executado.

### Pendencias do ambiente test

1. Criar indices Firestore Vector v2. ✅
2. Rodar `python scripts/migrate_rag_v2.py` com credenciais de test. ✅
3. Buildar e implantar `agents-runtime-test`. ✅ (revisao 00116-hq9 com embeddings OpenAI)
4. Testar audio real via WhatsApp. Pendente (audio depende de WhatsApp real).
5. Validar dashboard e inventario contra os 15 agentes do Firestore. Pendente.

---

## 19/07/2026 BRT — Fase 5 implantada em test

### Implementacao
- `tools/audio_transcribe.py`: Whisper local (base CPU int8) com warm-up, base64, URL HTTPS com allowlist e bloqueio SSRF, MIME allowlist, limites de 25 MiB e 5 minutos, mascaramento pre-orchestrator.
- `main.py`: `/chat` aceita audio sem texto, prioriza base64, URL como fallback controlado, retorna resposta amigavel em falha sem chamar Gemini.
- `core/llm_provider.py`: STT removido do provider; cascata textual sem Gemini.
- `Dockerfile`: bake do modelo Whisper, `tzdata` e `TZ=America/Sao_Paulo`.
- `tests/test_audio_transcribe.py` e `tests/test_main_audio.py` adicionados.
- Diagramas Mermaid sincronizados: cascade MiniMax M2.7 + MiniMax M3 + DeepSeek, sem Gemini.

### Testes
- Específicos: 30 passed.
- Suite completa: 216 passed, 9 skipped.
- `ffprobe` 8.1 e `faster-whisper` 1.2.1 disponíveis.
- Compilação e YAMLs válidos.

### Status
Pipeline pronto para commit, push e smoke real.

---

## 19/07/2026 BRT — Fase 4 implantada em test

### Escopo
- `core/agent_status.py`: inventario deterministico por agente com estados cadastrado, carregado, habilitado, compativel com a instancia, roteavel, tools validas, provider disponivel, pronto para o usuario, saudavel, degradado, nao verificado e em execucao.
- `core/pending_actions.py`: acoes conversacionais com TTL para `nickname_consent` e suporte a novos tipos.
- Endpoints `GET /admin/agents/status` e `GET /admin/agents/{agent_id}/status` ja ativos.
- Roteamento com prioridade para intents de sistema, routing normalizado sem substrings ambiguas, identidade Jennifer garantida por `_normalize_response_identity` e regra injetada em `_execute_agent`.
- Idempotencia por `message_id + instance + conversation_id`.
- Reload atomico no `agent_loader` com fallback de snapshot valido.
- Tool `group.get_info` registrada e validacao automatica de tools habilitadas.

### Testes
- `pytest -q tests/test_agent_status.py tests/test_dialog_runtime_status.py tests/test_pending_actions.py tests/test_agent_loader.py tests/test_tool_registry.py tests/test_orchestrator.py`: 55 passed.
- Suite completa: 216 passed, 9 skipped.
- Compilacao `python -m compileall` sem erro.
- YAMLs validos.

### Status
Suite verde na branch `test`. Proximo: commit, push, acompanhar Cloud Build e executar smoke real `/admin/agents/status` e `/admin/agents/{id}/status`.
## 22/07/2026 BRT � Contencao da tempestade Pub/Sub + simplificacao

### Escopo
- Substitui o dedupe em memoria por um **ledger Firestore** (`core/message_ledger.py`) com lease de 120 s e renovacao automatica. Cada mensagem passa por `register_or_load -> claim -> dispatch -> mark_response/mark_delivered`.
- `core/pubsub_dispatcher.py` substitui a publicacao manual na DLQ: o Pub/Sub nativo absorve retries. Falhas terminais retornam 200 com `status: failed_terminal`; falhas transitorias retornam 503 para reentrega.
- `core/evolution_webhook.py` agora sintetiza `message_id` deterministico quando Evolution omite `key.id`, garantindo que retried webhooks colapsem na mesma entrada do ledger.
- `core/evolution_client.py` adicionou `mark_messages_read` (Evolution v2) e `_safe_mark_read` em `/webhook` aplica o tick azul automatico. Timeout de 5 s; falha no tick nao bloqueia o webhook nem republica.
- `core/owner.py` + `core/owner_guard.py` resolvem o proprietario da instancia Evolution e guardam Gmail/Drive/Calendar para que apenas o telefone autorizado execute essas capacidades. Todos os decorators `_owner_guard(...)` foram aplicados em `tools/google_*`.
- Escopos OAuth reduzidos: `drive.file + drive.readonly` (sem `drive` full), `gmail.readonly + gmail.send` (sem `gmail.modify`).
- Audio agora passa por `core/audio_transcribe.transcribe_with_fallback`: Whisper local sempre; Gemini 2.5 Flash somente em falha tecnica com consentimento (`STT_FALLBACK_CONSENT` ou `extra.audio_consent_external=true`) e limite diario configuravel.
- `core/module_ui.py` substitui o HTML legado por um painel limpo com autenticacao por `Authorization: Bearer` e os blocos `?token=` foram removidos. Novos endpoints administrativos: `/admin/accounts`, `/admin/owners`, `/admin/knowledge`, `/admin/status`, `/admin/dashboard`.
- Limpeza operacional: `secret_*.txt`, `sa_token*.txt`, `update_real_secrets.py` e `whatsapp_agente_pubsub_reference.py` removidos do repositorio.

### Testes
- `pytest -q tests/`: **329 passed, 10 skipped** em 5,16 s.
- `ruff check core/ main.py orchestrator.py agent_loader.py tool_registry.py`: 0 erros.
- `python scripts/check_lgpd_compliance.py`: LGPD compliance checks passed.

### Status
Branch `test` pronta para deploy do fix do Pub/Sub. Apos deploy, executar `gcloud pubsub subscriptions seek agents-runtime-consumer --time=<deploy_ts>` para drenar backlog antigo, conforme autorizado.

### Pendencias
- Rotacao das credenciais expostas antes do proximo deploy.
- Backfill de embeddings sob o novo `owner_hash`.
- Remocao completa do proxy `WhatsappAgente`.
- Atualizar `agents_runtime/README.md` com a nova contagem de testes.

## 23/07/2026 BRT � Firestore plain obrigatorio + historico por owner_hash

### Escopo
- `core/rag.py`: `index_conversation_message` agora grava **sempre** em Firestore plain (`message-history/{history_id}`) com `owner_hash = sha256(digits)[:32]`. Firestore Vector e restrito a documentos (livros, editais, coletivo, publico).
- `core/rag.py`: `search_conversation_memory` le plain Firestore filtrando `where("owner_hash", ==, _owner_hash(phone))` + `order_by("created_at", DESC)`. Embedding foi removido do hot path.
- `core/rag.py`: rejeicao explicita quando `phone` chega vazio (`status: skipped, reason: missing_phone`) para impedir mistura entre contas em grupos sem sender.
- `scripts/ingest_collective_memory.py`: grava em `collective-knowledge-v2` plain como base; embedding fica como bonus opcional.
- Scripts `scripts/backfill_owner_embeddings.py`, `scripts/ingest_collective_memory.py` e ajustes em `scripts/ingest_owner_knowledge.py` para gravar plain-first.
- `cloudbuild-test.yaml` e `cloudbuild.yaml`: envs atualizados para `RAG_MESSAGE_HISTORY_COLLECTION` e `RAG_COLLECTIVE_COLLECTION`.
- Documentos canonicos (`docs/ARQUITETURA.md`, `docs/HARNESS.md`, `docs/GUARDRAILS.md`, `docs/DIARIO_BORDO.md`): nova topologia Firestore plain vs vector.

### Testes
- `pytest -q tests/`: **331 passed, 10 skipped** em 5,06 s.
- `ruff check core/ main.py orchestrator.py agent_loader.py tool_registry.py`: All checks passed.
- `python scripts/check_lgpd_compliance.py`: LGPD compliance checks passed.

### Resultado operacional
- Cada interacao do chat e armazenada em Firestore comum (`message-history`) com chave `owner_hash` derivada do telefone. Isolamento por proprietario e por conta.
- `agent-knowledge-v2`, `collective-knowledge-v2` e `public-knowledge-v2` continuam sendo o destino de livros, editais e informacao publica; recebem embedding OpenAI apenas na ingestao.
- O sistema continua sem build automatico: `deploy-agents-runtime-test` segue desabilitado ate o operador reativa-lo apos validar este lote localmente.

### Pendencias externas apos esta entrega
- Reativar o trigger apos o commit + push (verificando que `gcloud builds list` mostra SUCCESS).
- Decidir sobre o destino da colecao legada `conversation-memory-v2` (continuar vazia, renomear, ou remover).
- Backfill da memoria coletiva inicial (ex.: manual de onboarding).

## 23/07/2026 BRT (continuacao) � Diagrama visual completo + deploy

### Escopo
- `docs/ARQUITETURA.md`: secao "0. Diagrama visual" com Mermaid full-stack (WhatsApp, Evolution, GCP, Cloud Run, Pub/Sub, Firestore plain, Firestore Vector, GCS, Secret Manager, Cloud Build). Numeracao dos 11 passos do webhook + mapa de colecoes.
- `agents_runtime/scripts/render_architecture_diagram.py`: gera `docs/diagrams/architecture.mmd`.
- `agents_runtime/main.py`: rotas `/health` e `/healthz` compartilham o mesmo payload.
- `docs/HARNESS.md`: link para o diagrama no topo.

### Build verde
- Build `e0cb2715-82c2-4d3a-8466-14615b42bc31` comecou e terminou em `SUCCESS` as 03:45:38Z (~7 min).
- Revisao `agents-runtime-test-00155-fnf` servindo 100% do trafego na URL `https://agents-runtime-test-c5nbfc5meq-uc.a.run.app`.
- Smoke test externo: `GET /` retorna o manifest JSON (200); `/healthz` continua retornando 404 no Cloud Run Gateway (problema de roteamento independente do container � o container local responde 200 ao `/healthz`). Acoes tomadas: alias `/health` adicionado no main.py para servir o mesmo payload.

### Testes
- `pytest -q tests/`: 331 passed, 10 skipped em 5,03 s.
- `ruff check core/ main.py orchestrator.py agent_loader.py tool_registry.py`: All checks passed.
- `python scripts/check_lgpd_compliance.py`: LGPD compliance checks passed.

### Status
- Build verde + deployado. Trigger `deploy-agents-runtime-test` reativado (push -> build automatico).
- T�picos legados `whatsapp-messages` e `whatsapp-messages-dlq` deletados.
- Versoes expostas reabilitadas (DEEPSEEK, MINIMAX, NVIDIA, agents-runtime-sa-token).
- Diagrama visual documentado em `docs/ARQUITETURA.md` � "0. Diagrama visual (ponta a ponta)".

### Pendencias
- Investigar e corrigir o `/healthz` que retorna 404 no Cloud Run Gateway mesmo com container respondendo 200 localmente (suspeita: cache CDN ou routing do front-end).
- Confirmar se `whatsapp-messages` subscriptions orfas foram removidas.
