# Guardrails e Regras Inegociáveis — ChatBotWhatsapp

> Este arquivo dita as regras DURAS que todos os agentes IA devem obedecer neste projeto.

> **Documento mestre:** [`PLAN_OMNICHANNEL_AGENTES.md`](./PLAN_OMNICHANNEL_AGENTES.md) — plano consolidado.

## Restricoes Severas (O que NUNCA fazer)

### Seguranca
1. **Nenhuma chave de API** hardcoded em código. Sempre via `secrets_manager.get_secret()` ou env var.
2. **Upload de secrets**: usar APENAS `gcloud secrets versions add`, NUNCA `versions update` (bug de encoding 12/07/2026 corrompeu chave DeepSeek).
3. **Sem Gemini API** (Vertex AI ou AI Studio) para inferência. Embeddings via MiniMax embo-01 (NAO Vertex AI text-embedding-005).
4. **agents_runtime NAO expoe Swagger publico** (`/docs`, `/redoc`, `/openapi.json` proibidos).
5. **`/admin/*`, `/chat`, `/proactive/send` exigem Bearer SA token**. Sem excecao.
6. **Sem UI propria em agents_runtime** — toda gestao via Portal com Firebase JWT + super-admin.

### Privacidade (LGPD)
7. **LGPD masker obrigatorio** antes de qualquer envio para LLM externo (DeepSeek, NVIDIA, MiniMax).
8. **PII patterns mascarados**: CPF, RG, telefone, email, cartao, CNPJ.
9. **TTL de 90 dias** para `contatos/{phone}/historico`. Summary agregado permanece.
10. **Audit log LGPD** (SHA-256 do conteúdo) em `audit/` — retencao 5 anos.
11. **Opt-in duplo** para proatividade: usuario deve consentir explicitamente.
12. **Sem mencao a dados sensiveis** em mensagens proativas.
13. **RAG so indexa legislacao/codigo** (nao jurisprudencia com partes identificadas).

### Proatividade (Calibrada)
14. **Max 2 mensagens proativas por dia por contato**.
15. **Max 5 mensagens proativas por dia GLOBALMENTE**.
16. **Cooldown de 12 horas** entre mensagens proativas para o mesmo contato.
17. **Quiet hours 21h-9h BRT** — zero proatividade.
18. **Relevance minima 0.75** (LLM classifica).
19. **Auto-pausa 7 dias** se user nao responder 3 proativas seguidas.
20. **Max 5 proativas/semana por contato**.

### Codigo e Operacao
21. **Sem `$` solto** no código ou em mensagens formatadas (LaTeX conflict). Usar `USD`/`BRL` ou `dolares`/`reais`.
22. **Sem comentarios no código** (regra global).
23. **5 tentativas por ERRO especifico** antes de parar e reportar.
24. **Documentar ANTES de implementar** — 4 docs mandatorios atualizados por fase.
25. **Hot-reload obrigatorio** — toda alteracao de agente/skill/tool deve propagar em <= 2min sem rebuild.
26. **Mudanca de embedding model** requer re-indexacao completa + flag `embedding_model` no doc para identificar epoca.
27. **Firestore Vector v2 usa somente OpenAI text-embedding-3-small 1536d** — fallback de outro modelo ou dimensao na mesma collection e proibido.
28. **Collections vetoriais possuem nome fixo** — isolamento por `owner_hash`; telefone cru nunca integra nome de collection.
29. **Todo documento vetorial** exige `embedding_model`, `embedding_dim`, `schema_version`, `created_at` e campo tipado `Vector`.
30. **Memoria vetorial privada** armazena apenas texto mascarado e possui expiracao de 90 dias.
31. **Whisper background load** obrigatorio (evita cold start penalty para texto).
32. **Status de agentes e deterministico** — consultas operacionais nunca chamam LLM, web search ou todos os agentes.
33. **`healthy` exige sucesso recente** — agente sem execucao ou probe valido recebe `unverified`.
34. **Managers sao internos** — `response_identity` externa e sempre Jennifer; IDs tecnicos ficam apenas na metadata protegida.
35. **Confirmacao exige `pending_action`** — "sim", "pode" e equivalentes nao autorizam nenhuma acao sem estado tipado vigente.
36. **Idempotencia usa `message_id`** — proibido reutilizar resposta apenas por telefone e texto.
37. **Reload e atomico** — falha parcial preserva o ultimo snapshot valido e remocoes do Firestore saem do cache.
38. **Audio STT usa Whisper local** — Gemini, Vertex AI e AI Studio sao proibidos no caminho de audio.
39. **Base64 e o transporte canonico** — URL e fallback controlado por HTTPS, allowlist e protecao SSRF.
40. **Audio possui limites duros** — tamanho maximo configurado e duracao maxima de 5 minutos.
41. **Transcricao e mascarada antes da orquestracao** — audio, base64 e texto cru nunca entram em logs.
42. **Webhook Evolution e unico** (Fase A 2026-07-21) — `POST /webhook` do `agents-runtime` e o unico entry point de mensagens WhatsApp. Proibido criar proxies externos ou duplicatas.
43. **Extrator canonico de payload Evolution** (Fase A 2026-07-21) — toda alteracao no formato do payload Evolution passa por `core/evolution_webhook.py:extract_envelope`. Nenhum codigo fora desse modulo filtra ou normaliza mensagens WhatsApp.
44. **`/webhook` nao exige autenticacao** (Fase A 2026-07-21) — rota publica chamada pela Evolution API. Filtros anti-spam (fromMe, broadcast, instance vazia) sao obrigatorios como compensacao.

