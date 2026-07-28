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

## Escopos Google (GUARDRAILS §8 — em transição)

Estado atual em produção (25/07/2026):

```
gmail.readonly + gmail.send
drive                          (full, TEMPORARIO)
calendar + calendar.events
```

Estado alvo (migração pendente):

```
gmail.readonly + gmail.send
drive.file + drive.readonly
calendar + calendar.events
```

- O escopo `drive` (full) foi adotado em 25/07/2026 (commit `8e8a672`).
  O `access_guardian._has_required_scope()` tem bypass em commit
  `01e8b9d` que aceita `drive` como cobertura de `drive.file` **e**
  `drive.readonly` simultaneamente.
- Migração de volta para `drive.file + drive.readonly` exige
  **re-consentimento** de todos os usuários ativos (afinal, o escopo do
  token persistido vem do consentimento original; o `refresh_token`
  não amplia escopos).
- **GUARDRAILS §8** ainda diz `drive.file + drive.readonly` — está
  desatualizado em relação ao `main.py:1068`. Atualizar antes da
  migração.
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
- Cloud Scheduler pausado (reativação é decisão do operador).
