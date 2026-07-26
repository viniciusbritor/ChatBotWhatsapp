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
