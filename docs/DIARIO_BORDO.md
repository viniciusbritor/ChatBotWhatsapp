# Diário de Bordo — ChatBotWhatsapp

> Historico cronologico de decisoes tecnicas, alteracoes e bugs para evitar reincidencia.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

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