# CURRENT_PLAN.md — Plano de Execução por Fases (30/07/2026)

> ⚠️ **DOCUMENTO HISTÓRICO / ARQUIVADO** — conforme atualização de 16/08/2026.
> Este plano (Fases A-F de 30/07/2026) foi substancialmente superado pelos desenvolvimentos
> das sessões de 13-16/08/2026 (RAG overhaul, Composio, multi-tenant, FinOps Shield,
> Anti-Duplicação, etc). As pendências ativas estão agora em [`STATE.md`](../STATE.md)
> e o narrative detalhado em [`DIARIO_BORDO.md`](./DIARIO_BORDO.md).
>
> Mantido aqui apenas para referencia historica e audit trail.
>
> **Fonte autoritativa de pendências:** [`STATE.md`](../STATE.md)

## 🎯 Direcionamentos (do usuário, 30/07/2026)

1. **Reduzir latência** de resposta
2. **Parecer humana** — tom caloroso, decisões formatadas para fácil leitura humana
3. **Preservar privacidade** individual E do grupo
4. **Armazenar** em base de conhecimento quando pedido → **recuperar** via RAG
5. **Garantir acesso** às tools Calendar / Email / GDrive
6. **Image-based responses** — texto/lista vira PNG para WhatsApp
7. **Priorizar qualidade, humanidade, latência SEM aumentar custos** (FinOps)
8. **Cada mudança que afeta custos** deve ser avaliada; discrepante → evitar
9. **Incluir custos estimados** em cada commit
10. **Loop até não haver pendência grave**

## 📍 Estado atual (HEAD = `e82ffbe`)

**Production**: `agents-runtime-test` revision 00237, commit `e82ffbe`
**Suite**: ~675 testes passando. Ruff clean. LGPD OK.

## ✅ Já entregue (sessão 30/07) — 16 commits

| Commit | Fix | Impacto |
|---|---|---|
| `109410f` | Dedup docs | pendências centralizadas |
| `8dce677` | Tick azul cold start | cold 12s vs warm 5s |
| `4883d5a/b8ccf48/95f0260` | RAG keywords + LLM contexto + recent indexing | RAG detecção robusta |
| `a062456` | Scope-aware (1:1+grupo) | "o que é isso?" cross-scope |
| `789f488` | Filename-aware routing | `cdc-portugues-2013.pdf` → retriever |
| `4e01dd9/c3bed1f` | PDF multi-parser + partial | `Stream has ended unexpectedly` |
| `ee977fa` | Max tokens 1500 manager | respostas completas |
| `32a04ef` | Auto-image RAG chunks | tabelas PNG |
| `60ccee6` | Humanização BRT | tom caloroso |
| `bc0e217` | Privacy audit doc | 7 camadas |
| `da6d01b` | FinOps pricing | cost tracking |
| `94aacaf` | ROADMAP.md + STATE consolidado | loop methodology |
| `8710c0e` | Guard sync (-8s warm) | latência |
| **`29c48a0`** | **RAG vector composite indexes** | **resolve Edital.pdf bug** |
| **`e82ffbe`** | **Admin folder permissions fase 1** | **endpoints + storage** |

## 🟡 Pendências por fase

### Fase A — Latência & Custos
**Resolve:** Falta otimizar guard + max_tokens para manager-*

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| A.1 | max_tokens 1000 → 1500 para manager-* (sem mudança em runtime) | ~10% mais em tokens de saída (não em latência) | Médio |
| A.2 | Guard async → sync (substituir LangGraph state machine) | -8s latência warm path | ⭐⭐⭐⭐⭐ |

### Fase B — Imagem em respostas (User pediu: "texto/lista vira PNG")
**Resolve:** Validar e expandir auto-image tabular

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| B.1 | Auditoria cobertura atual (`_detect_tabular_payload`) | zero | ⭐⭐⭐⭐ |
| B.2 | Expandir auto-image para RAG (text chunks) | +1 imagem PNG a cada query RAG (~50ms) | ⭐⭐⭐⭐ |
| B.3 | Auto-image para atas/proactive (atas_worker) | +1 imagem PNG a cada ata | ⭐⭐ |

### Fase C — Humanização
**Resolve:** Tom mais caloroso + clareza visual

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| C.1 | Revisar jennifier system prompt (personalidade) | zero | ⭐⭐⭐ |
| C.2 | Saudações dinâmicas baseadas em BRT | zero | ⭐⭐ |
| C.3 | Emojis apropriados (já presente, validar) | zero | ⭐ |

### Fase D — Privacidade
**Resolve:** Group vs individual isolation + masker

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| D.1 | Audit masker: cobertura PII (CPF/RG/email/tel) | zero | ⭐⭐⭐⭐ |
| D.2 | Group RAG: block non-members | zero | ⭐⭐⭐⭐⭐ (já tem) |
| D.3 | Cross-user leakage check (owner_hash filter) | zero | ⭐⭐⭐⭐ (já tem) |

### Fase E — FinOps & Observabilidade
**Resolve:** Tracking de custo por turno

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| E.1 | Validar métricas tokens_in/out já no observability | zero | ⭐⭐⭐ |
| E.2 | Agregar cost_usd_estimado por turno (DeepSeek $0.14/$0.28 por 1M) | zero | ⭐⭐⭐⭐ |

### Fase F — Validação em Campo + Documentação Final

| Sub | Item | Custo estimado | Valor |
|---|---|---|---|
| F.1 | Smoke test em produção (whatsapp) | zero | ⭐⭐⭐⭐⭐ |
| F.2 | Atualizar STATE.md + ROADMAP | zero | ⭐⭐⭐ |

## 🚦 Critérios de aceite (gate por sub-fase)

- [ ] pytest -q → 0 falhas
- [ ] ruff check → "All checks passed!"
- [ ] mypy → no NEW errors
- [ ] LGPD → passed
- [ ] Build CI/CD SUCCESS
- [ ] /health → commit_sha novo
- [ ] Custo estimado anotado no commit message

## 🚨 Custos estimados por fase

| Fase | Esforço humano | Custo infra / mês | Net change |
|---|---|---|---|
| A.1 max_tokens | 30min | +10% DeepSeek output tokens (~$0.05/mês em workload nominal) | +$0.05/mês |
| A.2 guard sync | 3h | -30% Cloud Run CPU time (~$2/mês) | -$2/mês |
| B.1-B.3 imagem RAG | 4h | +5-10 PNG renders/turno | +$0.30/mês Cloud Run (CPU) |
| C.1-C.3 humanização | 2h | zero | $0 |
| D.1-D.3 privacidade | 2h | zero (auditoria) | $0 |
| E.1-E.2 FinOps | 1h | zero (logging) | $0 |
| F.1-F.2 smoke + docs | 1h | zero | $0 |
| **TOTAL** | **~13h** | | **-~$1.65/mês** |

**Nota FinOps:** todas as mudanças priorizam reduzir latência sem aumentar custo líquido. Guard sync é a única que REDUZ custo. Imagens adicionam custo pequeno mas geram valor humano.

## 🗓️ Cronograma estimado

- Fase A (latência): ~1 dia
- Fase B (imagens): ~1 dia
- Fase C (humanização): ~0.5 dia
- Fase D (privacidade): ~0.5 dia
- Fase E (FinOps): ~0.25 dia
- Fase F (validação): ~0.25 dia

**Total**: ~3-4 dias

## ⏭️ Próximo passo

Executar Fase A.1 (max_tokens) + A.2 (guard sync) e validar.
