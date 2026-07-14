# Diario de Bordo — agents_runtime

> Historico cronologico de decisoes tecnicas deste modulo.

---

## 13/07/2026 — STATUS FINAL: TODAS AS FASES CONCLUIDAS

### Resumo Global

| Fase | Status | Testes |
|---|---|---|
| Fase 0 — Documentacao | ✅ | n/a |
| Fase 1 — Fundacao | ✅ | 48 |
| Fase 2 — Tool Registry | ✅ | 39 |
| Fase 3 — Orchestrator + Audio + RAG + Groups | ✅ | 44 |
| Fase 4 — Portal UI (10 telas + backend proxy + 12 endpoints) | ✅ | manual |
| Fase 5 — WhatsappAgente thin proxy | ✅ | 14 |
| Fase 6 — Ata Worker | ✅ | 5 |
| Fase 6.5 — Proactive Worker | ✅ | 11 |
| Fase 7 — LGPD + Commands + Audit | ✅ | 16 |
| **TOTAL agents_runtime** | **152 passed, 9 skipped** | |
| **TOTAL WhatsappAgente** | **14 passed** | |
| **GRAND TOTAL** | **166 passed** | |

### Mudanças aplicadas em 2026-07-13 (final do dia)

#### Migração Evolution API
- **IP antigo:** `34.39.162.165` (whatsapp-server)
- **IP novo:** `34.95.181.124`
- **Domínio:** `evolution.coherenceai.com.br` (configurado na Locaweb)
- **Status:** ✅ Jennifer Connected confirmado via Evolution Manager
  - Mensagens: 1.377
  - Contatos: 152.368
  - Versão Evolution: 2.3.7
- **Arquivos atualizados:** 74+ referências em 24 arquivos
  - `EvolutionWhatsapp/CONEXAO.md`, `cloudbuild*.yaml`, `painel/index.html`, `docs/*`
  - `WhatsappAgente/agente/main.py`, `audio_handler.py`, `.env.runtime.test.yaml`, `docs/*`
  - `Coherence_Portal/docs/HARNESS.md`, `DIARIO_BORDO.md`
  - `vinicius_clone/.env.example`, `backend/.env.runtime.yaml`, `integrations/evolution.py`, `docs/*`
  - `Monitoria_Chamadas/docs/CUSTOS.md`
- **Pendências para SSL** (requer ação na VM nova):
  - Instalar certbot + configurar Let's Encrypt para `evolution.coherenceai.com.br`
  - Atualizar webhook no Evolution Manager para nova URL
  - Atualizar GCP Secret `evolution-server-url`

#### Correção número master phone (REVERTIDO após esclarecimento do usuário)
- **ATENÇÃO — DISTINÇÃO CRÍTICA:**
  - `+5511966830020` = **número PESSOAL do usuário** (Vinicius) — usado como **MASTER** allowlist para proatividade
  - `+5511917389901` = **número do CHATBOT** (instance WhatsApp Jennifer) — usado como IDENTIFICADOR da instância
- **Erro inicial:** troquei os dois números. **Revertido.**
- **Regras de proatividade (4 regras finais):**
  1. Proatividade APENAS com `+5511966830020` (DM pessoal)
  2. Proatividade com membros de grupos FECHADOS onde o chatbot (`+5511917389901`) está incluído
  3. Resposta reativa para qualquer pessoa que mandar mensagem (DM ou grupo)
  4. JAMAIS proatividade com quem não está no allowlist (master + grupo)
- **Arquivos atualizados:** 34 referências em 14 arquivos (todos com `+5511966830020` agora)
  - `ChatBotWhatsapp/docs/*` (PLAN_OMNICHANNEL_AGENTES, HARNESS, DIARIO_BORDO)
  - `ChatBotWhatsapp/agents_runtime/` (.env, main.py, orchestrator.py, proactive_worker/main.py)
  - `ChatBotWhatsapp/agents_runtime/tests/` (test_proactive_worker, test_proactive_gate, test_orchestrator)
  - `Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md`
  - `Coherence_Portal/backend/main.py`
  - `Coherence_Portal/frontend/src/pages/agents/Playground.jsx`
  - `WhatsappAgente/tests/test_proxy.py` (sender phone = user, não bot)

### Componentes Fase 7 adicionados

