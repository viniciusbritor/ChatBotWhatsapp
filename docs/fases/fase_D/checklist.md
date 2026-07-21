# Fase D — Checklist

**Data inicio:** 2026-07-21
**Branch:** test
**Gate duplo:** pytest verde (zero warning) + Ruff/mypy/LGPD zero + 4 docs permanentes atualizadas

## Escopo

Remover o fallback global `GOOGLE_OAUTH_TOKEN` nos 3 managers e tornar `phone` obrigatorio em `tools/google_calendar.py`, `tools/google_drive.py` e `tools/google_gmail.py`. Propagar `phone` em `tools/ata_helper.py`, `ata_worker/main.py` e `proactive_worker/main.py`. Cobrir o caminho per-user com testes deterministicos.

## Investigacao

| # | Hipotese | Resultado |
|---|---|---|
| 1 | Fallback global e ainda usado pelos 3 managers | **VERDADEIRO** — `_get_credentials(phone=None)` ainda consultava `core.secrets.get_secret("GOOGLE_OAUTH_TOKEN")` |
| 2 | Callers passam `phone` consistentemente | **PARCIAL** — orchestrator passa; ata_helper, ata_worker e proactive_worker NAO passam |
| 3 | Cache por telefone ja isola sessoes | **VERDADEIRO** — `_calendar_services`, `_drive_services`, `_gmail_services` ja sao `Dict[str, Any]` indexados por telefone |
| 4 | Mover `phone` para primeiro parametro quebra callers | **VERDADEIRO** — assinatura obrigaria reordenacao de todos os call-sites |
| 5 | Workers iteram por usuario para coletar eventos | **FALSO** — `ata_worker` e `proactive_worker` usavam apenas o token global |

## Tarefas

| # | Tarefa | Status |
|---|---|---|
| 1 | Mover `phone` para primeiro parametro em `tools/google_calendar.py` (5 funcoes) | concluida |
| 2 | Mover `phone` para primeiro parametro em `tools/google_drive.py` (5 funcoes) | concluida |
| 3 | Mover `phone` para primeiro parametro em `tools/google_gmail.py` (3 funcoes) | concluida |
| 4 | Remover fallback global e `get_secret("GOOGLE_OAUTH_TOKEN")` nos 3 managers | concluida |
| 5 | Atualizar `orchestrator.py` (4 prefetch calls) | concluida |
| 6 | Atualizar `tools/ata_helper.py` (save_ata_to_drive, notify_organizer) | concluida |
| 7 | Atualizar `ata_worker/main.py` (find_recent_meetings, find_event_thread, process_event, main loop) | concluida |
| 8 | Atualizar `proactive_worker/main.py` (scan_upcoming_events, run_events_scan) | concluida |
| 9 | Reescrever testes dos 3 managers com `phone` obrigatorio + 3 testes novos de caminho per-user | concluida — 9 testes adicionados |
| 10 | Cobrir LGPD compliance check (gate da Fase C) | ja passou |
| 11 | Atualizar 4 docs permanentes (ARQUITETURA, HARNESS, GUARDRAILS, DIARIO_BORDO) + PLANO_DETALHADO + checklist | concluida |
| 12 | Commit atomico | a executar |

## Evidencias do gate

| Validador | Comando | Resultado |
|---|---|---|
| Suite completa | `pytest -q tests/` | `312 passed, 10 skipped` (zero failed, zero error, zero warning) |
| Tests especificos | `pytest -q tests/test_google_calendar.py tests/test_google_drive.py tests/test_google_gmail.py` | 33 passed (24 existentes + 9 novos per-user OAuth) |
| Ruff | `ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/` | `All checks passed!` |
| Mypy | `mypy --no-incremental --explicit-package-bases --follow-imports=silent core/` | `Success: no issues found in 25 source files` |
| LGPD compliance | `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

## Pendencias externas (continuam para Fase E+)

- Provisionar indices Firestore Vector v2 no projeto GCP de teste.
- Reindexacao real do corpus no ambiente de teste.
- Build da imagem com o modelo Whisper pre-baixado.
- Implantar a branch `test` (gate atual e green build).
- Provisionar `ATA_WORKER_PHONES` e `PROACTIVE_WORKER_PHONES` no Cloud Scheduler / Cloud Run env.
- Provisionar Authorized redirect URIs do OAuth Client no Google Cloud Console (Fase B item 10).