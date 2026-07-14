# Diário de Bordo — ChatBotWhatsapp

> Historico cronologico de decisoes tecnicas, alteracoes e bugs para evitar reincidencia.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

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
- whatsapp-agente: min-instances=0, ping 5min (Tier 1 adicional)
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