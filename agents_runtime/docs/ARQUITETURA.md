# Arquitetura — agents_runtime

> Servico principal do modulo `omnichannel-agentes`. Stack: Python 3.12 + FastAPI + Agno + Firestore.

> **Documento mestre do projeto:** [`ChatBotWhatsapp/docs/PLAN_OMNICHANNEL_AGENTES.md`](../../PLAN_OMNICHANNEL_AGENTES.md)
> **Contrato Portal:** [`Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md`](../../../Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md)

## Visao Geral

`agents_runtime` e um servico Cloud Run que:
- Recebe mensagens WhatsApp do `WhatsappAgente` (thin proxy)
- Executa cascata LLM (DeepSeek → NVIDIA → MiniMax)
- Aplica escalation automatica Flash → Pro
- Chama tools pre-registradas (Calendar, Drive, Gmail, Web, Audio, RAG)
- Aplica LGPD masker antes de qualquer chamada LLM
- Retorna response com `delay_ms` calculado para typing effect

## Componentes Principais

| Componente | Funcao |
|---|---|
| `main.py` | FastAPI app, rotas `/healthz`, `/chat`, `/proactive/send`, `/admin/*` |
| `core/auth.py` | Middleware SA token |
| `core/secrets.py` | Resolucao de secrets (env → Secret Manager → default) |
| `core/llm_provider.py` | Cascata DeepSeek → NVIDIA → MiniMax |
| `core/escalation.py` | Heuristica Flash → Pro |
| `core/masker.py` | LGPD PII masker |
| `core/delay_calculator.py` | Typing effect |
| `core/proactive_gate.py` | 8 camadas anti-spam |
| `core/rag.py` | MiniMax embeddings + Firestore Vector |
| `tools/*.py` | Tools pre-registradas |

## Fluxo de Mensagem

```
POST /chat
  → auth (Bearer SA)
  → orchestrator (Fase 3)
  → masker
  → LLM cascade
  → escalation check
  → response + delay_ms
```

## Topologia Cloud Run

- **Service:** `agents-runtime-test`
- **Region:** `us-central1`
- **CPU:** 2
- **Memory:** 2Gi
- **Min instances:** 0
- **Max instances:** 3
- **CPU boost:** habilitado
- **Cold start:** 5-15s (mitigado por ping Cloud Scheduler 5min)

## Estado: Fase 1 (Fundacao)

Em construcao. Componentes ja implementados:
- main.py (skeleton)
- core/auth.py
- core/secrets.py
- core/llm_provider.py
- core/escalation.py
- core/masker.py
- core/delay_calculator.py