| Arquivo | Funcao |
|---|---|
| `core/lgpd.py` | cleanup_old_history (90d), cleanup_old_audit (5y), export_user_data, delete_user_data |
| `core/commands.py` | detect_command (7 comandos), apply_command, handle_command_if_any |
| `core/audit.py` | log_action, log_chat - integracao com Firestore audit/ |
| `scripts/lgpd_cleanup.py` | Runnable script para Cloud Run Job diario (3am BRT) |
| `tests/test_fase7.py` | 16 testes para LGPD + Commands + Audit |

### Comandos proativos suportados

- "Jennifer, silêncio" → proactive_mode = "off"
- "Jennifer, modo zen" → proactive_mode = "zen" (50% reducao)
- "Jennifer, modo turbo" → proactive_mode = "turbo" (ate 2/dia)
- "Jennifer, só emergências" → proactive_mode = "emergencies"
- "Jennifer, retomar" → proactive_mode = "normal"
- "Jennifer, grupo off" → group_proactive_mode = "off"
- "Jennifer, grupo on" → group_proactive_mode = "normal"

### LGPD Compliance Implementada

- **TTL 90d para historico** (`cleanup_old_history`)
- **TTL 5 anos para audit** (`cleanup_old_audit`)
- **Art. 18 LGPD - Export**: `export_user_data(phone)` retorna tudo do contato
- **Art. 18 LGPD - Right to be forgotten**: `delete_user_data(phone)` remove tudo
- **Comandos proativos no chat** para opt-in/opt-out dinamico
- **Audit log** em todas as acoes (chat, comandos, admin)

### Componentes Fase 4 (Portal UI) criados

**Backend (`Coherence_Portal/backend/`):**
- `agents_runtime_proxy.py` - cliente HTTP com Bearer SA token
- 12 endpoints proxy em `main.py`:
  - GET/POST `/api/admin/agents` (lista, cria/atualiza)
  - GET `/api/admin/agents/{id}` (detalhe)
  - GET/POST `/api/admin/skills` 
  - GET/POST `/api/admin/tools`
  - POST `/api/admin/playground` (teste de mensagem)
  - GET `/api/admin/agents-runtime/cache-stats`
  - GET `/api/admin/contacts` (lista)
  - GET `/api/admin/contacts/{phone}` (detalhe)
  - GET `/api/admin/proactive/config` 
  - GET `/api/admin/proactive/logs`
  - POST `/api/admin/proactive/kill-switch`
  - GET `/api/admin/cost/summary`

**Frontend (`Coherence_Portal/frontend/src/`):**
- `lib/agentsAdmin.js` - cliente API com auth Firebase
- `pages/agents/AgentsLayout.jsx` - shell com sidebar interna
- `pages/agents/AgentCreate.jsx` - form de criacao
- `pages/agents/AgentReview.jsx` - tabela com delete
- `pages/agents/SkillCreate.jsx` - form
- `pages/agents/SkillReview.jsx` - lista
- `pages/agents/ToolCreate.jsx` - form com JSON schema editor
- `pages/agents/ToolReview.jsx` - lista
- `pages/agents/Playground.jsx` - teste de mensagem
- `pages/agents/ContactsList.jsx` - tabela de contatos
- `pages/agents/ProactiveDashboard.jsx` - config + logs + kill switch
- `pages/agents/CostDashboard.jsx` - custos por modelo
- `App.jsx` atualizado com rotas `/admin/agents/*`
- `Dashboard.jsx` - ICON_MAP ganhou `'omnichannel-agentes': Bot`

### Resumo dos testes

```
$ pytest tests/ -q
152 passed, 9 skipped in 3.38s
```

### Pendencias para Deploy (mesmas de antes)

1. git init + push em 3 repos para branch `test`
2. Upload de 9 secrets via `scripts/upload_secrets.sh`
3. Cloud Scheduler triggers:
   - ata-worker (10min)
   - proactive-worker-events (15min)
   - proactive-worker-topics (terca+sexta 8h BRT)
   - lgpd-cleanup (diario 3h BRT) — NOVO
   - ping-warmup x2 (5min cada)
4. Cloud Build triggers para 3 repos
5. Registrar modulo `omnichannel-agentes` no Portal via POST /api/admin/modules/

### Limitacoes Conhecidas

- LLM cascade nao testado com chaves reais (apenas mocks)
- Whisper audio transcricao requer audio real + dependencias
- RAG vetorial requer Firestore vector index criado manualmente
- Agents_runtime e WhatsappAgente em projetos GCP diferentes (cross-project)

---

## Historico de fases anteriores

(Conteudo das fases 0-6.5 preservado abaixo)