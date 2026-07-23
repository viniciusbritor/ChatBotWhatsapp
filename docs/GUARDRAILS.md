# Guardrails e Regras Inegociáveis — ChatBotWhatsapp

> Regras DURAS que todos os agentes IA e humanos devem obedecer neste projeto.
> Última atualização: **2026-07-22**.

## 1. Segurança

- **Nenhuma chave de API** hardcoded em código, scripts, documentação ou
  contexto Docker. Use `core.secrets.get_secret()` ou env var injetada via
  Secret Manager. As credenciais expostas no commit `ad6399a` foram removidas e
  precisam ser rotacionadas antes do próximo deploy.
- **Upload de secrets**: APENAS `gcloud secrets versions add`. Nunca `versions
  update` (bug 12/07/2026 corrompeu chave DeepSeek).
- **Sem Gemini API** para inferência LLM fora do fallback STT. STT Gemini só é
  acionado para transcrição quando Whisper falha tecnicamente **e** há
  consentimento registrado.
- **`agents_runtime` não expõe Swagger público** (`/docs`, `/redoc`,
  `/openapi.json` proibidos).
- **`/admin/*`, `/chat`, `/proactive/send` exigem Bearer SA token ou Firebase
  ID token**. `/admin/dashboard` aceita Authorization header.
- **Tokens não trafegam em query string**. O `?token=` antigo foi removido do
  UI e do middleware.
- **Webhook aceita apenas payload Evolution válido**; filtros aplicam
  Evolution event, broadcast, fromMe e MIME.

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
- Tick não bloqueia nem repete o webhook: timeout máximo 5 s, sem retry.
- Remetente precisa coincidir com `owner_phone` da instância Evolution para
  acessar Gmail, Drive ou Calendar.

## 6. Áudio

- Whisper local é o caminho padrão; download valida host, MIME, tamanho
  (25 MB), duração (5 min) e ausência de redirecionamento.
- Fallback Gemini 2.5 Flash só dispara quando Whisper falha tecnicamente **e**
  `STT_FALLBACK_CONSENT=true` ou `extra.audio_consent_external=true`.
- Limite diário do fallback: 20 chamadas (`STT_FALLBACK_DAILY_LIMIT`).
- Áudio bruto nunca é persistido; temporários são apagados em `finally`.
- Transcrição é mascarada antes de qualquer embedding ou LLM.

## 7. Firestore Vector vs Firestore plain

23/07/2026: o Firestore Vector é **restrito a documentos** (livros,
editais, base coletiva e pública). Toda interação do chat é persistida
em Firestore plain (`message-history/{history_id}`) com indexação por
`owner_hash = sha256(phone_digits)[:32]`.

- `index_conversation_message()` — hot path: grava em
  `message-history` plain **e nunca** em vector. Falhas de Firestore
  são logadas e o retorno segue 200 (a interação não trava).
- `scripts/ingest_owner_knowledge.py` e
  `scripts/ingest_collective_memory.py` — únicos locais onde embedding
  + Firestore Vector são aplicados.
- `search_conversation_memory()` lê **plain** Firestore filtrando
  `where("owner_hash", ==, _owner_hash(phone))` e ordena por
  `created_at` desc. Resultado devolve `[]` quando `phone` é vazio.
- A coleção vetorial legada `conversation-memory-v2` não é mais
  alimentada em produção; pode ser removida após confirmação das novas
  gravações.

## 7. Embeddings

- OpenAI `text-embedding-3-small` (1536d) é o único provedor aceito em v2.
- Nenhuma coleção vetorial aceita mistura de modelos/dimensões — toda
  inserção deve carregar `embedding_model`/`embedding_dim`.
- Coleções filtram `owner_hash == owner_id` em toda leitura.
- Base pública (`public-knowledge-v2`) **nunca** recebe `owner_hash`.

## 8. OAuth Google

- Escopos mínimos obrigatórios: `gmail.readonly + gmail.send`,
  `drive.file + drive.readonly`, `calendar + calendar.events`.
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

## 11. Pendências

- Rotação efetiva das credenciais expostas no commit `ad6399a`.
- Backfill de embeddings para novos `owner_hash` da coleção legada
  `contatos/.../historico`.
- Remoção completa do proxy `WhatsappAgente` e do serviço legado.