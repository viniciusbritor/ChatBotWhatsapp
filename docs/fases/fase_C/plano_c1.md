# Fase C — Hardening de Confiabilidade

## Entendimento

- A Fase B foi aprovada (commit `d0bb97b`) e deixou pendente um aviso de tarefa RAG em background durante o shutdown do pytest, separado deliberadamente para nao misturar escopos.
- Ao retomar a esteira, o estado local divergiu do HEAD: ha alteracoes nao commitadas em `core/`, `orchestrator.py`, `main.py`, `tool_registry.py`, varios `tools/*.py` e novos arquivos (OAuth per-user, logging estruturado, testes de Pub/Sub, docs LGPD, scripts de compliance).
- A suite atual do `agents_runtime` apresenta 5 falhas e 3 warnings, mesmo isolando secrets reais. Nenhum desses itens pode seguir como "deferred" ou "skipped".
- O gate da Fase C exige zero falhas, zero erros, zero warnings, Ruff zero, mypy zero.

## Premissas

- Toda alteracao dependente da Fase B sera preservada (commit `d0bb97b` permanece base).
- Os artefatos ja presentes (OAuth per-user, logging, testes Pub/Sub, LGPD) serao estabilizados e cobertos por testes; nada sera revertido sem evidencia de regressao.
- Nenhum teste sera afrouxado ou marcado como `xfail`/`skip` apenas para obter verde.
- Nenhum segredo real sera carregado pelo ambiente de teste; quando necessario, sera injetado via `monkeypatch`.
- A documentacao permanente sera atualizada **somente** apos o gate tecnico ficar verde.

## Escopo tecnico

| Bloco | Itens | Origem |
|---|---|---|
| C.1 Estabilizar testes existentes | corrigir cascade order em `test_llm_provider.py`; precedencia de `OPENAI_API_KEY` em `core/rag.py`; dependencia `tzdata` | erros pre-existentes conhecidos |
| C.2 Eliminar `ResourceWarning` | fechar event loop em `chat_escalating` (async) | warning de shutdown observado na Fase B |
| C.3 Ativar trabalho em andamento | `core/oauth_per_user.py`, `core/logging.py`, `core/evolution_client.py`, `tests/test_*_pubsub*`, `tests/test_main_*`, `tests/integration/`, `tests/load/` | PLANO_DETALHADO.md itens 1-4 |
| C.4 Cobertura minima de LGPD | `scripts/check_lgpd_compliance.py` + guardrail dedicado | PLANO_DETALHADO.md item de compliance |
| C.5 Documentacao | `ARQUITETURA.md`, `HARNESS.md`, `GUARDRAILS.md`, `DIARIO_BORDO.md` + esteira oficial | regra 0 do harness global |

## Execucao

1. Confirmar baseline isolada com Python 3.12, sem chaves reais.
2. Aplicar correcoes minimas dos testes pre-existentes (bloco C.1).
3. Corrigir `ResourceWarning` no caminho async de `chat_escalating` (bloco C.2).
4. Habilitar e validar os novos modulos com testes verdes:
   - `core.oauth_per_user.refresh_user_google_token`
   - `core.logging.JsonFormatter` (timestamp BRT, payload estavel)
   - `core.evolution_client` (extrator canonico ja em `core.evolution_webhook`)
   - testes do Pub/Sub publisher/consumer
   - testes de `/webhook`, `/pubsub/push`, `/oauth/*`
5. Configurar `pyproject.toml`/`requirements-dev.txt` com `tzdata`.
6. Garantir que `pytest -q tests/` retorna `0 failed, 0 errors`, sem warnings de projeto.
7. Rodar `ruff check` e `mypy --strict` ate sair zero.
8. Atualizar `ARQUITETURA.md`, `HARNESS.md`, `GUARDRAILS.md`, `DIARIO_BORDO.md` com o resumo da fase.
9. Apresentar evidencias finais.

## Criterios de aceite

- `pytest -q tests/` retorna `passed` sem `failed`, `error` ou warning de projeto.
- `pytest -q tests/test_llm_provider.py` cobre a nova ordem de cascade (MiniMax-M2.7-highspeed -> MiniMax M3 -> DeepSeek V4 Flash) com assertions alinhadas.
- `pytest -q tests/integration/` retorna verde sem dependencia externa real (Firestore/Pub/Sub mockados).
- `ruff check .` retorna exit code 0.
- `mypy core orchestrator.py main.py tool_registry.py agent_loader.py` retorna `Success: no issues found`.
- Nenhum `ResourceWarning` de event loop nao fechado durante o teardown.
- Documentos permanentes atualizados com a data e hash de gate.
- Nenhum commit, push ou deploy realizado (gate local).

## Decisoes

| Decisao | Alternativas | Motivo |
|---|---|---|
| Atualizar testes do cascade | Reverter ordem do cascade para DeepSeek primeiro | A priorizacao do MiniMax-M2.7-highspeed foi decisao de Fase A; voltar atras geraria retrabalho maior |
| Tornar `get_secret` fonte unica de chave no `_embed_direct` | Deixar o teste robusto via `monkeypatch.delenv` | Centraliza o fluxo seguro; segue o padrao de `core/secrets.py` |
| Adicionar `tzdata` em `requirements-dev.txt` | Usar `zoneinfo` Windows-only | Mantem paridade com Cloud Build (linux) e com demais testes BRT |
| Fechar loop async em `chat_escalating` via `asyncio.run(...)` isolado | Trocar a fixture pytest-asyncio | Menos invasivo, mantem compatibilidade com o mock `requests.post` ja em uso |