45. **Falha de transcricao nao descarta a mensagem** — quando nao existe texto alternativo, indexar somente marcador mascarado de auditoria no RAG; nunca armazenar audio bruto, URL ou transcricao parcial.
46. **Fallback de `message_id` e observavel sem PII** — emitir WARN com `owner_hash`, instancia e indicador de nao idempotencia; telefone bruto e proibido no log.

## Regras de Ouro (O que SEMPRE fazer)

### Persona
1. **Jennifer e assistente corporativa** — tom profissional + humor leve + leve flirt motivacional. Zero linguagem explicita.
2. **Mensagens curtas** (max 4 linhas), exceto atas ou instrucoes.
3. **Portugues brasileiro**, fuso `America/Sao_Paulo`.
4. **1-2 emojis** por mensagem.
5. **Typing effect sempre**: `delay_ms = min(0.6 x palavras x 1000, 15000)`.

### Proatividade (Anti-Desagrado)
6. **Templates PROIBIDOS** (hard block no orchestrator):
   - "Oi, tudo bem?" sem contexto
   - "Senti sua falta"
   - Elogios forcados ("Voce e incrivel!")
   - Memes/piadas aleatorias
   - Mensagens motivacionais genericas
   - "Bom dia!" sem motivo
7. **Comandos do usuario** (afetam modo proativo):
   - `Jennifer, silencio` → para TUDO
   - `Jennifer, modo zen` → reduz 50%
   - `Jennifer, modo turbo` → ate cap 2/dia
   - `Jennifer, so emergencias` → so criticas
   - `Jennifer, retomar` → normal
   - `Jennifer, grupo off/on` → toggle grupo
8. **Auto-avaliacao semanal** (domingo 20h BRT): ajusta thresholds baseado em engagement.
9. **Em grupo**: mensagem GERAL visivel a todos (sem @mention obrigatoria).
10. **Triggers permitidos**: Calendar 1h antes + follow-up 1-2h + topicos 2x/semana + aniversario.

### Memoria
11. **Apelidos com consentimento**: perguntar 1x "Posso te chamar de X?" e respeitar a resposta.
12. **Nunca inventar apelido** — usar apenas do dict built-in (200+ nomes BR) ou perguntar.
13. **Iteracao de contato por NOME** (preferred_name se consentiu, senao display_name), internamente por phone.
14. **Auto-aprendizado exige confirmacao** no chat antes de aplicar patch em system_prompt.
15. **WhatsApp webhook DEVE processar grupos** (`@g.us`) — mudanca do comportamento atual.
16. **Mensagem de boas-vindas obrigatoria** ao entrar em grupo (1x).
17. **Proatividade em grupo = sempre permitida** apos entrada (sem opt-in extra).
18. **LGPD em grupos** — masker antes de exibir nome/mencao de outros membros.

### LLM
19. **Cascata obrigatoria**: DeepSeek V4 Flash → NVIDIA NIM → MiniMax M3.
20. **Escalacao Flash → Pro por heuristica** (threshold -2 default).
21. **Static-first prompts** para otimizar cache automatico do DeepSeek.
22. **Thinking desabilitado por padrao** (opt-in por agente via `thinking: enabled` no Firestore).
23. **Fallback gracioso** quando todos provedores LLM falham (mensagem + log).

### Audio
24. **Whisper self-hosted** no agents_runtime (faster-whisper base CPU int8).
25. **Mensagem amigavel** no cold start: "1o audio demora um pouquinho".
26. **Max 5min audio** (timeout 120s do Cloud Run).

### WhatsApp
27. **Webhook Evolution tem retry automatico 3-5x com backoff** — zero perda de mensagens mesmo durante cold start.
28. **Min-instances=0 em whatsapp-agente** e agents_runtime — ping Cloud Scheduler 5min mantem warm.
29. **Cold start 5-15s esperado** em horario nao-comercial (0h-7h).

## Regras de Seguranca / Privacidade

1. Nenhuma chave de API, credencial ou token deve ser escrito no código em hardcode (plaintext).
2. **Masker obrigatorio** em todas as camadas: input do usuario, tool calls, output do LLM, mensagens proativas.
3. **Agent-morality**: linguagem grosseira/assedio → recusa educada + informacao sobre legislacao vigente (RAG em `agente-knowledge-{phone}`).
4. **Jennifer NAO reproduz** linguagem vulgar, ofensiva ou de baixo calao mesmo se provocada.
5. **Conteudo adulto**: proibido.
6. **Webhook Evolution**: validar `fromMe=false`, `remoteJid` nao-broadcast.

