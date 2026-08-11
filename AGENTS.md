# AGENTS.md — ChatBotWhatsapp

> Guia curto pra AI agents trabalharem neste repo sem inventar hipótese errada.
> Doc canônica completa fica em `docs/ARQUITETURA.md`, `docs/HARNESS.md`,
> `docs/GUARDRAILS.md` e `docs/DIARIO_BORDO.md`. **Leia antes de sugerir mudanças.**

## TL;DR

- **Bot WhatsApp** (Evolution API → Cloud Run `agents-runtime-test` → Pub/Sub → orchestrator → Evolution).
- **Owner único** por instância: telefone master em `whatsapp_accounts/{id}.owner_phone`. **Só ele** acessa Gmail/Drive/Calendar. Outros recebem `owner_only_capability`.
- **OAuth per-user** (Fase D, 21/07/2026): token em `usuarios/{phone}.google_oauth_token` no Firestore. **Não existe mais fallback global** `GOOGLE_OAUTH_TOKEN` em produção.
- **Guard de verdade** = `access_guardian` (subagente no grafo LangGraph, Fase H 23/07/2026). O `@_owner_guard` nos `tools/google_*.py` é decoração legada — quem decide owner+OAuth+scopes é o access_guardian **antes** da tool.
- **LLM único**: DeepSeek V4 Flash via `ChatOpenAI(base_url='https://api.deepseek.com/v1')` (Fase N, 25/07/2026). Cascade removido. Gemini só STT sob consentimento.
- **DEPLOY**: push em `test` → trigger `deploy-agents-runtime-test` (2nd-gen, us-central1). **PROIBIDO `gcloud builds submit` manual** (GUARDRAILS §10).
- **CANAL**: apenas **WhatsApp via Evolution API v2.3.7**. **NÃO suportado**: LinkedIn, Telegram, Facebook, Instagram, Discord, SMS. PDF/anexo que chega por outro canal é silenciosamente ignorado (webhook não recebe).
- **F4d.2 (27/07/2026)**: fileLength do `documentMessage` na Evolution v2.3.7 chega como `dict` (proto Long do Baileys), não como `int`. O `extract_envelope` agora normaliza: `dict → low + high*2^32`, `int → int`, ausente → 0.
- **F4d.2 (27/07/2026)**: ack do F2 ("Só um instante...") usa `delay_ms = max(1500, calculate_delay_ms(ack_text))` para que o WhatsApp mostre o typing indicator ("digitando...") antes da resposta aparecer. Sem isso, a resposta brota na tela instantaneamente.
- **F4d (27/07/2026)**: handler de attachment no `orchestrator._handle_attachment` — pipeline PDF/DOCX/XLSX via Evolution v2.3.7. Anexos vão para `agent-knowledge-v2` (individual) ou `group-knowledge-v2` (grupo) quando o user pede para "memorizar"/"indexar"/"armazenar".
- **F4d.5 (28/07/2026)**: confirmação de leitura paralela ao webhook com log estruturado (`evolution_mark_read_ok` / `_timeout` / `_failed` / `_skipped`). RAG de grupo sem teto rígido: `truncated=True` quando `len(text) > RAG_GROUP_CHARS_SOFT_LIMIT` ou `len(chunks) > RAG_GROUP_CHUNKS_SOFT_LIMIT`. Padrão de chunks permanece `max_chars=1200`, `overlap_pct=15`.
- **Fase G — Knowledge Router (28/07/2026)**: sub-agente `agent-knowledge-router` em `agent_orchestration/knowledge_router.py` decide a skill por MIME e keywords, com tie-breaker via DeepSeek V4 Flash. Skills em `skills/knowledge/` (`pdf`, `docx`, `xlsx`, `text`, `drive`). Default = Firestore Vector (`agent-knowledge-v2` individual ou `group-knowledge-v2` grupo); Google Drive apenas se o user pedir explicitamente. Embeddings OpenAI `text-embedding-3-small` (1536d). Soft limits `RAG_PRIVATE_CHUNKS_SOFT_LIMIT=500` e `RAG_PRIVATE_CHARS_SOFT_LIMIT=1_000_000`.
- **Fase H — Knowledge Retriever (28/07/2026)**: sub-agente `agent-knowledge-retriever` em `agent_orchestration/knowledge_retriever.py` decide tema RAG (keywords + tie-breaker DeepSeek V4 Flash), aplica escopo (privado, grupo ou cruzado via `pending_action share_private_knowledge_in_group`), e devolve trechos acima de `RAG_RETRIEVE_MIN_SCORE` (default 0.5).
- **Fase F4d.6 — Categorizer + Isolation (28/07/2026)**: sub-agente `agent-categorizer` em `agent_orchestration/categorizer.py` classifica cada anexo em `{class, group, theme, confidence}` antes de persistir (15 classes, ~50 groups). O `agent-knowledge-retriever` agora usa `RAG_RETRIEVE_K=10` (default) e `RAG_RETRIEVE_MIN_SCORE=0.7`, extrai hints da query (filename e class) e filtra por `source_title` e `class` em `agent-knowledge-v2`. Quando nada bate, devolve `needs_clarification=True` com `clarification_prompt`. Sem alucinação: lista `source_title` antes de citar e não inventa fatos. 3 índices compostos em `firestore.indexes.json` para queries com filtro.
- **Fase F4d.7 — rag-retrieval-fix (28/07/2026)**: corrigiu o deploy parcial da Fase F4d.6 — `agent-knowledge-retriever` e tools `knowledge.retrieve` / `knowledge.categorize` agora registradas na collection Firestore, `jennifier.delegates_to` inclui o retriever, `agent-rag` legado migrado para `rag.search_legal_knowledge` (collection privada) e `_resolve_agent_for_intent` agora retorna o prefixo correto `agent-knowledge-retriever`. Scripts de diagnóstico: `scripts/diag_rag.py` (storage/agents/tools), `scripts/smoke_retrieval.py` e `scripts/smoke_retrieval_mocked.py` (logica de retrieval), `scripts/backfill_categorizer.py` (reprocessa docs antigos). Storage validado: 352 chunks com class/group/theme preenchidos.
- **Fase F4d.8 — system-prompt-aware-agent (28/07/2026)**: o `jennifier.yaml` e o `agent-knowledge-retriever.yaml` foram atualizados (versão 2) com system prompts que documentam a propria arquitetura (Firestore Vector, agent-knowledge-retriever, categorizer, class/group/theme, source_title, clarification_prompt) e adicionam personalidade ao jennifier (levemente sarcastico, ate 1 comentario por resposta, sem ironia em contextos sensiveis de saude/juridico/financas). Cloud Run 4 GB + max-instances=5. Testes: `tests/test_jennifier_system_prompt.py` valida presenca de todas as keywords obrigatorias. Script: `scripts/smoke_e2e.py` faz 4 cenarios de validacao.
- **Fix manager-prompt-hallucination (01/08/2026)**: o prompt de `manager-drive` em `deepagent_layer/agents.py` dizia "NUNCA diga 'estou sem acesso ao Drive' — voce SEMPRE tem acesso" enquanto o codigo retornava `folder_permission_required` com URL `/admin/users/.../folder-permissions`. A LLM inventava UI admin ("Admin > Usuarios > Permissoes de pasta") que nao existe. Corrigido: bloco `[ERRO DE PERMISSAO]` adicionado aos 3 prompts (calendar/email/drive) instruindo a LLM a responder com mensagem humana apontando para o Portal Coherence real, sem inventar URL interna nem caminho de menu. Removida a frase contraditoria do `manager-drive`. Testes: `tests/test_deepagent_layer.py::TestManagerPromptsAntiHallucination` valida (1) presenca dos codigos de erro reais, (2) ausencia de `/admin/` em contexto positivo, (3) ausencia da frase contraditoria legada.
- **Owner bypass em TASK B (01/08/2026)**: `core/owner_guard.py::_check_folder_permission` agora retorna `None` (allow) sem consultar Firestore quando o phone resolve para owner da instance via `resolve_owner`. TASK B lock-down continua valendo para non-owners (preparação multi-user). Dupla validação: `deny_if_not_owner` no caller `_invoke_with_guard` já confirmou owner antes. Resolve definitivamente "tools NAO podem falhar" para o owner — mesmo sem folder_permissions wildcard, sem cache invalidado, sem grant manual. Testes: `tests/test_owner_guard.py::TestOwnerBypassTASKB` (6 classes, 21 testes).
- **Composio INTEGRADO (09/08/2026)**: tools `linkedin.*`, `youtube.*`, `googledocs.*`, `notion.*`, `github.*`, `onedrive.*` em `tools/*_composio.py` via SDK Composio (não confundir com as tools Google nativas `calendar./drive./gmail.` que usam OAuth per-user). **4 camadas obrigatórias para funcionar** (qualquer uma faltando = erro genérico no WhatsApp): (1) `USER_SCOPED_TOOL_PREFIXES` inclui `youtube.`/`linkedin.`/`googledocs.`/`notion.`/`github.`/`onedrive.` → `_bind_tool_args` injeta `phone`; (2) wrappers no `tool_registry.py` repassam `phone=kwargs.get("phone","")`; (3) funções passam `user_id` ao `tools.execute()`; (4) `toolkit_versions` pinadas em `tools/_composio_common.py`. Schemas reais: YouTube usa `q`/`maxResults` (não query/max_results), GoogleDocs usa `document_id`/`file_id` (não id), LinkedIn exige `author` URN (`urn:li:person:{id}` resolvido via `_resolve_author_urn`). `COMPOSIO_API_KEY` no Secret Manager. Endpoints Connect API: `/api/v1/composio/{status,connect-all,authorize-owner}` (usa `user_ids=[phone]`, plural).
- **DECISÃO (10/08/2026)**: Gmail/Calendar/Drive/Google Maps **NÃO usam Composio** — usam OAuth direto per-user (`core.oauth_per_user` + `googleapiclient`, token em `usuarios/{phone}.google_oauth_token`) e API Key direta (Maps). Os pins `gmail`/`googlecalendar`/`googledrive`/`google_maps` foram removidos de `tools/_composio_common.py`. `googledocs` e `googlesheets` continuam via Composio.
- **`calendar.move_event` (commit `28eed0b`)**: tool dedicada que faz PATCH in-place de `start`/`end` com `sendUpdates='all'` — corrige bug "vc não moveu, vc copiou" (a LLM estava usando `create_event` por cima de um existente do usuário). **SEMPRE preferir `move_event` a `update_event` quando o pedido for "mover/reagendar/trocar horário"** — `update_event` faz GET + merge de kwargs, o que pode regredir outros campos. `move_event` altera só data/horário, preserva id, participantes, link Meet e descrição. O prompt de `manager-calendar` em `deepagent_layer/agents.py` instrui a LLM explicitamente. Tests: `tests/test_google_calendar.py` (6 testes novos em `TestMoveEvent`).
- **Memory per-user no grupo (commit `806d931`)**: o `extract_envelope` (commit 01/08/2026) extrai `phone` do `key.participant` em grupo, garantindo que o `memory.search_facts` lê os fatos do PRÓPRIO user (não do `remoteJid` do grupo). No grupo, quando o owner (Vinicius, `5511966830020`) fala, o `phone` chega como owner e os fatos DELE são encontrados normalmente (`usuarios/{5511966830020}/facts/`). Quando um membro fala, MEMBRO vê apenas os fatos do próprio member — NUNCA vazam. Tests: `tests/test_memory_group_owner.py` (6 testes — FASE 2 enviada com o usuário).

