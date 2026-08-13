# Guardrails e Regras Inegociáveis — ChatBotWhatsapp

> Regras DURAS que todos os agentes IA e humanos devem obedecer neste projeto.
> Última atualização: **2026-08-13** — Obrigatoriedade estrita de deploy via Esteira CI/CD (Cloud Build) + Harness DeepSeek v4.

## Ǥ. Harness Global DeepSeek v4 (Flash e Pro) — QUEBRA SILENCIOSA

**Regra:** É **TERMINANTEMENTE PROIBIDO** passar `"thinking": {"type": "disabled"}` ou qualquer valor
no campo `thinking` dentro de `model_kwargs` ao usar `langchain_openai.ChatOpenAI` com DeepSeek v4
(Flash ou Pro).

**Motivo:** A API do DeepSeek v4 rejeita com `HTTP 400: unexpected keyword argument 'thinking'`.
O erro é silencioso quando capturado por try/except — o código cai em fallback sem alertar.

**Evidência:** Log de produção em 07/08/2026:
```
full_document synthesis failed: Completions.create() got an unexpected keyword argument 'thinking'
```

**Correto:**
```python
ChatOpenAI(
    model="deepseek-v4-flash",
    model_kwargs={"extra_body": {"cache_mode": "default"}},  # apenas extra_body
)
```

**Errado (BANIDO):**
```python
ChatOpenAI(
    model="deepseek-v4-flash",
    model_kwargs={"thinking": {"type": "disabled"}, "extra_body": {"cache_mode": "default"}},  # NUNCA
)
```

**Nota:** O `core/llm_provider.py:chat()` já NÃO envia `thinking` (comentário na linha 69 documenta o motivo).
Esta regra aplica-se a todos os outros call-sites que usam `langchain_openai.ChatOpenAI` diretamente.

## 0. Harness de CI/CD (Regra Zero — violar = bloqueio)

### §0.0 — Gate de Qualidade por Fase

```powershell
# Antes de QUALQUER commit em branch:
cd agents_runtime
python -m pytest -q tests/ `
  --ignore=tests/test_audio_transcribe.py `
  --ignore=tests/test_google_*.py `
  --ignore=tests/test_oauth_per_user.py `
  --ignore=tests/test_llm_provider.py `
  --ignore=tests/test_pubsub.py `
  --ignore=tests/test_webhook*.py `
  --ignore=tests/test_evolution_webhook.py `
  --ignore=tests/load/ `
  --ignore=tests/integration/ `
  -rs

# DEVE retornar: 0 failed, 0 errors
# Warnings permitidos apenas: Firestore positional, Google auth, extra_body cache
# NUNCA passar de fase com falhas ou warnings novos
```

### §0.1 — Workflow de Branch

```
git checkout test
git checkout -b feat/<nome>
# implementar fase → pytest tests/ completo → 0 fails
git add <arquivos>
git commit -m "tipo(escopo): descricao"
# repetir até todas fases prontas
git checkout test
git merge feat/<nome> --no-edit
git push origin test
git branch -d feat/<nome>
```

**NUNCA:** merge sem suite completa passando. Push com testes quebrados localmente. Continuar build após failures no Cloud Build.

### §0.2 — DeepSeek Cache (obrigatório)

Todo `ChatOpenAI(...)` DEVE incluir:
```python
model_kwargs={"extra_body": {"cache_mode": "default"}}
```
Se já tem `model_kwargs`, merge: `{**existing, "extra_body": {"cache_mode": "default"}}`.

---

## 0.5. Arquitetura de Coleções (Vector + Plain)

### §0.5.0 — Schema Final

| # | Collection | Tipo | Escopo | Isolamento |
|---|---|---|---|---|
| 1 | `knowledge-database` | Vector (1536d) | User + grupo | `scope` + hash |
| 2 | `message-history` | Plain | Chat history | `owner_hash` |

### §0.5.1 — Schema do knowledge-database

Todo documento DEVE ter:
- `scope`: `"private"` ou `"group"`
- `owner_hash` (private) ou `group_hash` (group)
- `text_content`, `vector_embedding`, `source_title`, `section_title`
- `document_title` — título real extraído na ingestão (via `_extract_document_title`)
- `hierarchy` — `_extract_legal_hierarchy()` para textos jurídicos
- `class`, `group`, `theme`, `chunk_index`, `chunk_type`

**NUNCA:** criar nova collection vector sem aprovação explícita. Armazenar chat history com embedding (custo proibitivo). Duplicar texto em `-plain` ou `-sections`.

### §0.5.2 — Collections PROIBIDAS (deletadas)

- `agent-knowledge-v2`, `agent-knowledge-v2-plain`, `agent-knowledge-sections`
- `group-knowledge-v2`, `public-knowledge-v2`, `collective-knowledge-v2`
- `conversation-memory-v2`, `contatos/*/historico`, `ata_runs`