## Decisoes Resolvidas (nao mais pendentes)

| Pendencia | Resolucao |
|---|---|
| Embedding provider | **MiniMax embo-01 (1536d)** via LangChain |
| RAG collection naming | **Por phone do master**: `agente-knowledge-{phone}` |
| Whisper load strategy | **Background load** (sem cold start penalty para texto) |
| Min-instances | **0** + ping Cloud Scheduler 5min (ambos servicos) |
| RAG pre-seed | **~10 docs curados** (Codigo Penal, Lei Maria da Penha, etc.) |
| ~~whatsapp-agente min~~ (removido 2026-07-21) | ~~0 + ping (aceita cold start)~~ |
| Proatividade em grupo | **Sempre permitida** apos entrada + welcome message |
| Proatividade em grupo (formato) | **Mensagem GERAL** (sem @mention obrigatoria) |
| Frequencia proativa | **2/dia/contato, 5/dia global, cooldown 12h** |

## LGPD Checklist por Fase

- [x] Fase 0: 4 docs mandatorios criados
- [ ] Fase 1: masker.py criado e testado
- [ ] Fase 3: masker aplicado antes de LLM
- [ ] Fase 3: agent-morality com RAG respeitando LGPD
- [ ] Fase 4: Portal UI com toggle "exportar meus dados" (Art. 18)
- [ ] Fase 5: LGPD audit em cada webhook
- [ ] Fase 7: TTL 90d para historico + opt-out completo

## Referencias

- [PLAN_OMNICHANNEL_AGENTES.md](./PLAN_OMNICHANNEL_AGENTES.md) - Plano completo
- [ARQUITETURA.md](./ARQUITETURA.md) - Componentes
- [DIARIO_BORDO.md](./DIARIO_BORDO.md) - Decisoes tecnicas
- `Coherence_Portal/docs/GUARDRAILS.md` - Guardrails globais do Portal

## Guardrails Operacionais (17/07/2026)

### G1-G6: WhatsappAgente (anti-spam e resiliência)

| Guardrail | Regra | Onde | Penalidade |
|---|---|---|---|
| **G1** | Webhook NUNCA bloqueia. Responde 200 em <1s. Processamento async. | `whatsapp-agente/agente/main.py` /webhook | Timeout >1s = Evolution retry = spam |
| **G2** | Idempotência por content hash (phone+texto). Mesma msg não processada 2x em 120s. | `_is_duplicate()` + `_content_hash()` | Duplicata gera fallback em cascata |
| **G3** | Máximo 1 fallback por telefone a cada 120s. | `_can_send_fallback()` | Usuário recebe N mensagens "Demorou mais" |
| **G4** | Máximo 5 mensagens enviadas por telefone por minuto. Excedeu → bloqueia. | `_check_outbound_rate()` | Spam para o usuário |
| **G5** | Circuit breaker: 3 falhas seguidas no agents-runtime → pausa 60s. | `_circuit_breaker_allowed()` | Degradação controlada, não cascata |
| **G6** | MESSAGES_UPDATE e fromMe=true NUNCA processam webhook. Só MESSAGES_UPSERT de usuário. | `extract_message()` | Loop infinito: Jennifer responde → Evolution notifica → webhook processa → timeout → fallback → repete |

### G7: Orchestrator (eficiência)

| Guardrail | Regra | Onde | Penalidade |
|---|---|---|---|
| **G7** | Saudações NUNCA usam tool loop. Apelido é pré-resolvido do JSON estático. 1 chamada LLM. | `orchestrator.py` `_prefetch_nickname()` | 2 chamadas LLM (10-30s) vs 1 chamada (5-10s) |

### G8: Instância mínima

| Guardrail | Regra | Onde |
|---|---|---|
| **G8** | `min-instances=1`. Nunca 0. Cold-start quebra WhatsApp. | `cloudbuild-test.yaml` |

### G9: OAuth Per-User

| Guardrail | Regra | Onde |
|---|---|---|
| **G9** | Tools Google (Calendar/Drive/Gmail) sempre usam token do usuário (phone). Fallback para token global se não existir. | `tools/google_*.py` `_get_credentials(phone)` |

### Monitoramento

| Métrica | O que observar | Alerta |
|---|---|---|
| Webhook latency | `POST /webhook` duração | >1s = ALERTA |
| Duplicate webhooks | `skip: duplicate` no log | >3/min = investigar |
| Circuit breaker | `CIRCUIT BREAKER OPEN` no log | Imediato |
| Fallback rate | `Fallback throttled` no log | >1/hora = agents-runtime lento |
| Outbound rate limit | `RATE LIMIT HIT` no log | >0 = anomalia |
- Skill `lgpd_compliance` - Implementacao de LGPD