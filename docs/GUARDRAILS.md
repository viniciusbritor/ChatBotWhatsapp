# Guardrails e Regras Inegociáveis — ChatBotWhatsapp

> Regras DURAS que todos os agentes IA e humanos devem obedecer neste projeto.
> Última atualização: **2026-07-25**.

## 1. Segurança

- **Nenhuma chave de API** hardcoded em código, scripts, documentação ou
  contexto Docker. Use `core.secrets.get_secret()` ou env var injetada via
  Secret Manager. As credenciais expostas no commit `ad6399a` foram removidas e
  precisam ser rotacionadas antes do próximo deploy.
- **Upload de secrets**: APENAS `gcloud secrets versions add`. Nunca `versions
  update` (bug 12/07/2026 corrompeu chave DeepSeek).
- **Gemini API é usada exclusivamente para transcrição de áudio**
  (STT fallback quando Whisper falha tecnicamente **e** há consentimento
  registrado). Gemini não é mais usado como fallback LLM — cascade removido
  em 25/07/2026, apenas DeepSeek V4 Flash é o provedor de LLM.
- **DeepSeek V4 Flash é o ÚNICO LLM em todo o sistema.** Padrão irrestrito
  em 25/07/2026 (Fase N). Qualquer chamada LLM DEVE usar
  `ChatOpenAI(model='deepseek-v4-flash', base_url='https://api.deepseek.com/v1')`
  via `langchain_adapter.build_default_chat_model()`. Proibido:
  `model='openai:deepseek-...'`, `model='deepseek-v4-pro'`, `model='gemini-...'`
  em produção. LangChain `openai:` prefix roteia para `api.openai.com` —
  causa HTTP 400 silencioso. Use sempre o adapter com `base_url` explícito.
- **Timezone único: BRT (`America/Sao_Paulo`, UTC-3).** Toda referência a
  datetime DEVE usar `from core.timezone import BRT, now_brt, to_brt`.
  Proibido `datetime.now(timezone(timedelta(hours=-3)))` ou
  `BRT = timezone(timedelta(hours=-3))` espalhado pelo código.
  Audit-periodico: `grep -rn "timedelta(hours=-3)" agents_runtime/` deve
  retornar 0 matches fora de `core/timezone.py`.
- **`agents_runtime` não expõe Swagger público** (`/docs`, `/redoc`,
  `/openapi.json` proibidos).
- **`/admin/*`, `/chat`, `/proactive/send` exigem Bearer SA token ou Firebase
  ID token**. `/admin/dashboard` aceita Authorization header.
- **Tokens não trafegam em query string**. O `?token=` antigo foi removido do
  UI e do middleware.
- **Webhook aceita apenas payload Evolution válido**; filtros aplicam
  Evolution event, broadcast, fromMe e MIME.
- **Controle de acesso Gmail/Drive/Calendar é responsabilidade do agente
  `access_guardian`** (Fase H, 23/07/2026). O guardião roda dentro do grafo
  LangGraph (`agent_orchestration.graph`) antes de cada tool call. O guard
  determinístico `core.owner_guard` foi **descontinuado** — toda checagem de
  owner + OAuth + scopes agora flui pelo agente. Tools Google podem confiar
  que o guard já autorizou.

## 2. Privacidade (LGPD)

- **LGPD masker** (`core.masker.mask_pii`) é obrigatório antes de enviar
  texto para qualquer LLM externo.
- PII mascarado: CPF, RG, telefone, email, cartão, CNPJ.
- **TTL de 90 dias** para `conversation-memory-v2` e históricos de
  `contatos/{phone}`.
- **Audit log** em `audit/` (truncado SHA-256) com retenção de 5 anos.
- **Opt-in duplo** para proatividade; sem menção a dados sensíveis em
  mensagens proativas.
- **RAG só indexa legislação/código** com mascaramento aplicado.
- **Documentos vetoriais** devem conter `embedding_model`, `embedding_dim`,
  `schema_version`, `created_at` e `expires_at`.
- **Exclusão de conta** remove `usuarios`, `contatos`, `apelidos_custom`,
  `pending-actions`, vetores privados e audit trail conforme
  `core/lgpd.py`.

## 3. Proatividade

- Máx. 2 mensagens proativas/dia por contato.
- Máx. 5 mensagens proativas/dia globalmente.
- Cooldown de 12 h entre mensagens proativas para o mesmo contato.
- Quiet hours 21h–9h BRT — zero proatividade.
- Relevance mínima 0,75.
- Auto-pausa 7 dias se o usuário não responder 3 proativas seguidas.
- Máx. 5 proativas/semana por contato.

