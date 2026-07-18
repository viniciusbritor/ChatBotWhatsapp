# Guardrails — agents_runtime

> Regras inegociaveis para implementacao no `agents_runtime`.

> **Documento mestre:** [`ChatBotWhatsapp/docs/GUARDRAILS.md`](../../GUARDRAILS.md)

## Restricoes Criticas

### Seguranca
1. Nenhuma chave de API hardcoded. Usar `core/secrets.py` (env → Secret Manager → default).
2. Upload de secrets APENAS via `gcloud secrets versions add` (nunca `update`).
3. **Sem Gemini API** (Vertex AI ou AI Studio). Embeddings via OpenAI text-embedding-3-small.
4. **Sem Swagger publico** (`/docs`, `/redoc`, `/openapi.json` removidos).
5. **`/chat`, `/proactive/send`, `/admin/*`** exigem Bearer SA token.
6. **Sem UI propria** — toda gestao via Portal.

### LGPD
7. **Masker obrigatorio** antes de todo LLM externo.
8. PII patterns: CPF, RG, telefone, email, cartao, CNPJ.
9. **Nunca** retornar PII cru em respostas.

### Codigo
10. **Sem `$` solto** (LaTeX conflict).
11. **Sem comentarios** no codigo (regra global).
12. **5 tentativas por erro especifico** antes de parar.

## Regras de Ouro

1. Cascata LLM: DeepSeek V4 Flash → NVIDIA NIM → MiniMax M3.
2. Escalation Flash → Pro por heuristica (threshold -2).
3. Static-first prompts para cache DeepSeek.
4. Thinking desabilitado por padrao.
5. Typing effect: `min(0.6 × palavras × 1000, 15000)`.
6. Whisper background load.

## Estado: Fase 1

Implementacoes ja alinhadas com todas as regras acima.