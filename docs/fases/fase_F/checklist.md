# Fase F — Checklist

**Data inicio:** 2026-07-21
**Branch:** test
**Gate:** pytest verde (zero warning) + Ruff/mypy/LGPD zero + 4 docs permanentes atualizadas + 3 procedures externas criadas

## Escopo

Documentar procedures externas para o usuario executar o cleanup pos-merge
(secrets orfaos, pasta local, repo GitHub) e configurar OAuth per-user no
Google Cloud Console. Nenhum codigo novo introduzido — gate local deve
permanecer verde sem regressao.

## Tarefas

| # | Tarefa | Status |
|---|---|---|
| 1 | Criar `docs/fases/fase_F/cleanup_secrets.md` | concluida |
| 2 | Criar `docs/fases/fase_F/cleanup_repo.md` | concluida |
| 3 | Criar `docs/fases/fase_F/oauth_setup.md` | concluida |
| 4 | Atualizar `docs/HARNESS.md` com lista de secrets + troubleshooting OAuth | concluida |
| 5 | Adicionar regra 56 em `docs/GUARDRAILS.md` | concluida |
| 6 | Atualizar `docs/ARQUITETURA.md` com nota de cleanup pendente | concluida |
| 7 | Atualizar `docs/DIARIO_BORDO.md` com entrada da Fase F | concluida |
| 8 | Atualizar `docs/PLANO_DETALHADO.md` status para F+ | concluida |
| 9 | Gate tecnico verde (pytest 316, ruff 0, mypy 0, LGPD 0) | concluida |
| 10 | Commit atomico | a executar |

## Evidencias do gate (sem regressao)

| Validador | Comando | Resultado |
|---|---|---|
| Suite completa | `pytest -q tests/` | `316 passed, 10 skipped` (zero failed, zero error, zero warning) |
| Ruff | `ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/ ata_worker/ proactive_worker/` | `All checks passed!` |
| Mypy | `mypy --no-incremental --explicit-package-bases --follow-imports=silent core/` | `Success: no issues found in 25 source files` |
| LGPD compliance | `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

## Resumo das fases

| Fase | Commit | Gate | Pendencias internas |
|---|---|---|---|
| A | `e38471a` | verde | nenhuma |
| B | `d0bb97b` | verde | nenhuma |
| C | `1862d51` | verde | nenhuma |
| D | `ff6375f` | verde | nenhuma |
| E | `6f095d8` | verde | nenhuma |
| F | (este commit) | verde | nenhuma |

## Pendencias externas (transferidas ao usuario)

Apos merge de `test` em `main`:

- [ ] Executar `docs/fases/fase_F/cleanup_secrets.md`
- [ ] Executar `docs/fases/fase_F/cleanup_repo.md`
- [ ] Executar `docs/fases/fase_F/oauth_setup.md`

Ate a conclusao desses passos, o sistema permanece em estado de transicao.