## 4. Pub/Sub (regra nova pós-44k)

- Um único tópico (`chatbotwhatsapp-messages`) + uma assinatura
  (`agents-runtime-consumer`) + DLQ nativa (`chatbotwhatsapp-dlq`).
- Idempotência obrigatória via ledger `message-processing` no Firestore.
- Handler deve retornar:
  - **200** para mensagem já processada, falha permanente ou sucesso.
  - **503** somente em falha transitória (timeout, OOM, infra).
- Publicação manual na DLQ foi removida.
- Mensagens com `message_id` vazio recebem ID determinístico baseado em
  `(instance, remote_jid, publish_time)` antes de qualquer publicação.
- ACK deadline configurado em 60 s para tolerar Whisper + LLM.

## 5. WhatsApp

- Tick azul (`markMessagesAsRead`) é chamado automaticamente para todo webhook
  válido. Falha no tick vira métrica mas nunca bloqueia o webhook.
- Tick não bloqueia nem repete o webhook: timeout máximo 15 s via
  `asyncio.wait_for`, sem retry. Logs estruturados:
  - `evolution_mark_read_ok` (info) — sucesso HTTP < 400.
  - `evolution_mark_read_timeout` (warning) — `asyncio.TimeoutError`.
  - `evolution_mark_read_failed` (warning) — qualquer outra falha, com `reason`
    (`exception`, `cancelled`) e `error_type`.
  - `evolution_mark_read_skipped` (warning) — falta de `remote_jid` ou `message_id`.
- Remetente precisa coincidir com `owner_phone` da instância Evolution para
  acessar Gmail, Drive ou Calendar. Ver `access_guardian` no grafo LangGraph
  (§ 0.0.1 do ARQUITETURA.md).
- Toda resposta do LLM que cite "Vou puxar", "Deixa eu verificar", "aguarde"
  etc. **sem retorno ativo** é considerado bug e deve gerar issue. O guard
  do grafo LangGraph bloqueia esses placeholders antes do envio.

## 6. Áudio

- Whisper local é o caminho padrão; download valida host, MIME, tamanho
  (25 MB), duração (5 min) e ausência de redirecionamento.
- Fallback Gemini 2.5 Flash só dispara quando Whisper falha tecnicamente **e**
  `STT_FALLBACK_CONSENT=true` ou `extra.audio_consent_external=true`.
- Limite diário do fallback: 20 chamadas (`STT_FALLBACK_DAILY_LIMIT`).
- Áudio bruto nunca é persistido; temporários são apagados em `finally`.
- Transcrição é mascarada antes de qualquer embedding ou LLM.

## 7. Firestore Vector vs Firestore plain

23/07/2026: o Firestore Vector é restrito a documentos, incluindo anexos
explicitamente memorizados pelo usuário. Toda interação do chat é persistida
em Firestore plain (`message-history/{history_id}`) com indexação por
`owner_hash = sha256(phone_digits)[:32]`.

- `index_conversation_message()` — hot path: grava em `message-history` plain
  e nunca em vector. Falhas de Firestore são logadas e o retorno segue 200 (a
  interação não trava).
- `scripts/ingest_owner_knowledge.py` e `scripts/ingest_collective_memory.py`,
  além do handler explícito de anexos, aplicam embedding + Firestore Vector.
- Anexo individual memorizado usa `agent-knowledge-v2` e filtro por `owner_hash`.
- Anexo de grupo memorizado usa `collective-knowledge-v2` com `group_hash`; não
  usa o `owner_hash` como escopo de leitura.
- `search_conversation_memory()` lê **plain** Firestore filtrando

  `where("owner_hash", ==, _owner_hash(phone))` e ordena por
  `created_at` desc. Resultado devolve `[]` quando `phone` é vazio.
- A coleção vetorial legada `conversation-memory-v2` não é mais
  alimentada em produção; pode ser removida após confirmação das novas
  gravações.
- `index_group_document` não usa teto rígido para chunks ou para o
  tamanho do texto. Acima dos tetos saudáveis (`RAG_GROUP_CHUNKS_SOFT_LIMIT=500`,
  `RAG_GROUP_CHARS_SOFT_LIMIT=1_000_000`), o retorno inclui `truncated=True`
  e `truncated_reason`, mas a indexação prossegue. Logs
  `index_group_document_chars_soft_limit` e
  `index_group_document_chunks_soft_limit` são registrados em warning.
