# Fase D — OAuth per-user nos managers

## Entendimento

- A infraestrutura de OAuth per-user (`core.oauth_per_user.py`) e os 3 managers
  (`tools/google_calendar.py`, `tools/google_drive.py`, `tools/google_gmail.py`)
  ja aceitam `phone: Optional[str]` para escolher entre o token global
  (`GOOGLE_OAUTH_TOKEN`) e o token por usuario (`core.oauth_per_user.get_user_credentials`).
- A fase atual precisa fechar a transicao: tornar `phone` obrigatorio nos 3
  managers, remover o fallback global, ajustar os callers que ainda dependem
  dele (`tools/ata_helper.py`, `proactive_worker/main.py`,
  `ata_worker/main.py`) e cobrir o caminho per-user com testes deterministicos.
- O gate local exige zero falhas, zero erros, zero warnings, Ruff zero, mypy
  zero e LGPD zero.

## Premissas

- Toda alteracao dependente das Fases A/B/C permanece em `HEAD~1` (commit
  `1862d51` da Fase C).
- O secret `GOOGLE_OAUTH_TOKEN` continua existindo no Secret Manager durante a
  transicao para evitar indisponibilidade do `ata_worker`/`proactive_worker`,
  mas o codigo nao consulta mais o caminho global por padrao.
- Nenhum teste sera afrouxado, removido ou marcado como `xfail`/`skip`
  apenas para obter verde.
- A documentacao permanente sera atualizada **somente** apos o gate tecnico
  ficar verde.
- Nenhum commit, push ou deploy executado nesta fase alem do commit final
  atomico apos gate verde.

## Escopo tecnico

| Bloco | Itens | Arquivos |
|---|---|---|
| D.1 | Tornar `phone` obrigatorio nos 3 managers | `tools/google_calendar.py`, `tools/google_drive.py`, `tools/google_gmail.py` |
| D.2 | Propagar `phone` em `tools/ata_helper.py` | `tools/ata_helper.py`, `ata_worker/main.py` |
| D.3 | Propagar `phone` em `proactive_worker/main.py` | `proactive_worker/main.py` |
| D.4 | Adicionar testes do caminho per-user | `tests/test_google_calendar.py`, `tests/test_google_drive.py`, `tests/test_google_gmail.py`, `tests/test_oauth_per_user.py` (novo) |
| D.5 | Documentar Fase D | `ARQUITETURA.md`, `HARNESS.md`, `GUARDRAILS.md`, `DIARIO_BORDO.md`, `PLANO_DETALHADO.md`, `docs/fases/fase_D/checklist.md` |

## Execucao

1. Confirmar baseline atual: `pytest -q tests/` (303 passed, 10 skipped).
2. D.1 — Refatorar `_get_credentials(phone)` para aceitar `phone: str`
   obrigatorio. Quando `phone` vazio, levantar `RuntimeError` claro em vez de
   cair no fallback global.
3. D.2 — `tools/ata_helper.save_ata_to_drive(event, ata_markdown, phone)` e
   `tools/ata_helper.notify_organizer(..., phone)`. `ata_worker/main.py`
   resolve `phone` por evento (organizador -> usuarios Firestore) antes de
   delegar.
4. D.3 — `proactive_worker/main.py` recebe `ATA_WORKER_PHONES` (env ou lista
   hardcoded com allowlist) e processa cada usuario com seu proprio token.
5. D.4 — Adicionar testes:
   - `test_google_calendar.py`: novo teste verifica que `_get_credentials`
     chama `core.oauth_per_user.get_user_credentials` quando recebe `phone`.
   - `test_google_drive.py` e `test_google_gmail.py`: equivalentes.
   - `test_oauth_per_user.py`: testes do refresh automatico, persistencia e
     escopo por telefone (16 testes ja existentes, manter todos verdes).
6. D.5 — Atualizar `GUARDRAILS.md` (refinar regra 47 sobre OAuth per-user),
   `HARNESS.md` (gate de reproducao), `ARQUITETURA.md` (status do fallback
   global), `DIARIO_BORDO.md` (entrada da Fase D).
7. Rodar gate: pytest + ruff + mypy + LGPD ate sair zero.
8. Commit atomico `feat(fase-D): oauth per-user obrigatorio nos 3 managers`.

## Criterios de aceite

- `pytest -q tests/` retorna `passed` sem `failed`, `error` ou warning de
  projeto.
- `pytest -q tests/test_google_calendar.py tests/test_google_drive.py
  tests/test_google_gmail.py tests/test_oauth_per_user.py` cobre o caminho
  per-user e o caminho de erro (sem `phone`).
- `ruff check .` retorna exit code 0.
- `mypy core/ orchestrator.py main.py agent_loader.py tool_registry.py` retorna
  `Success: no issues found`.
- `python scripts/check_lgpd_compliance.py` retorna exit code 0.
- Nenhum dos 3 managers consulta mais `get_secret("GOOGLE_OAUTH_TOKEN")`.
- `tools/ata_helper.py`, `proactive_worker/main.py` e `ata_worker/main.py`
  propagam `phone` em todas as chamadas aos 3 managers.
- Documentos permanentes atualizados.

## Decisoes

| Decisao | Alternativas | Motivo |
|---|---|---|
| `phone` obrigatorio (sem fallback) | Manter fallback opcional com warning | Forca callers a explicitar contexto; alinha com LGPD por usuario |
| Workers iteram por `ATA_WORKER_PHONES` | Service account global para workers | Mantem isolamento por usuario; segue regra 47 do GUARDRAILS |
| `phone` resolvido por organizador no ata_worker | Pool de SAs dedicado para worker | Reaproveita mapeamento existente `usuarios/{phone}/google_oauth_token` |
| Tests deterministicos (mockam `_get_credentials`) | Tests de integracao contra GCP | Mantem gate local rapido e sem credenciais reais |