---

## 0.6. Arquitetura de Agentes

### §0.6.0 — Classificador LLM (obrigatório)

Toda query passa por `_classify_intent_llm()` ANTES de qualquer pipeline:
- Modelo: DeepSeek Flash, temperature=0, max_tokens=5
- Cache via `message_id` (já existe em `orchestrate()`)
- Retorna: `juridicas | editais | academica | anotacoes | ferramentas | conversa`

**NUNCA:** usar keyword detection como rota primária. Keyword = apenas sub-detect para `ferramentas`.

### §0.6.1 — Agentes Especialistas (Firestore)

| Agent ID | Domínio | Tools | System Prompt |
|---|---|---|---|
| `juridicas-agent` | Leis, códigos, normas | `knowledge.retrieve`, `chat_history.search` | Editável via Portal |
| `editais-agent` | Licitações, concursos | `knowledge.retrieve`, `chat_history.search` | Editável via Portal |
| `academica-agent` | Teses, papers | `knowledge.retrieve`, `chat_history.search` | Editável via Portal |
| `anotacoes-agent` | Notas, lembretes | `knowledge.retrieve`, `chat_history.search` | Editável via Portal |

**NUNCA:** hardcodar system prompt de agente em código. Agentes DEVEM ser editáveis via Portal (`/admin/dashboard` → aba Agentes).

### §0.6.2 — Agentes Desabilitados

- `agent-rag` → substituído pelos 4 especialistas
- `agent-knowledge-retriever` → redundante

---

## 0.7. Retrieval (RAG)

### §0.7.0 — Regras de Retrieval

1. `min_score` default = 0.4 (ajustável via env `RAG_RETRIEVE_MIN_SCORE`)
2. `ADAPTIVE_FLOOR` = 0.3 (ajustável via env `RAG_ADAPTIVE_FLOOR`)
3. Chunking: `min_chars=50`, `max_chars=2000`, overlap via `_chunk_text_semantic`
4. Full document fallback: ativa quando ≤2 docs na base E retrieval vazio
5. `_retrieve_full_document()` lê de `knowledge-database` (NÃO de `-plain`)

### §0.7.1 — Guardrails de Ingestão

1. `_extract_document_title()` OBRIGATÓRIO em toda ingestão
2. Hierarquia jurídica (`_extract_legal_hierarchy()`) armazenada como `hierarchy` no chunk
3. `source_title` nunca vazio — fallback para filename sem extensão
4. Texto de imagem NUNCA armazenado como bytes (extrair texto, descartar imagem)
5. Formatos suportados: PDF, DOCX, XLSX, TXT, IMG (texto extraído)

## 1. Segurança

- **Nenhuma chave de API** hardcoded em código, scripts, documentação ou
  contexto Docker. Use `core.secrets.get_secret()` ou env var injetada via
  Secret Manager.
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
  que o guard já autorizou. Em **grupo**, capabilities pessoais do owner
  (`is_drive`/`is_email`/`is_calendar`) só executam para membro confirmado
  (`grupos/{jid}/membros/{phone}.confirmed=true`); caso contrário, o
  orchestrator cria `pending_action group_consent` (TTL 300 s) antes de
  bloquear a execução.
- **Origem do `phone` em grupo**: a Evolution API v2.3.7 envia o
  phone do user individual em `data.key.participant` em conversa
  de grupo. O `core/evolution_webhook.py::extract_envelope()`
  extrai esse campo quando `remoteJid` tem `@g.us` (patch 01/08/2026,
  `fix(webhook)`). Fallback para `remoteJid.split('@')[0]` quando
  `participant` ausente. Em conversa privada, phone vem
  diretamente de `remoteJid`. Anotado em `envelope.extra.phone_source`
  para debug (`"participant"` ou `"remote_jid"`).

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
- Anexo de grupo memorizado usa `group-knowledge-v2` com `group_hash`;
  leitura exige `phone` ser membro ativo (`grupos/{jid}/membros/{phone}.is_active=true`).
- `search_conversation_memory()` lê **plain** Firestore filtrando

  `where("owner_hash", ==, _owner_hash(phone))` e ordena por
  `created_at` desc. Resultado devolve `[]` quando `phone` é vazio.
- A coleção vetorial legada `conversation-memory-v2` não é mais
  alimentada em produção; pode ser removida após confirmação das novas
  gravações.
