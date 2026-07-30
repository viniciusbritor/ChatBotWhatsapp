# ROADMAP.md — Roadmap de Longo Prazo (30/07/2026)

> Documento vivo. Itens finalizados vão para `STATE.md`.
> Fonte autoritativa de pendências: [`STATE.md`](./STATE.md)
> Plano operacional atual: [`CURRENT_PLAN.md`](./CURRENT_PLAN.md)

## 🎯 Visão

Chatbot WhatsApp único, humano-latência, humano-forma, FinOps consciente. Privacy-by-design (1:1 + grupo), RAG-first para conhecimento memorizado, tools Google (calendar/email/drive), imagens para conteúdo tabular.

## 📍 Onde estamos (30/07/2026)

| Dimensão | Status | Cobertura |
|---|---|---|
| RAG simples / recente indexing | ✅ | Testes 17/17 |
| Tick azul cold start | ✅ (parcial — Evolution pode ter limit) | Logs mostram 201 OK |
| Filename-aware routing | ✅ | Testes 6/6 |
| PDF extraction (fallback + partial) | ✅ | Testes 11/11 |
| Image-based responses (Drive/Gmail/Calendar/RAG) | ✅ | Testes 10/10 |
| Humanização (sazionalidade BRT + tom caloroso) | ✅ | Testes 24/24 |
| Privacy (masker + group isolation + OAuth) | ✅ | Audit doc |
| FinOps (cost_usd_estimated no tracker) | ✅ | Testes 9/9 |

## 🟡 Próximas fases (em ordem de valor)

### Próxima: Latência — guard sync (Fase A.2)

**Resolve:** Latência warm path cai ~8s ao substituir LangGraph state machine por função sync.

**Esforço:** 3h | **Risco:** médio (afeta logica central) | **Custo:** **-$2/mês** (menos CPU time)

**Tasks:**
1. Medir latência baseline atual warm path
2. Identificar _run_guard_graph onde é sync-equivalente
3. Refatorar para função pura (sem LangGraph overhead)
4. Manter compatibilidade com agent_loader + access_guardian
5. Testes de regressão latência (warm path <4s)

### Depois: Streaming SSE (Fase 3)

**Resolve:** Resposta "chega antes" para o user.

**Esforço:** 1 semana | **Risco:** médio | **Custo:** +$0.50/mês (bandwidth)

### Depois: RAG Híbrido (Fase 6)

**Resolve:** Busca semântica + BM25 keyword fallback. Melhora recall em queries técnicas.

**Esforço:** 6 semanas | **Risco:** alto (nova infra) | **Custo:** +$5/mês (indexação keyword)

### Pendências externas (não-críticas)

| Item | Bloqueio | Janela |
|---|---|---|
| Rotação credenciais `ad6399a` | Usuário precisa adicionar nova key | Quando quiser |
| Drive scope rollback | Re-consentimento | Próxima janela |
| OAuth Client Console config | Setup manual | Quando user quiser |
| Backfill embeddings legacy | Script `scripts/backfill_owner_hash_embeddings.py` | Fase 5 |
| README desatualizado (contagens) | Refresh após estabilizar | Após Fase 0.5+ |

## ⚠️ Cronograma estimado

- **Curto prazo (2-4 semanas):** A.2 guard sync + image refinement + streaming
- **Médio prazo (2-3 meses):** Fase 6 RAG otimizado + Fase 2 cache LRU + Fase 4 orchestrator split
- **Longo prazo (6+ meses):** Domain embeddings, multi-document synthesis, finetuning se justificado

## 🔄 Loop methodology

Cada iteração segue:
1. **Avaliar** pendências graves (STATE.md + user feedback)
2. **Criar plano** em fases (CURRENT_PLAN.md)
3. **Documentar** o plano (este arquivo + commit message)
4. **Executar** cada fase com gates (pytest, ruff, mypy, LGPD, build SUCCESS)
5. **Documentar** tudo (CURRENT_PLAN.md atualizado, STATE.md)
6. **Repetir** se houver pendência grave remanescente

## 🛟 Rollback strategy

Cada commit = deploy isolado. `git revert <sha> && git push origin test` = rollback em ~5min via trigger 2nd-gen.

---

**Última atualização:** 30/07/2026 04:00 BRT
**Próxima iteração:** após smoke test em produção das Fases A-E deployadas hoje.
