# Fase E — agent-privacy-guard testado + deploy agent-proatividade

## Entendimento

- O `agent-privacy-guard` ja esta integrado em `orchestrator.py:_is_personal_intent` + `_is_group_message` (linhas 803-844). Falta cobertura de testes deterministica.
- O `agent-proatividade` ja existe em `proactive_worker/main.py` com 2 modos (events, topics). O `cloudbuild-proactive-test.yaml` referencia `GOOGLE_OAUTH_TOKEN` (obsoleto desde Fase D) e precisa de Dockerfile/Cloud Scheduler documentados.
- O gate local exige zero falhas, zero erros, zero warnings, Ruff zero, mypy zero e LGPD zero.

## Premissas

- Toda alteracao dependente das Fases A/B/C/D permanece em `HEAD~1` (commit `ff6375f` da Fase D).
- O secret `GOOGLE_OAUTH_TOKEN` NAO e mais consumido em `agents_runtime/` desde a Fase D; pode ser removido do `--set-secrets` do job `proactive-worker-test`.
- Workers continuam iterando por telefone via `ATA_WORKER_PHONES` / `PROACTIVE_WORKER_PHONES`.
- Nenhum teste sera afrouxado, removido ou marcado como `xfail`/`skip` apenas para obter verde.
- A documentacao permanente sera atualizada **somente** apos o gate tecnico ficar verde.

## Escopo tecnico

| Bloco | Itens | Arquivos |
|---|---|---|
| E.1 | Adicionar testes do `agent-privacy-guard` no orchestrator | `tests/test_orchestrator.py` |
| E.2 | Remover `GOOGLE_OAUTH_TOKEN` do `cloudbuild-proactive-test.yaml` | `cloudbuild-proactive-test.yaml` |
| E.3 | Adicionar `Dockerfile` ao `LGPD compliance check` (worker precisa rodar `check_lgpd_compliance.py`) | `scripts/check_lgpd_compliance.py`, `proactive_worker/Dockerfile`, `ata_worker/Dockerfile` |
| E.4 | Documentar Fase E | `ARQUITETURA.md`, `HARNESS.md`, `GUARDRAILS.md`, `DIARIO_BORDO.md`, `PLANO_DETALHADO.md`, `docs/fases/fase_E/checklist.md` |

## Execucao

1. Confirmar baseline: `pytest -q tests/` deve estar em 312 passed, 10 skipped.
2. E.1 — Em `tests/test_orchestrator.py`, adicionar `TestPrivacyGuard` com 4 testes:
   - `test_personal_intent_in_group_with_unconfirmed_member_sets_pending_action` — verifica que `pending_action: group_consent` foi gravado e resposta cita Portal.
   - `test_personal_intent_in_group_with_confirmed_member_proceeds` — verifica que o agent foi executado e metadata nao tem `blocked`.
   - `test_personal_intent_in_private_proceeds` — verifica que sem group_jid nao ha checagem.
   - `test_personal_intent_unregistered_user_returns_portal_link` — verifica resposta com `metadata.agent_id == 'privacy-guard'` e `blocked == 'unregistered_user'`.
3. E.2 — `cloudbuild-proactive-test.yaml`: remover `GOOGLE_OAUTH_TOKEN=google-oauth-token:latest` de `--set-secrets`. Adicionar `PROACTIVE_WORKER_PHONES=` placeholder (vazio por padrao, populado via Cloud Scheduler env override).
4. E.3 — `scripts/check_lgpd_compliance.py`: adicionar `agents_runtime/proactive_worker/Dockerfile` e `agents_runtime/ata_worker/Dockerfile` ao `REQUIRED_FILES`. Atualizar testes em `tests/test_lgpd_compliance.py` para refletir.
5. E.4 — Atualizar `GUARDRAILS.md` (nova regra 54 sobre privacy-guard automatico), `HARNESS.md` (gate da Fase E + Cloud Scheduler procedure), `ARQUITETURA.md` (status do deploy do proactive-worker), `DIARIO_BORDO.md` (entrada da Fase E).
6. Rodar gate ate zero.
7. Commit atomico `feat(fase-E): privacy-guard testado + proactive-worker deploy`.

## Criterios de aceite

- `pytest -q tests/` retorna `passed` sem `failed`, `error` ou warning de projeto.
- 4 testes novos do `TestPrivacyGuard` verdes.
- `python scripts/check_lgpd_compliance.py` passa com os novos arquivos exigidos.
- `ruff check .` retorna exit code 0.
- `mypy core/ orchestrator.py main.py agent_loader.py tool_registry.py` retorna `Success: no issues found`.
- `cloudbuild-proactive-test.yaml` NAO referencia mais `GOOGLE_OAUTH_TOKEN`.
- Documentos permanentes atualizados.

## Decisoes

| Decisao | Alternativas | Motivo |
|---|---|---|
| Cobrir privacy-guard via testes sincronos | Mock de todo o orchestrator | Cobertura direta dos 4 ramos: grupo confirmado, nao confirmado, privado, unregistered |
| Manter Dockerfile do proactive worker identico ao ata_worker | Worker generico compartilhado | Mantem padrao; gate LGPD checa existencia do arquivo |
| Remover GOOGLE_OAUTH_TOKEN do job | Manter como no-op por compatibilidade | Evita queries ao Secret Manager para secret descontinuado |