- Anexos individuais memorizados continuam com limite nominal LGPD
  (TTL em `RAG_RETENTION_DAYS`).
- **Knowledge Router (Fase G)**: o anexo é roteado pelo
  `agent-knowledge-router` para a skill apropriada por MIME.
  Embeddings OpenAI `text-embedding-3-small` (1536d). Storage
  default = Firestore Vector (`agent-knowledge-v2` ou
  `group-knowledge-v2`). Google Drive apenas se o user pedir
  explicitamente (`manda pra mim`, `salvar no drive`,
  `guardar no gdrive`, etc.).
- **Knowledge Retriever (Fase H)**: quando a pergunta do user
  refere-se a conteudo previamente armazenado, o
  `agent-knowledge-retriever` decide o escopo:
  - privado -> `agent-knowledge-v2` filtrado por `owner_hash`.
  - grupo -> `group-knowledge-v2` filtrado por `group_hash`.
    Acesso negado se o user nao for membro.
  - cruzado privado->grupo -> cria
    `pending_action share_private_knowledge_in_group` (TTL 300 s)
    antes de compartilhar.
  - Score minimo: `RAG_RETRIEVE_MIN_SCORE` (default 0.7 na Fase F4d.6).
- Auditoria de retrieval nao e obrigatoria nesta fase.
- **Categorizer (Fase F4d.6)**: o `agent-categorizer` (DeepSeek V4 Flash)
  classifica cada anexo em `class/group/theme` antes da persistencia.
  Sistema de 15 classes com ~50 groups. Em caso de falha, fallback
  para `outros/outros`. Heuristica local disponivel para cenarios sem
  LLM.
- **Retrieval isolado (Fase F4d.6)**: o `agent-knowledge-retriever` usa
  `RAG_RETRIEVE_K=10` e `RAG_RETRIEVE_MIN_SCORE=0.7`. Filtra por
  `source_title` e `class` quando a query ou o historico sugerem.
  Quando nada bate, devolve `needs_clarification=True` em vez de
  alucinar.
- **Composite indexes (Fase F4d.6)**: 3 indices em `firestore.indexes.json`
  (raiz do repo) deployados pelo Cloud Build. Nenhum dos 3 filtra
  cross-collection: apenas `agent-knowledge-v2`.
- **System prompt do jennifier (Fase F4d.8)**: o prompt documenta
  a propria arquitetura (Firestore Vector, agent-knowledge-retriever,
  categorizer, class/group/theme, source_title) e adiciona
  personalidade. Regras:
  - Maximo 1 comentario ironico por resposta.
  - Nunca ironizar o proprio servico ou o usuario.
  - Em contextos sensiveis (saude, juridico, financas), seja
    direto e educado, sem ironia.
  - Cite o source_title antes de qualquer trecho da base.
  - NUNCA invente informacoes fora dos chunks retornados.
  - Em duvida, peca mais contexto via clarification_prompt.
- **Soft limits para RAG individual** (`RAG_PRIVATE_CHUNKS_SOFT_LIMIT`,
  `RAG_PRIVATE_CHARS_SOFT_LIMIT`): espelham o grupo. Documentos acima
  do teto retornam `truncated=True` em vez de abortar.

## 8. Integração com a Evolution API (23/07/2026)

- **Endpoints** — esta versão da Evolution aceita:
  - `POST /message/sendText/{instance}` (envio de mensagens) → 201.
  - `GET /instance/connectionState/{instance}` (verificação de status).
  - `POST /chat/markMessageAsRead/{instance}` (v1, **singular**) com
    payload v2 `readMessages: [{id, fromMe, remoteJid}]` → 200.
  - **Não suporta** `POST /chat/markMessagesAsRead/{instance}` (plural)
    — retorna 404 "Cannot POST". Não usar.
- **Instance name é case-sensitive**. O nome cadastrado na Evolution
  deve ser preservado em todas as chamadas. `core/evolution_client.py`
  resolve dinamicamente via `GET /instance/fetchInstances` antes de
  chamar os endpoints; o container **não** pode assumir um casing
  hardcoded.
- **Token `EVOLUTION_API_KEY`**: configurado no Secret Manager
  (`evolution-api-key`) e injetado via `--set-secrets` na revisão.
  A `cloudbuild-test.yaml` referencia `EVOLUTION_API_KEY=evolution-api-key:latest`.