## Escopos Google (GUARDRAILS §8 — em transição)

Estado atual em produção (25/07/2026):

```
gmail.readonly + gmail.send
drive                          (full, TEMPORARIO)
calendar + calendar.events
```

- O escopo `drive` (full) é a **configuração definitiva** (adotado em
  25/07/2026, commit `8e8a672`). O `access_guardian._has_required_scope()`
  tem bypass (commit `01e8b9d`) que aceita `drive` como cobertura de
  `drive.file` **e** `drive.readonly` simultaneamente. Sem migração
  futura nem re-consentimento.
- `OAUTH_CLIENT_SECRET` armazenado sem `client_id`/`client_secret`
  no Firestore (`_persist_token` strip).

## Drive — casos de uso reais

| Operação | Tool | Quando |
|---|---|---|
| **Subir** ata de reunião | `find_omnichannel_atas_folder` → `upload_file` em `Omnichannel/Atas/` | "Salva essa ata no Drive" |
| **Listar** arquivos da pasta Omnichannel | `list_folder` | "Lista os arquivos do Drive" (já funciona desde Fase D) |
| **Ler** PDF, DOCX, XLSX, Google Docs | `search_drive_files` → `read_file_content` (commit `c4d8f7f`) | "Leia a ata", "o que tem no PDF", "resuma o documento" |