- `agent-knowledge-v2` (escopo privado) e `group-knowledge-v2` (escopo
  de grupo) são coleções **separadas** com regras de filtro
  distintas:
  - `agent-knowledge-v2`: `where owner_hash == owner_id(inbound)`.
  - `group-knowledge-v2`: `where group_hash == sha256(group_jid)[:32]`
    e exige `phone` constar em `grupos/{jid}/membros/{phone}.is_active=true`.
  - Cruzar source privada → grupo exige `pending_action
    share_private_knowledge_in_group` (TTL 300 s,
    `PENDING_ACTION_TTL_SEC`).
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
- **Adaptive floor (Fase 31/07 v2)**: embeddings OpenAI 1536d em
  chunks de 3KB costumam dar cosine similarity 0.4-0.65 (abaixo
  do `min_score=0.7`). O `search_legal_knowledge` agora aplica
  um `ADAPTIVE_FLOOR=0.3`: matches entre 0.3 e o `min_score` sao
  entregues com warning estruturado (`retrieval_low_confidence`).
  Abaixo de 0.3 ainda sao descartados. Justificativa: o golden
  set sintetico (CDC/LGPD/Higiene) tem densidade semantica baixa,
  e o threshold alto estava truncando queries legitimas para 0
  hits. Log `retrieval_zero_hits` captura top-3 candidates quando
  TUDO falha (< floor).
- **UX da `clarification_prompt` (Fase 31/07 v2)**: quando o retrieval
  retorna 0 hits, a mensagem agora lista os `source_title`
  conhecidos do owner (`Voce tem esses documentos salvos: ...`).
  Implementado em
  `agent_orchestration/knowledge_retriever.py::_list_known_sources` +
  `_build_clarification_prompt`. Helper de diagnostico:
  `scripts/diag_rag_query.py` (rode com `min_score=0.0` para
  inspecionar todos os candidates e seus scores).
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

- Escopos ativos (29/07/2026) em `agents_runtime/main.py:1465-1471`:
  ```
  gmail.readonly + gmail.send
  drive                          (FULL — definitivo desde 25/07/2026)
  calendar + calendar.events
  ```
- O escopo `drive` (full) é a configuração definitiva: o
  `access_guardian._has_required_scope()` aceita `drive` como cobertura
  de `drive.file` **E** `drive.readonly` simultaneamente (bypass vigente,
  commit `01e8b9d`). Sem migração futura.
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

## 8.1. Regra de Acesso a Conhecimento (Unificada) — 31/07/2026

