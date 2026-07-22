# Fase E — Checklist

**Data inicio:** 2026-07-21
**Branch:** test
**Gate duplo:** pytest verde (zero warning) + Ruff/mypy/LGPD zero + 4 docs permanentes atualizadas

## Escopo

Cobrir `agent-privacy-guard` com testes deterministicos, remover `GOOGLE_OAUTH_TOKEN` do `cloudbuild-proactive-test.yaml` (obsoleto desde Fase D), exigir `Dockerfile` dos workers no LGPD compliance check e atualizar 4 docs permanentes.

## Investigacao

| # | Hipotese | Resultado |
|---|---|---|
| 1 | `agent-privacy-guard` ja integrado no orchestrator | **VERDADEIRO** — `_is_personal_intent + _is_group_message + set_pending_action` em orchestrator.py:803-844 |
| 2 | Tests do privacy-guard existem | **FALSO** — caminho nao coberto |
| 3 | `cloudbuild-proactive-test.yaml` referencia secret obsoleto | **VERDADEIRO** — `--set-secrets=...GOOGLE_OAUTH_TOKEN=google-oauth-token:latest` |
| 4 | LGPD compliance check exige Dockerfile do worker | **FALSO** — so exigia `masker.py`, `docs/PRIVACIDADE.md`, `docs/TERMOS.md` |

## Tarefas

| # | Tarefa | Status |
|---|---|---|
| 1 | Adicionar `TestPrivacyGuard` (4 testes) em `tests/test_orchestrator.py` | concluida — 4 testes verdes |
| 2 | Remover `GOOGLE_OAUTH_TOKEN` do `cloudbuild-proactive-test.yaml` | concluida |
| 3 | Adicionar `Dockerfile`, `ata_worker/Dockerfile`, `proactive_worker/Dockerfile` ao `scripts/check_lgpd_compliance.py` | concluida |
| 4 | Atualizar `tests/test_lgpd_compliance.py` para os 3 Dockerfiles | concluida |
| 5 | Atualizar 4 docs permanentes (ARQUITETURA, HARNESS, GUARDRAILS, DIARIO_BORDO) + PLANO_DETALHADO + checklist | concluida |
| 6 | Commit atomico | a executar |

## Evidencias do gate

| Validador | Comando | Resultado |
|---|---|---|
| Suite completa | `pytest -q tests/` | `316 passed, 10 skipped` (zero failed, zero error, zero warning) |
| Tests especificos | `pytest -q tests/test_orchestrator.py::TestPrivacyGuard` | 4 passed |
| Ruff | `ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/` | `All checks passed!` |
| Mypy | `mypy --no-incremental --explicit-package-bases --follow-imports=silent core/` | `Success: no issues found in 25 source files` |
| LGPD compliance | `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

## Pendencias externas (continuam para Fase F+)

- Provisionar indices Firestore Vector v2 no projeto GCP de teste.
- Reindexacao real do corpus no ambiente de teste.
- Build da imagem com o modelo Whisper pre-baixado.
- Implantar a branch `test` (gate atual e green build).
- Provisionar `ATA_WORKER_PHONES` e `PROACTIVE_WORKER_PHONES` no Cloud Scheduler / Cloud Run env.
- Provisionar Authorized redirect URIs do OAuth Client no Google Cloud Console (PLANO_DETALHADO item 10).
- Deletar secrets orfaos do Secret Manager (PLANO_DETALHADO item 12).
- Deletar pasta local `WhatsappAgente/` (PLANO_DETALHADO item 13).
- Deletar repo `viniciusbritor/WhatsappAgente` no GitHub (PLANO_DETALHADO item 14).
- Provisionar Cloud Scheduler para `proactive-worker-test` (cron: */15min eventos + Tue/Fri 8h BRT topicos).