- Suportados pelo `read_file_content`: PDF, DOCX, XLSX (formatado como
  tabela ASCII com bordas para WhatsApp), texto puro, Google Docs,
  Google Sheets, Google Slides.
- Outros MIME types (vídeo, áudio, imagem) retornam
  `{"error": "unsupported_mime_type"}`.
- Limite de extração: **12.000 chars** (~8 páginas) por arquivo.
  Conteúdo maior é truncado com `truncated=True` na resposta da tool.

## Onde olhar quando algo quebra

- **Erro `user_google_oauth_required`** → HARNESS.md § "Troubleshooting OAuth per-user" tem checklist de 4 sintomas.
- **Drive retorna `scope_missing:...` mesmo com token válido** → ver `docs/DIARIO_BORDO.md` 25/07/2026 "Bug Drive scope_missing". Causa: bypass do `access_guardian` para escopo `drive` (full) precisa estar no commit `01e8b9d` ou posterior.
- **Falha ao ler arquivo do Drive** → verificar MIME type do arquivo nos logs do Cloud Run. Suportados: `application/pdf`, DOCX, XLSX, `text/*`, `application/vnd.google-apps.{document,spreadsheet,presentation}`. Outros retornam `unsupported_mime_type`.
- **Prefetch Drive/Calendar/Email retornando None** → log `Prefetch X failed: ...` no Cloud Run (`agents-runtime-test`).
- **Webhook parado** → logs `pubsub send_text_skipped` ou `pubsub reply_dropped_empty_phone` (sintoma de retry-storm histórico).
- **Tools composio (`linkedin.*`/`youtube.*`/`googledocs.*`) retornando erro genérico no WhatsApp** → validar as 4 camadas em ordem: (1) prefixo em `USER_SCOPED_TOOL_PREFIXES`; (2) wrapper em `tool_registry.py` repassa `phone`; (3) `user_id` no `tools.execute()`; (4) versão no `tools/_composio_common.py`. Erros típicos: `unregistered callers` (camada 3), `Toolkit version not specified` (camada 4), `Invalid request data ... missing {'q'}` (schema errado — conferir com `c.tools.get_raw_composio_tool_by_slug()`). Histórico completo: DIARIO_BORDO 08-09/08/2026.
- **Custo Cloud Run alto** → GUARDRAILS §10 (Guardrail 57): nunca `--no-cpu-throttling` ou `minScale > 0` em dev/test.