- **Variável de env `INSTANCE`**: deve ser exportada com o nome
  exato cadastrado (ex.: `INSTANCE=Jennifer`). O `_resolve_instance_name`
  funciona como fallback dinâmico.
- **Auditoria**: `core.evolution_client` emite `logger.debug` com
  `base_url`, `token_prefix` (4 primeiros caracteres) e `token_len` em
  cada request — sem expor o token completo.

## 7. Embeddings

- OpenAI `text-embedding-3-small` (1536d) é o único provedor aceito em v2.
- Nenhuma coleção vetorial aceita mistura de modelos/dimensões — toda
  inserção deve carregar `embedding_model`/`embedding_dim`.
- Coleções filtram `owner_hash == owner_id` em toda leitura.
- Base pública (`public-knowledge-v2`) **nunca** recebe `owner_hash`.

## 8. OAuth Google

- Escopos ativos (29/07/2026) em `agents_runtime/main.py:1112-1118`:
  ```
  gmail.readonly + gmail.send
  drive                          (FULL — TEMPORÁRIO desde 25/07/2026)
  calendar + calendar.events
  ```
- Estado alvo: voltar para `gmail.readonly + gmail.send` + `drive.file + drive.readonly` +
  `calendar + calendar.events`. Migração exige re-consentimento de todos os usuários
  ativos (o `refresh_token` não amplia escopos — apenas o consentimento original).
- Bypass vigente (commit `01e8b9d`): `access_guardian._has_required_scope()` aceita `drive`
  como cobertura de `drive.file` **E** `drive.readonly` simultaneamente.
- Tokens persistidos **sem** `client_secret` e **sem** `client_id`.
- Apenas o telefone do proprietário da instância pode chamar Gmail/Drive.
- Revogação disponível via `POST /oauth/google` (re-login) ou remoção
  manual no Firestore `usuarios/{phone}`.

## 9. Código e operação

- Sem `$` solto em código, mensagens ou documentação (conflito LaTeX).
- Sem comentários no código.
- 5 tentativas por erro específico antes de parar e reportar.
- Documentação canônica: somente `docs/` na raiz. `agents_runtime/docs/` é
  histórico e será removido.
- Hot-reload de `agents/skills/tools` em ≤ 2 min sem rebuild (polling
  120 s).
- `embedding_model` no documento identifica época; mudança exige
  re-indexação completa.
- `response_identity` externa é sempre Jennifer; IDs internos ficam apenas
  na metadata protegida.
- `pending_action` é obrigatório para confirmar consentimento.

## 10. CI/CD e qualidade

- `scripts/check_lgpd_compliance.py` roda em todo `cloudbuild-*.yaml`.
- `ruff` + `mypy` + `pytest -q` obrigatórios antes do merge.
- Integração Pub/Sub real (`RUN_PUBSUB_E2E=1`) roda no Cloud Build da branch
  `test`.
- Carga Locust fica em `tests/load/` e só roda com `RUN_LOAD_TEST=1`.
- **PROIBIDO executar `gcloud builds submit` manualmente.** Todo deploy deve
  passar exclusivamente pelo trigger CI/CD (`deploy-agents-runtime-test` na
  branch `test`, 2nd-gen, região `us-central1`). O fluxo correto é:
  `git commit` → `git push origin test` → trigger dispara build → Cloud Run
  deploy. Builds manuais fora da esteira quebram rastreabilidade, reprodutibilidade
  e auditoria. Violação registrada em 25/07/2026 (builds `97a5128d` e `ef2640bb`).
- **DeepAgents é o harness de produção para managers** (Fase L, 25/07/2026).
  O tool calling loop manual em `core/llm_provider.py::chat_with_tools` é
  fallback legacy. Tool executors SEMPRE usam `asyncio.wait_for(..., timeout=30s)`
  para evitar congelamento. Tool results devem ser truncados a 2000 chars.

## 11. Pendências

> Pendências ativas e histórico de execução ficam em [`STATE.md`](../STATE.md) na
> raiz do repo (single source of truth). Este arquivo documenta apenas
> regras técnicas inegociáveis; itens que requerem ação do operador estão
> consolidados em STATE.md para evitar drift entre docs.
>
> Itens resolvidos (Fase F, 21/07 → 30/07/2026): rotação de credenciais do
> commit `ad6399a`, backfill de embeddings legacy, e remoção completa do
> proxy `WhatsappAgente` + serviço legado. Permanecem em STATE.md como
> histórico até serem explicitamente fechados.