# Fase C — Checklist

**Data inicio:** 2026-07-21
**Branch:** test
**Gate duplo:** pytest verde (zero warning) + Ruff/mypy/LGPD zero + 4 docs permanentes atualizadas

## Escopo

Estabilizar trabalho em andamento apos a Fase B, corrigir testes pre-existentes, eliminar `ResourceWarning` de event loop, endurecer cobertura LGPD e fechar 4 docs permanentes.

## Investigacao

| # | Hipotese | Resultado |
|---|---|---|
| 1 | Suite diverge do gate B.6 por regressao | **VERDADEIRO** — 5 falhas e 3 warnings no estado nao commitado |
| 2 | `ResourceWarning` vem de `asyncio.run` em testes sincronos | **VERDADEIRO** — `test_llm_provider.py` misturava `asyncio.run` com `pytest-asyncio` strict mode |
| 3 | Cascade LLM ainda prioriza DeepSeek | **FALSO** — Fase A reordenou para MiniMax-M2.7-highspeed primeiro; testes precisavam refletir a ordem vigente |
| 4 | `core.rag._embed_direct` prioriza env var sobre `get_secret` | **VERDADEIRO** — permitia contaminacao em testes com `OPENAI_API_KEY=dummy` |
| 5 | `ZoneInfo("America/Sao_Paulo")` exige `tzdata` em runner sem tz local | **VERDADEIRO** — pytest estruturado de log falhava por `ZoneInfoNotFoundError` |
| 6 | DeprecationWarning de `google._upb._message` e do projeto | **FALSO** — vem do C-extension do protobuf 4.25; filtrado via `pyproject.toml` |

## Tarefas

| # | Tarefa | Status |
|---|---|---|
| 1 | Reescrever `tests/test_llm_provider.py` com `@pytest.mark.asyncio` | concluida — 12 testes verdes |
| 2 | Ajustar cascade order nos asserts para MiniMax-M2.7-highspeed | concluida — `test_minimax_highspeed_first`, `test_cascade_fallback_to_deepseek`, `test_no_escalation_when_confident` |
| 3 | `core/rag.py`: `get_secret` antes de `os.getenv` | concluida — chave OpenAI vem do Secret Manager com fallback explicito |
| 4 | Adicionar `tzdata>=2024.1` em `requirements-dev.txt` | concluida — instalado no `.venv-c` |
| 5 | Adicionar `filterwarnings` no `pyproject.toml` para third-party protobuf | concluida — 0 warnings do projeto |
| 6 | Cobrir `scripts/check_lgpd_compliance.py` com `tests/test_lgpd_compliance.py` | concluida — 3 testes (pass / missing file / missing snippet) |
| 7 | Corrigir Ruff em `tests/` (40 fixes + 7 manuais) | concluida — `All checks passed!` |
| 8 | Corrigir Mypy (`has_nickname.cache`, `tool_calls`) | concluida — `Success: no issues found in 25 source files` |
| 9 | Atualizar DIARIO_BORDO, ARQUITETURA, GUARDRAILS, HARNESS | concluida |
| 10 | Commit atomico | pendente — a executar apos validacao final do conjunto D+ |

## Evidencias do gate

| Validador | Comando | Resultado |
|---|---|---|
| Suite completa | `pytest -q tests/` | `303 passed, 10 skipped` (zero failed, zero error, zero warning) |
| Tests especificos | `pytest -q tests/test_llm_provider.py tests/test_rag.py::TestOpenAIEmbeddingContract tests/test_structured_logging.py` | 16 passed |
| Ruff | `ruff check tests/ core/ main.py orchestrator.py agent_loader.py tool_registry.py tools/ scripts/` | `All checks passed!` |
| Mypy | `mypy --no-incremental --explicit-package-bases --follow-imports=silent core` | `Success: no issues found in 25 source files` |
| LGPD compliance | `python scripts/check_lgpd_compliance.py` | `LGPD compliance checks passed` |

## Pendencias externas (continuam para Fase D+)

- Provisionar indices Firestore Vector v2 no projeto GCP de teste.
- Reindexacao real do corpus no ambiente de teste.
- Build da imagem com o modelo Whisper pre-baixado.
- Implantar a branch `test` (gate atual e green build).
- Migrar `manager-calendar`, `manager-drive`, `manager-email` para `core.oauth_per_user`.