## Comandos rápidos

```powershell
# Rodar suite
cd agents_runtime
python -m pytest -q tests/

# Diagnóstico OAuth (ver scopes reais no Firestore)
gcloud firestore documents get usuarios/<phone> --project=coherence-ominichannel-fs --format="value(google_oauth_token.scopes)"

# Validar billing
gcloud --project=coherence-ominichannel-fs logging read "resource.type=cloud_run_revision AND resource.labels.service_name=agents-runtime-test AND httpRequest.requestUrl:'/pubsub/push'" --limit=50000 --format='value(timestamp,httpRequest.status)' --freshness=24h
```

## Pendências externas (Fase F)

1. Deletar secrets órfãos (`whatsapp-agente-url`, `agents-runtime-sa-token-clean`, `google-oauth-token`).
2. Deletar pasta local `WhatsappAgente/` e repo `viniciusbritor/WhatsappAgente`.
3. Configurar OAuth Client no Google Cloud Console (Authorized redirect URIs) — `docs/fases/fase_F/oauth_setup.md`.

## Onde **NÃO** mexer

- Repos `Monitoria_Chamadas` e seus triggers (fora de escopo).
- Triggers `EvolutionWhatsapp-*` (1st-gen, monitorar).

## Regras de blindagem (ANTI-REGRESSÃO)

- **NUNCA comentar/remover função sem `grep` em todas as chamadas.** O incidente 03/08/2026 (NameError `_build_skills_section`) quebrou Calendar/Email/Drive/Jennifer por ~17h porque a função foi comentada mas a chamada permaneceu viva.
- **ANTES de push no branch `test`**: rodar `pytest tests/pipelines/ -q` — se algum pipeline quebrar (calendar, email, doc, jennifer), o deploy é bloqueado.
- **`_execute_agent()` é ponto único de falha** — todos os agentes (calendar, email, drive, jennifer) passam por ele. Cada componente interno (skills, correções, deep agent, memory, history) tem try/except próprio. Se um falhar, os outros continuam.
- **RAG tem caminho próprio** (`retrieve()` direto, sem `_execute_agent`) — não usar como prova de que "está tudo funcionando".
