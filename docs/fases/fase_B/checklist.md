# Fase B — Checklist

**Data inicio:** 2026-07-21
**Branch:** test
**Gate duplo:** pytest verde + 4 docs permanentes atualizados

## Escopo

Investigar e corrigir o bug reportado "audio quebra RAG por usuario".
Investigar a causa raiz, fortalecer o pipeline audio->Pub/Sub->RAG.

## Investigacao

| # | Hipotese | Resultado |
|---|---|---|
| 1 | message_id nao chega do Evolution ate `_index_message` | **FALSO** — pipeline testado E2E, message_id chega corretamente |
| 2 | Dedupe por message_id falha em audio retry | **FALSO** — `_dedupe` no pubsub_consumer funciona |
| 3 | owner_hash inconsistente entre audio e texto | **FALSO** — `_owner_hash` normaliza telefone corretamente |
| 4 | Whisper falha e mensagem de audio nao indexada | **VERDADEIRO** — quando Whisper falha, mensagem sai sem chamar `orchestrate`, audio NAO entra no RAG |
| 5 | Logs insuficientes para detectar problemas futuros | **VERDADEIRO** — sem telemetria sobre fallback de message_id |

## Tarefas

| # | Tarefa | Status |
|---|---|---|
| 1 | Teste integracao audio pipeline RAG (7 testes) | concluida — 7 testes de fluxo cobertos |
| 2 | Indexar audio mesmo quando transcricao falha (caminho except) | concluida — marcador de auditoria mascarado persistido |
| 3 | Telemetria: log WARN quando message_id cai no fallback | concluida — owner_hash, sem telefone bruto |
| 4 | Suite pytest completa (221+ + 7 novos) | concluida — 17 testes especificos; suite isolada com 249 passed e 9 skipped |
| 5 | Atualizar 4 docs permanentes | concluida |
| 6 | Commit atomico | pendente — sera criado apos validar o conjunto final da B.7 |

## Evidencias do gate

- Testes especificos: `17 passed` em Python 3.12.
- Suite geral isolada: `249 passed, 9 skipped`.
- Ruff: `All checks passed`.
- Mypy: `Success: no issues found in 19 source files`.
- Os 9 skips pertencem aos testes de proatividade que exigem allowlist configurada; nao representam falha do pipeline de audio.
- O warning de tarefa RAG pendente foi classificado como hardening de confiabilidade para a Fase C e nao altera o resultado dos testes.


- Mudanca no except do /chat pode alterar comportamento atual. Mitigacao: teste de regressao cobre o caso.
- Adicionar log pode aumentar volume. Mitigacao: usar WARN (nao ERROR) e apenas quando message_id realmente cai no fallback.
