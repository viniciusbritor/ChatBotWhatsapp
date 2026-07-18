# Arquitetura — agents_runtime

> Servico principal do modulo `omnichannel-agentes`. Stack: Python 3.12 + FastAPI + Firestore.

> **Documento mestre do projeto:** [`ChatBotWhatsapp/docs/PLAN_OMNICHANNEL_AGENTES.md`](../../PLAN_OMNICHANNEL_AGENTES.md)
> **Contrato Portal:** [`Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md`](../../../Coherence_Portal/docs/MODULE_INTEGRATION_AGENTES.md)

## Visao Geral

`agents_runtime` e um servico Cloud Run que:
- Recebe mensagens WhatsApp do `WhatsappAgente` (thin proxy)
- Executa cascata LLM (MiniMax M2.7 Highspeed → MiniMax M3 → DeepSeek)
- Aplica escalation automatica por heuristica
- Chama tools pre-registradas (Calendar, Drive, Gmail, Web, Audio, RAG)
- Aplica LGPD masker antes de qualquer chamada LLM
- Retorna response com `delay_ms` calculado para typing effect

## Componentes Principais

| Componente | Funcao |
|---|---|
| `main.py` | FastAPI app, rotas `/healthz`, `/chat`, `/proactive/send`, `/admin/*` |
| `core/auth.py` | Middleware SA token |
| `core/secrets.py` | Resolucao de secrets (env → Secret Manager → default) |
| `core/llm_provider.py` | Cascata MiniMax → DeepSeek, sem Gemini |
| `core/escalation.py` | Heuristica Flash → Pro |
| `core/masker.py` | LGPD PII masker |
| `core/delay_calculator.py` | Typing effect |
| `core/proactive_gate.py` | 8 camadas anti-spam |
| `core/rag.py` | MiniMax embo-01 1536d + Firestore Vector v2 |
| `core/agent_status.py` | Inventario operacional deterministico dos agentes |
| `tools/*.py` | Tools pre-registradas |

## Inventario e identidade operacional

`core/agent_status.py` e a fonte unica para chat e endpoints administrativos. O inventario diferencia configuracao, reload, roteabilidade, tools, provider, readiness por usuario, saude recente e execucoes em andamento.

Perguntas de status usam rota deterministica `runtime-status`. Managers permanecem internos e toda resposta externa declara `response_identity=Jennifer`. Regras de web exigem pedido externo explicito; frases genericas como "o que eles fazem" nao ativam `manager-web`.

Confirmacoes curtas consultam `pending-actions/{owner_hash}` com TTL. O cache final e usado somente como idempotencia por `message_id`, instancia e conversa.

## Audio local

`tools/audio_transcribe.py` encapsula faster-whisper. `audio_base64` e o formato canonico recebido do WhatsappAgente. `audio_url` existe apenas como fallback HTTPS com allowlist de hosts, validacao DNS contra redes privadas, limite de bytes, timeout e validacao de duracao por ffprobe.

O modelo Whisper e carregado em background no startup e prebaixado na imagem. A transcricao passa pelo masker antes do orchestrator. Falhas retornam resposta amigavel sem chamar Gemini e sem registrar conteudo de audio ou texto cru.

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

## Estado: Fases corretivas 3, 4 e 5 concluidas

Componentes validados localmente em 18/07/2026:

- Firestore Vector v2 com 16 testes especificos.
- Inventario e orquestracao com 41 testes especificos.
- Audio Whisper local com 30 testes especificos.
- Suite completa: 212 passed, 9 skipped.
- Deploy, reindexacao GCP e smoke WhatsApp real nao executados nesta sessao.