**Canônico:** [`ARQUITETURA.md §0.0.4`](./ARQUITETURA.md#004-regra-unificada-de-acesso-a-conhecimento-31072026).

A cada turno o `orchestrator._detect_intent()` aplica **uma única
classificação** por keywords. O `_resolve_agents_for_intents` resolve
o agente. O `access_guardian` valida owner + OAuth + scopes para
capacidades Google. Em grupo, há regras de consent adicional.

### Switch por turno (excludente)

1. **RAG (base de conhecimento)** — se a mensagem contém keyword
   RAG (`base de conhecimento`, `memorizou`, `quais documentos`,
   `esse documento`, `knowledge base`, `qual arquivo`, `vc guardou`,
   `o que você salvou`, `lembra disso`, etc.), o caminho é
   `agent-knowledge-retriever`. Storage:
   - privado → `agent-knowledge-v2` filtrado por `owner_hash`.
   - grupo (membro) → `group-knowledge-v2` filtrado por `group_hash`.
   - privado com hit em grupo → `pending_action
     share_private_knowledge_in_group` (TTL 300 s) antes de compartilhar.
2. **Drive** — se a mensagem contém keyword estritamente de storage
   (`drive`, `gdrive`, `onedrive`, `dropbox`, `salvar no drive`,
   `manda pra mim`, `guarda no drive`, `lista os arquivos do drive`,
   `dentro desse drive`, `nesse drive`, etc.), o caminho é
   `manager-drive` + `access_guardian`. Storage:
   - privado (1:1) → Drive do owner (subject a scope `drive.read` ou
     `drive.write`).
   - grupo (membro confirmado) → Drive do owner ou pasta do grupo
     (`grupos/{jid}.drive_folder_id`).
   - grupo (membro não confirmado) → `pending_action group_consent`
     (TTL 300 s) antes de bloquear.
3. **Chat memory** — qualquer outra mensagem. Vai direto para
   `jennifier` (LLM). O histórico fica em `message-history/{id}`
   (Firestore **plain**, sem embedding) com `owner_hash` derivado.

### Keyword patch (31/07/2026)

`orchestrator.DRIVE_KEYWORDS` foi estreitado para conter apenas
nomes de serviço de storage e expressões que **explicitam** o
destino Drive. Isso evita conflito com o `agent-knowledge-retriever`:
queries como "quais documentos você tem na sua base de
conhecimento?" agora acertam `is_rag=True` em vez de cair
erroneamente em `manager-drive`.

Tokens genéricos (`documento`, `pdf`, `docx`, `xlsx`, `ata`,
`arquivo`, `pasta`, `planilha`, `relatorio`, `minuta`, `upload`)
foram movidos para `DRIVE_KEYWORDS_REMOVED` (não usados) e continuam
cobertos por `attachment_save_kw` / `attachment_file_kw` quando há
anexo em processamento.

### Auditoria de violação

- `python -m pytest -q tests/test_orchestrator.py
  tests/test_agent_orchestration.py tests/test_rag_routing_pt8.py`
  garante que a unidade de classificação (`_detect_intent` /
  `classify_intent_node`) preserva a regra.
- `scripts/smoke_access_rule.py` (manual, Cloud Run test) exercita
  os 4 cenários ponta-a-ponta contra o `agents-runtime-test`
  implantado.

## 8.2. Visibilidade de anexo em grupo — 01/08/2026

Quando o `manager-group-rag` indexa um anexo (PDF/DOCX/XLSX) recebido
dentro de um grupo, a `visibility` é **automática**:

| Cenário | visibility | Quem tem acesso |
|---|---|---|
| Anexo em grupo, sem comando explícito de publicar | **`group`** (default) | Só membros do grupo (`grupos/{jid}/membros/{phone}.is_active=true`) |
| Anexo em grupo, user pede explicitamente `"deixe publico"` / `"compartilhe com qualquer pessoa"` / `"publique isso"` / `"para todos os usuários"` / `"fora do grupo"` | **`public`** | Qualquer pessoa com acesso ao Firestore do projeto (cross-user leak aceito) |
| Anexo em privado, user pede para salvar | **`private`** (equivale a `agent-knowledge-v2` sem `visibility`) | Só o próprio user |

**Justificativa:** quando o user anexa algo em grupo, o contexto
já é o grupo. Perguntar "membros ou público?" a cada anexo quebra
o fluxo da conversa. O **fail-safe é privacidade**: ambiguidade
mantém `group`.

**Cross-group leakage:** impossível. `tools.group._group_hash(group_jid)`
filtra por grupo específico. Mesmo user em grupos A e B vê docs apenas
do grupo onde perguntou.

**Não confundir com** `confirmed` (campo separado em
`grupos/{jid}/membros/{phone}.confirmed`). Esse campo é gate
explícito para capacidades pessoais do owner (Drive/Gmail/Calendar)
em grupo. Não afeta RAG.



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

### §10.1 — Escape de `$` em scripts bash no cloudbuild YAML (ANTI-QUEBRA DA ESTEIRA)

**Regra**: Em Cloud Build **2ª geração**, todo `$` dentro de scripts bash
em `cloudbuild*.yaml` que NÃO for uma substituição do Cloud Build
(`$PROJECT_ID`, `$BUILD_ID`, `$SHORT_SHA`, `$_DEPLOYED_AT`, `$COMMIT_SHA`,
`$REF_NAME`, `$REPO_NAME`, `$REVISION_ID`, `$TRIGGER_NAME`) DEVE ser escapado
com `$$`.

**Causa do incidente 05/08/2026**: Bash script inline em step `smoke-test`
usava `$(curl ...)`, `$STATUS`, `${http_code}` sem escape. O Cloud Build
2nd-gen tentou resolver essas expressões como substituições de build
durante o parse do YAML (ANTES do fetch do source code). Como `seq`,
`curl`, `http_code` não são substituições válidas, o parse falhou
silenciosamente. Resultado: 5 builds FAILURE consecutivos sem
`SHORT_SHA` nem `TRIGGER_NAME` — builds-fantasma que quebram
rastreabilidade e bloqueiam deploy.

**Exemplo CORRETO**:
```yaml
- name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
  entrypoint: "bash"
  args:
    - "-c"
    - |
      echo "Deploying $$SHORT_SHA to $$URL"
      STATUS=$$(curl -s -w '%{http_code}' "$$URL")
```

**Exemplo INCORRETO**:
```yaml
- name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
  entrypoint: "bash"
  args:
    - "-c"
    - |
      STATUS=$(curl -s "$URL")     # QUEBRA A ESTEIRA!
```

**Validação automática**: O script `scripts/check_cloudbuild_dollar.py`
valida TODOS os `cloudbuild*.yaml` do projeto e bloqueia o deploy se
encontrar `$(` não escapado. Executado no primeiro step do
`cloudbuild-test.yaml`.

### §10.2 — Scripts complexos em arquivo `.sh` separado

Para scripts bash com mais de 3 linhas, extraia para `scripts/build/*.sh`
e chame via `bash scripts/build/meu_script.sh`. Isso evita o problema de
escape de `$` e melhora a legibilidade.
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
> Itens resolvidos (Fase F, 21/07 → 30/07/2026): backfill de embeddings
> legacy e remoção completa do proxy `WhatsappAgente` + serviço legado.
> Permanecem em STATE.md como histórico até serem explicitamente fechados.