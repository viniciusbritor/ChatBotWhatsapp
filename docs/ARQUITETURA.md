# Arquitetura — ChatBotWhatsapp (Agentes Omnichannel)

> Última revisão: **2026-08-05** — unificação de vector stores em `knowledge-database`.
> Chunking com hierarquia jurídica brasileira (Art., §, Capítulo, Seção, Lei).
> Retrieval com expansão de contexto vizinho (`search_with_context`).
> 2 collections core: `knowledge-database` (vector user+grupo) + `message-history` (chat).
> Regra unificada de acesso a conhecimento (RAG vs Drive vs Chat memory)
> documentada em §0.0.4.
> Ver `docs/DIARIO_BORDO.md` para o histórico completo do dia.

## 0. Diagrama visual (ponta a ponta)

```mermaid
flowchart LR
    subgraph USER["Usuario"]
        WA["WhatsApp no celular"]
    end

    subgraph EVO_CLUSTER["Evolution API (projeto EvolutionWhatsapp)"]
        EVO_API["API Evolution (Mongo + WebSocket)"]
    end

    subgraph GCP_PROJECT["GCP Project coherence-ominichannel-fs"]
        EDGE["Cloud Run agents-runtime-test\nmin=0 max=3 cpu-throttling=true"]
        subgraph RUNTIME["Container agents-runtime"]
            WEBHOOK["POST /webhook"]
            PUSH["POST /pubsub/push"]
            ORCH["orchestrator.py (tool loop)"]
            GRAPH["LangGraph StateGraph\njennifier -> classify ->\nguardian -> manager -> reply"]
            JENNIFIER["Jennifer agent (system prompt)"]
            GUARDIAN["access_guardian agent\n(decide owner + OAuth + scopes)"]
            ADMIN["GET/POST /admin/* (Bearer SA)"]
            UI["HTML do modulo Agentes Omnichannel"]
            WHISPER["Whisper local + Gemini STT fallback"]
            EMBED["OpenAI Embeddings (somente ingestao)"]
            SUBF["Tools: calendar/drive/gmail/web/nickname"]
        end

        subgraph PUBSUB["Pub/Sub"]
            TOPIC["chatbotwhatsapp-messages"]
            DLQ["chatbotwhatsapp-dlq (nativa)"]
        end

        subgraph SECRETS["Secret Manager"]
            S_OPENAI["OPENAI_API_KEY"]
            S_EVO["EVOLUTION_API_KEY"]
            S_MINIMAX["MINIMAX_API_KEY"]
            S_GEMINI["GEMINI_API_KEY (LLM fallback + STT)"]
            S_SA["agents-runtime-sa-token"]
        end

        subgraph FIRESTORE["Firestore coherence-ominichannel-fs"]
            LEDGER["message-processing/{id} (ledger)"]
            HISTORY["message-history/{id} (plain)"]
            KNOWLEDGE["agent-knowledge-v2 (Vector)"]
            COLLECTIVE["collective-knowledge-v2 (Vector)"]
            PUBLIC["public-knowledge-v2 (Vector)"]
            ACCOUNTS["whatsapp_accounts/{id}"]
            USERS["usuarios/{phone} (OAuth Google)"]
            NICKNAMES["apelidos_custom/{owner_hash}"]
            AUDIT["audit/* (5y)"]
        end

        subgraph STORAGE["Cloud Storage"]
            GCS["coherence-knowledge-prod (livros/editais)"]
        end

        CLOUD_BUILD["Cloud Build\n(trigger deploy-agents-runtime-test)"]
    end

    WA -- "mensagem" --> EVO_API
    EVO_API -- "POST /webhook (HTTPS)" --> WEBHOOK
    WEBHOOK -- "1. resolve_message_id (deterministico)" --> LEDGER
    WEBHOOK -- "2. ledger.register_or_load()" --> LEDGER
    WEBHOOK -- "3. markMessagesAsRead (async, 5s timeout)" --> EVO_API
    WEBHOOK -- "4. publish chatbotwhatsapp-messages" --> TOPIC
    WEBHOOK -- "200 OK (sem bloquear)" --> EVO_API

    TOPIC -- "push (OIDC validado)" --> PUSH
    PUSH -- "ledger.claim (lease 120s)" --> LEDGER
    PUSH --> ORCH

    ORCH --> GRAPH
    GRAPH --> JENNIFIER
    GRAPH --> GUARDIAN
    GUARDIAN --> ACCOUNTS
    GUARDIAN --> USERS
    GRAPH -- "prefetch Calendar/Email/Drive" --> SUBF
    SUBF --> WHISPER
    SUBF -- "OAuth per-user" --> USERS
    SUBF -- "Calendar/Drive/Gmail" --> USER

    WHISPER -. "OPENAI_API_KEY" .-> S_OPENAI
    EMBED -. "OPENAI_API_KEY (somente ingestao)" .-> S_OPENAI
    JENNIFIER -. "MiniMax M2.7-highspeed -> Gemini 2.5 Flash" .-> S_MINIMAX
    JENNIFIER -. "fallback cascade" .-> S_GEMINI

    ORCH -- "history.write (always, plain)" --> HISTORY
    ORCH -- "history.read (where owner_hash == ...)" --> HISTORY

    ADMIN -- "Bearer SA" --> S_SA
    S_EVO --> EVO_API

    GCS -- "scripts/ingest_owner_knowledge.py" --> KNOWLEDGE
    GCS -- "scripts/ingest_collective_memory.py" --> COLLECTIVE
    KNOWLEDGE -- "search_legal_knowledge (kNN, owner_hash filter)" --> GRAPH
    COLLECTIVE -- "search_collective (kNN, no owner_hash)" --> GRAPH
    PUBLIC -- "search_knowledge (kNN)" --> GRAPH

    UI --> ADMIN
    NICKNAMES --> ORCH

    CLOUD_BUILD -- "git push origin/test" --> EDGE
    EDGE -- "deploy" --> RUNTIME
    AUDIT -- "log_action (5y retencao)" --> RUNTIME

    TOPIC -. "5 tentativas" .-> DLQ
```

### 0.0.0. Knowledge Router (Fase G)

```mermaid
flowchart LR
    WA["WhatsApp: anexo PDF/DOCX/XLSX/text"]
    EVO["Evolution API v2.3.7"]
    WEB["POST /webhook"]
    ORCH["orchestrator"]
    ROUTER["agent-knowledge-router"]
    DET["keywords + MIME"]
    LLM["DeepSeek V4 Flash\n(tie-breaker)"]
    PDF["pdf_handler"]
    DOCX["docx_handler"]
    XLSX["xlsx_handler"]
    TXT["text_handler"]
    DRV["google_drive_saver"]
    RAGI["agent-knowledge-v2"]
    RAGG["group-knowledge-v2"]

    WA --> EVO --> WEB
    WEB --> ORCH
    ORCH --> ROUTER
    ROUTER --> DET
    DET -->|ambiguous| LLM
    DET -->|rag| SK["skill por MIME"]
    DET -->|drive| DRV
    SK --> PDF
    SK --> DOCX
    SK --> XLSX
    SK --> TXT
    LLM --> SK
    LLM --> DRV
    PDF --> RAGI
    DOCX --> RAGI
    XLSX --> RAGI
    TXT --> RAGI
    PDF -. grupo .-> RAGG
    DOCX -. grupo .-> RAGG
    XLSX -. grupo .-> RAGG
    TXT -. grupo .-> RAGG
    DRV --> GDRIVE["Google Drive"]

    classDef ok fill:#d9ead3,stroke:#38761d,color:#000
    class WA,EVO,WEB,ORCH,ROUTER,DET,SK,PDF,DOCX,XLSX,TXT,RAGI,RAGG,DRV,GDRIVE ok
    class LLM fill:#fff2cc,stroke:#bf9000,color:#000
```

### 0.0.1. Knowledge Retriever (Fase H)

```mermaid
flowchart TD
    U["user: pergunta"]
    D{"is_rag?"}
    LLM["DeepSeek V4 Flash tie-breaker"]
    PR["retrieve_private\nagent-knowledge-v2"]
    GR["retrieve_group\ngroup-knowledge-v2"]
    MEM{"user membro?"}
    PEND["pending_action\nshare_private_knowledge_in_group"]
    SHARE["compartilhar citando fonte"]

    U --> D
    D -->|sim| PR
    D -->|nao| NN["resposta normal"]
    D -->|ambiguous| LLM
    LLM -->|rag| PR
    LLM -->|group| GR
    PR -->|tem hits| OK1["retornar trechos"]
    PR -->|zero| GR
    GR --> MEM
    MEM -->|nao| DN["negado"]
    MEM -->|sim| GR2["retornar trechos do grupo"]
    GR -->|tem hits| OK2
    GR -->|zero, mas privado tem| PEND
    PEND --> SHARE
```

### 0.0.2. Knowledge Categorizer + Isolation (Fase F4d.6)

```mermaid
flowchart LR
    PDF["PDF/DOCX/XLSX"]
    EXT["skill.extract"]
    CAT["agent-categorizer\nDeepSeek V4 Flash"]
    TX["texto"]
    CL["{class,group,theme}"]
    IND["index_private_document"]
    VEC["agent-knowledge-v2"]
    USR["user: pergunta"]
    HINT["hints = filename + class"]
    RET["agent-knowledge-retriever\nk=10, score=0.7"]
    CLAR["needs_clarification=True"]
    RESP["resposta citando source_title"]

    PDF --> EXT --> TX
    TX --> CAT --> CL
    CL --> IND
    IND --> VEC
    USR --> HINT --> RET
    VEC --> RET
    RET -->|hits| RESP
    RET -->|zero| CLAR

    classDef ok fill:#d9ead3,stroke:#38761d,color:#000
    classDef armazenado fill:#fff2cc,stroke:#bf9000,color:#000
    classDef novo fill:#cfe2f3,stroke:#1f6feb,color:#000
    class PDF,EXT,TX,CL,IND,USR,HINT,RET,RESP,CLAR novo
    class CAT novo
    class VEC armazenado
```

### 0.0.3. Fluxo de anexos (F4d.5)

```mermaid
flowchart LR
    WA["WhatsApp: PDF/DOCX/XLSX"]
    EVO["Evolution API v2.3.7"]
    WEB["POST /webhook"]
    PUSH["POST /pubsub/push"]
    ACK["_schedule_mark_read (paralelo)"]
    ORCH["orchestrator"]
    HANDLE["_handle_attachment"]
    IND["index_private_document"]
    GRP["index_group_document"]
    DRV["upload_file (Drive)"]

    WA --> EVO --> WEB
    WEB --> PUSH
    WEB --> ACK
    PUSH --> ORCH
    ORCH --> HANDLE
    HANDLE -->|save_to_rag=True, is_group| GRP
    HANDLE -->|save_to_rag=True, individual| IND
    HANDLE -->|save_to_rag=False| DRV

    IND -.->|agent-knowledge-v2| F1["Firestore Vector: owner_hash"]
    GRP -.->|group-knowledge-v2| F2["Firestore Vector: group_hash"]
    DRV -.->|folder_id| F3["Google Drive: raiz do proprietario"]

    classDef ok fill:#d9ead3,stroke:#38761d,color:#000
    classDef warn fill:#fff2cc,stroke:#bf9000,color:#000
    classDef paral fill:#cfe2f3,stroke:#1f6feb,color:#000
    class WA,EVO,WEB,PUSH,ORCH,HANDLE,IND,GRP,DRV,F1,F2,F3 ok
    class ACK paral
```

### 0.0.4. Regra Unificada de Acesso a Conhecimento (31/07/2026)

```mermaid
flowchart TD
    U["user: mensagem"] --> K{"keywords?"}
    K -->|"base de conhecimento,<br/>memorizou, esse documento,<br/>qual arquivo, what did you save"| RAG["agent-knowledge-retriever"]
    K -->|"drive, gdrive, onedrive, dropbox,<br/>salvar no drive, manda pra mim"| DRV["manager-drive + access_guardian"]
    K -->|outras| CHAT["jennifier (LLM) +<br/>message-history plain"]

    RAG --> RAGP{"escopo?"}
    RAGP -->|"privado (1:1)"| RAGP1["agent-knowledge-v2<br/>filtro owner_hash"]
    RAGP -->|"grupo (membro)"| RAGG["group-knowledge-v2<br/>filtro group_hash"]
    RAGP -->|"grupo + sem hits privados"| RAGX["pending_action<br/>share_private_knowledge_in_group"]

    DRV --> DRVG{"escopo?"}
    DRVG -->|"privado (1:1)"| DRVP["manager-drive<br/>+ access_guardian allow"]
    DRVG -->|"grupo + owner confirmou"| DRVG1["manager-drive<br/>+ access_guardian allow"]
    DRVG -->|"grupo + owner NAO confirmou<br/>OR membro NAO confirmado"| DRVX["pending_action<br/>group_consent (TTL 300s)"]

    CHAT --> MEM["message-history/{id}<br/>Firestore plain, owner_hash"]

    classDef rag fill:#d9ead3,stroke:#38761d,color:#000
    classDef drive fill:#fff2cc,stroke:#bf9000,color:#000
    classDef chat fill:#cfe2f3,stroke:#1f6feb,color:#000
    classDef pend fill:#f4cccc,stroke:#cc0000,color:#000
    class RAG,RAGP,RAGP1,RAGG rag
    class DRV,DRVG,DRVP,DRVG1 drive
    class CHAT,MEM chat
    class RAGX,DRVX pend
```

**Como funciona**: a cada turno, o `orchestrator.py::_detect_intent()`
aplica 3 listas de keywords (estritas, pós-patch 31/07/2026) e marca
`is_rag`, `is_drive` ou nenhum dos dois. O `_resolve_agents_for_intents`
decide o agente; o `access_guardian` valida owner+OAuth+scopes quando
envolve Google (Drive/Gmail/Calendar).

| Camada | Trigger | Storage | Agente |
|---|---|---|---|
| **RAG** | "base de conhecimento", "memorizou", "esse documento", "qual arquivo", "knowledge base", "vc guardou" | `agent-knowledge-v2` (1:1, `owner_hash`) ou `group-knowledge-v2` (grupo, `group_hash`) | `agent-knowledge-retriever` |
| **Drive** | "drive", "gdrive", "onedrive", "dropbox", "salvar no drive", "manda pra mim", "guarda no drive" | Google Drive via OAuth per-user | `manager-drive` + `access_guardian` |
| **Chat memory** | qualquer outra mensagem (saudação, comandos, status, agente info) | `message-history` (Firestore **plain**, sem embedding) | `jennifier` (LLM direto) |

**No grupo (regra de consent)**:
- RAG do grupo = `group-knowledge-v2`, filtro `group_hash`. Acesso
  negado se o telefone não for membro do grupo.
- Drive/Gmail/Calendar **pessoais** em grupo = `pending_action
  group_consent` (TTL 300s) antes de devolver conteúdo. Membro
  confirmado segue direto.
- Drive do **grupo** (pasta dedicada) = escopo compartilhado, sem
  consent adicional.

**Keyword patch (31/07/2026)**: `orchestrator.DRIVE_KEYWORDS` foi
estreitado para conter **apenas** nomes de serviço de storage
(`drive`, `gdrive`, `onedrive`, `dropbox`, `google drive`, `meu drive`,
`no drive`, `salvar no drive`, `manda pra mim`, etc.) e expressões
que **explicitam** o destino Drive (`dentro desse drive`, `nesse
drive`, `lista os arquivos do drive`). Tokens genéricos
(`documento`, `pdf`, `docx`, `xlsx`, `ata`, `arquivo`, `pasta`,
`planilha`, `relatorio`, `minuta`, `upload`) ficaram em
`DRIVE_KEYWORDS_REMOVED` (não usados) e continuam cobertos pelo
`attachment_save_kw` / `attachment_file_kw` quando o handler de
anexo é acionado. Resultado: queries como "quais documentos você
tem na sua base de conhecimento?" agora acertam `is_rag=True` em
vez de cair em `manager-drive`.



```mermaid
flowchart LR
    START([inbound turn]) --> J["jennifier_node\n(identity)"]
    J --> C["classify_intent_node\n(detect calendar/email/drive)"]
    C --> G["guard_node\n(access_guardian.decide_guardian)"]
    G -- "verdict=allow" --> M["manager_node\n(_prefetch_calendar/email/drive)"]
    G -- "verdict=request_oauth" --> R["reply_node\n(link OAuth)"]
    G -- "verdict=deny" --> R
    M --> R
    R --> END([reply enviado ao WhatsApp])
```

### 0.1. Caminho do webhook em sequência (numerada no diagrama)

| Passo | Onde | O que acontece |
| --- | --- | --- |
| 1 | `webhook` | Resolve `message_id` determinístico (ou usa o do Evolution). |
| 2 | `webhook` | `ledger.register_or_load` — idempotência transacional no Firestore. |
| 3 | `webhook` | `markMessagesAsRead` na Evolution v2 (timeout 5 s, async — não bloqueia o webhook). |
| 4 | `webhook` | Publica em `chatbotwhatsapp-messages` e devolve `200 OK` imediatamente. |
| 5 | `push` | `ledger.claim` — pega lease de 120 s. |
| 6 | `orchestrator` | Detecta intenção, escolhe agente principal, prefetch Calendar/Email/Drive. |
| 7 | `access_guardian` | Subagente do grafo LangGraph que valida owner (`phone == owner_phone` da instância) + token OAuth per-user + scopes Google (`drive.read` / `drive.write` / `calendar` / `gmail`). Em grupo, pessoal (`is_drive`/`is_email`/`is_calendar`) de owner não confirmado dispara `pending_action group_consent` (TTL 300 s). |
| 8 | `orchestrator` | Persistência plain (`message-history/{id}`) com `owner_hash` derivado. |
| 9 | `orchestrator` | LLM único DeepSeek V4 Flash via DeepAgents (harness LangGraph). Mascaramento PII. |
| 10 | `pubsub` | `send_text` na Evolution → resposta + tick azul. |
| 11 | `pubsub` | `mark_delivered` no ledger. |

### 0.2. Mapa de Firestore

```
coherence-ominichannel-fs
├── agents/                      # configuracao (Carregada pelo agent_loader)
├── skills/
├── tools/
├── config/
├── whatsapp_accounts/{id}/      # 1 doc por instancia Evolution
├── usuarios/{phone}/            # OAuth Google + identidade do proprietario
├── apelidos_custom/{owner_hash}
├── audit/                        # 5 anos de retencao (LGPD Art. 37)
├── message-processing/{id}/      # ledger Pub/Sub (TTL 7 dias)
├── message-history/{id}/         # historico de chat (FIRESTORE PLAIN)
├── knowledge-database/           # Firestore Vector unificado (1536d)
│   ├── scope="private" + owner_hash  → conhecimento individual
│   └── scope="group"   + group_hash  → conhecimento de grupo WhatsApp
└── pending-actions/              # confirmacoes pendentes (TTL 300s)
```

### 0.3. Inventário de Agentes (18 agentes + 2 resolvers)

> Última atualização: **05/08/2026** — reclassificação com cores de status.

| Cor | Significado |
|---|---|
| 🟢 Verde | Mais usados, funcionando (diários) |
| 🟡 Amarelo | Menos usados, funcionando (ocasionais) |
| 🟠 Laranja | Nunca usados, funcionando (background/interno) |
| 🔴 Vermelho | Com problema (deploy bloqueado) |

#### 🟢 Em uso diário (7)

| Agente | Tipo | Disparado por |
|---|---|---|
| `jennifier` | Orchestrator | Toda mensagem (fallback) |
| `agent-knowledge-retriever` | Sub-agente | Query "base de conhecimento" |
| `agent-categorizer` | Sub-agente | Todo anexo ingerido (PDF/DOCX/XLSX) |
| `manager-calendar` | Deep Agent | Keywords: agenda, reunião, evento |
| `manager-email` | Deep Agent | Keywords: email, inbox, gmail |
| `manager-drive` | Deep Agent | Keywords: drive, pasta, upload |
| `access-guardian` | Determinístico | Antes de toda tool Google (OAuth+scopes) |

#### 🟡 Uso ocasional (9)

| Agente | Tipo | Disparado por |
|---|---|---|
| `agent-intimacy` | Specialist | "me chame de", "meu apelido" |
| `agent-learning` | Specialist | "na verdade", "errado" |
| `manager-web` | Deep Agent | "pesquisar", "buscar na internet" |
| `agent-locomocao` | Specialist | "uber", "rota", "onde fica" |
| `agent-youtube` | Specialist | "youtube", "video", "tutorial" |
| `agent-morality` | Specialist | Keywords de agressão |
| `agent-group-rag` | Deep Agent | Anexo em grupo WhatsApp |
| `agent-rag` (legacy) | Specialist | Superseded pelo knowledge-retriever |
| `doc-disambiguator` | Pipeline | RAG vs Drive ambíguo |

#### 🟠 Background / Interno (5)

| Agente | Tipo | Função |
|---|---|---|
| `ata-generator` | Worker | Gera ata de reunião pós-evento |
| `agent-proatividade` | Worker | Lembretes e follow-ups |
| `group-resolver` | Interno | Mapeia grupo WhatsApp → pasta Drive |
| `agent-privacy-guard` | Interno | Bloqueia dados pessoais em grupo |
| `source_title_resolver` | LLM Resolver | 🔧 NOVO (Opção D) — match semântico de documentos via LLM |

#### 🔴 Com problema (0 — resolvido em 05/08/2026)

| Item | Status |
|---|---|
| ~~Esteira CI/CD quebrada~~ | ✅ Corrigido (`cf09d94`) |
| ~~Índice source_title_full~~ | ✅ Definido no cloudbuild |
| ~~Fases 1-5 não deployadas~~ | ✅ Em deploy (`cf09d94`) |

```mermaid
graph TB
    subgraph GREEN["🟢 Uso diario"]
        J["jennifier"]
        RET["knowledge-retriever"]
        CAT["categorizer"]
        CAL["manager-calendar"]
        EML["manager-email"]
        DRV["manager-drive"]
        ACC["access-guardian"]
    end
    subgraph YELLOW["🟡 Uso ocasional"]
        INT["intimacy"]
        LRN["learning"]
        WEB["manager-web"]
        LOC["locomocao"]
        YT["youtube"]
        MOR["morality"]
        GRP["group-rag"]
        RAG["agent-rag (legacy)"]
        DIS["doc-disambiguator"]
    end
    subgraph ORANGE["🟠 Background/Interno"]
        ATA["ata-generator"]
        PRO["proatividade"]
        GRS["group-resolver"]
        PRV["privacy-guard"]
        SRC["source_title_resolver ⟮NOVO⟯"]
    end
    J --> RET
    J --> CAT
    J --> CAL
    J --> EML
    J --> DRV
    J --> ACC
    J --> INT
    J --> LRN
    J --> WEB
    J --> LOC
    J --> YT
    J --> MOR
    J --> GRP
    J --> RAG
    RET --> SRC
    GRP --> DRV
    GRS --> DRV
```

## 1. Objetivo

Um único runtime FastAPI (`agents-runtime`) responde a mensagens do
WhatsApp via Evolution API, orquestra capacidades por agente
(configuração em Firestore) usando um **grafo LangGraph** onde Jennifer
é o agente mestre e `access_guardian` é o subagente que decide
autorização de Gmail/Drive/Calendar. Toda leitura vetorial é filtrada
por `owner_hash` e o histórico de chat é mantido em Firestore plain.
A documentação oficial é **somente esta pasta `docs/` na raiz**; cópias
em `agents_runtime/docs/` foram removidas em 22/07/2026.

## 2. Stack

- **Linguagem**: Python 3.12 (imagem `python:3.12-slim`).
- **Framework**: FastAPI 0.115 + Uvicorn.
- **Mensageria**: Pub/Sub (`chatbotwhatsapp-messages` + DLQ nativa
  `chatbotwhatsapp-dlq`).
- **Persistência**: Firestore (collections canônicas acima) + GCS para
  arquivos-fonte da base de conhecimento.
- **Embeddings**: OpenAI `text-embedding-3-small` (1536d), collection
  `knowledge-database`.
- **Orquestração**: dispatch procedural em `orchestrator.py` (flat,
  pipeline-based). Jennifer → `access_guardian` → manager → reply.
- **LLM**: DeepSeek V4 Flash (único provedor desde Fase N).
- **STT**: Whisper local (`faster-whisper`, `base/int8`). Fallback
  controlado para Gemini 2.5 Flash apenas em falha técnica do Whisper
  **e** com consentimento explícito.
- **Chunking**: `_chunk_text_semantic()` com detecção de hierarquia
  jurídica brasileira — Lei, Título, Capítulo, Seção, Art., §, Inciso.
- **TTS / tick azul**: `markMessagesAsRead` (Evolution v2) automático
  em cada webhook válido.
- **Segredos**: Google Secret Manager, projeto
  `coherence-ominichannel-fs`.

## 3. Topologia

```mermaid
flowchart LR
    WA["WhatsApp"] --> EVO["Evolution API"]
    EVO --> WEB["Cloud Run único: /webhook"]
    WEB --> LEDGER[("Firestore: message-processing")]
    WEB --> PS["Pub/Sub chatbotwhatsapp-messages"]
    PS --> PUSH["Mesmo Cloud Run: /pubsub/push"]
    PUSH --> ORCH["Jennifer orchestrator"]
    ORCH --> TOOLS["Capacidades Gmail/Drive/Calendar + RAG"]
    TOOLS --> VECT[("Firestore Vector por owner")]
    ORCH --> EVO
    ORCH --> PORTAL["Coherence Portal (UI Agentes Omnichannel)"]
    PORTAL -->|"Authorization: Bearer ou Firebase"| WEB
    SECRETS["Secret Manager"] --> WEB
```

## 4. Componentes

| Componente | Responsabilidade |
| --- | --- |
| `main.py` | FastAPI, lifecycle, endpoints `/webhook`, `/pubsub/push`, `/chat`, `/admin/*`. |
| `orchestrator.py` | Detecção de intenção (RAG / Drive / Calendar / Email / Chat), roteamento para capabilities, prefetch Calendar/Email/Drive, indexação RAG, integração com `_run_guard_graph`. Keywords de Drive são estritas (Fase 31/07/2026). |
| `agent_orchestration/jennifier.py` | Definição do agente mestre Jennifer (system prompt, personalidade levemente irônica, modelo único DeepSeek V4 Flash). |
| `agent_orchestration/access_guardian.py` | Decisão determinística de owner + OAuth + scopes (`decide_guardian`). É o subagente do grafo que roda **antes** de qualquer tool Google. |
| `agent_orchestration/graph.py` | Grafo LangGraph `StateGraph`: jennifier → classify → guardian → manager → reply. Classificação de intent com tie-breaker LLM. |
| `agent_orchestration/knowledge_router.py` | (Fase G) Decide skill de memória do anexo (PDF, DOCX, XLSX, text, drive) por MIME + keywords + tie-breaker DeepSeek V4 Flash. |
| `agent_orchestration/knowledge_retriever.py` | (Fase H) Decide tema RAG (scope privado vs grupo), aplica escopo, retorna chunks acima de `RAG_RETRIEVE_MIN_SCORE` (default 0.7). Cruzar privado → grupo cria `pending_action share_private_knowledge_in_group`. |
| `agent_orchestration/categorizer.py` | (Fase F4d.6) Classifica cada anexo em `{class, group, theme}` via DeepSeek V4 Flash antes da persistência. Fallback heurístico sem LLM. |
| `agent_loader.py` | Polling 120 s para `agents`, `skills`, `tools` e snapshot atômico. |
| `core.message_ledger` | Ledger Firestore para idempotência transacional de mensagens. |
| `core.pubsub_dispatcher` | Lease, retry-control e terminalidade por mensagem. |
| `core.evolution_client` | `send_text` e `mark_messages_read` na Evolution v2. |
| `core.audio_transcribe` | Wrapper Whisper com fallback controlado para Gemini 2.5 Flash. |
| `core.owner` | Resolução do proprietário da instância Evolution. |
| `tools/google_*` | Integrações Google com escopos mínimos. A checagem de owner foi centralizada no `access_guardian` (Fase H). Decorador legada `@_owner_guard` removida. |
| `core.rag` | Embeddings OpenAI e busca vetorial filtrada por `owner_hash`. |
| `core.module_ui` | Plano de controle HTML renderizado em `/admin/dashboard`. |
| `scripts/ingest_owner_knowledge.py` | Ingestão de livros/editais em GCS para a coleção do proprietário. |

## 5. Fluxo da mensagem

```mermaid
sequenceDiagram
    participant Evo as Evolution API
    participant Hook as /webhook
    participant Ledger as Firestore ledger
    participant PS as Pub/Sub
    participant Push as /pubsub/push
    participant Orch as Orchestrator
    participant Tools as Capabilities
    Evo->>Hook: POST {MESSAGES_UPSERT}
    Hook->>Ledger: register_or_load(message_id)
    Ledger-->>Hook: snapshot
    Hook-->>Evo: POST markMessagesAsRead (async)
    Hook->>PS: publish(envelope)
    Hook-->>Evo: 200 OK
    PS->>Push: push delivery
    Push->>Ledger: claim(message_id)
    Push->>Orch: orchestrate(envelope)
    Orch->>Tools: Google/RAG/HTTP
    Tools-->>Orch: result
    Orch-->>Push: reply
    Push->>Evo: sendText(remote_jid, reply)
    Push->>Ledger: mark_delivered
```

A entrega da resposta é registrada no ledger; Pub/Sub só reentrega se a
instância sinaliza 503 (falha transitória). Falhas terminais são marcadas e o
Pub/Sub descarta após o número configurado de tentativas.

## 6. Coleções Firestore

Camadas:

### Mensageria e controle
- `message-processing/{message_id}` — ledger de idempotência por mensagem (TTL 7 dias).
- `audit/*` — trilha de auditoria.
- `whatsapp_accounts/{account_id}` — vínculo entre `instance`, `owner_phone`, `owner_uid`.
- `usuarios/{phone}` — tokens OAuth Google do proprietário (refresh automático).

### Histórico do chat (Firestore **plain**, sem embedding)
- `message-history/{history_id}` — todas as interações (`owner_hash` +
  `message_id` + `text_masked` + `conversation_id` + `direction` +
  `created_at` + `agent_id`). Filename explícito: conversas **nunca** vão
  para o Firestore Vector. A coleção `conversation-memory-v2` (vetorial)
  está marcada como **legada** e não é mais alimentada pelo runtime.

### Base de conhecimento (Firestore Vector, embeddings OpenAI)
- `agent-knowledge-v2` — livros/editais por proprietário (`owner_hash`).
  Escopo **privado** (1:1). Toda leitura filtra `owner_hash == owner_id(inbound)`.
- `group-knowledge-v2` — memórias de grupo (`group_hash`). Escopo
  **compartilhado** dentro de um WhatsApp group. Acesso negado se o
  telefone não constar em `grupos/{jid}/membros/{phone}` com `is_active`.
  Cruzar source privada → grupo exige `pending_action
  share_private_knowledge_in_group` (TTL 300 s).
- `collective-knowledge-v2` — memórias coletivas configuradas pelo
  operador via `scripts/ingest_collective_memory.py`.
- `public-knowledge-v2` — base pública sem `owner_hash`.

**Regra de acesso (31/07/2026)**: a base de conhecimento RAG é o destino
default do user quando ele menciona "base de conhecimento", "memorizou",
"qual arquivo", "esse documento" etc. (`agent-knowledge-retriever`). Não
vai para Drive nem responde com Google. Ver §0.0.4.

**Retrieval adaptive floor (31/07 v2)**: embeddings OpenAI 1536d em
chunks do `reindex_golden_set.py` (CDC/LGPD/Higiene, ~3KB) costumam
ter cosine similarity 0.4-0.65. O threshold `RAG_RETRIEVE_MIN_SCORE=0.7`
era alto demais e truncava queries legítimas para 0 hits. Fix:
`core/rag.py::search_legal_knowledge` aplica `ADAPTIVE_FLOOR=0.3` —
matches entre 0.3 e o `min_score` são entregues com warning
`retrieval_low_confidence`. Abaixo de 0.3 ainda são descartados.
Quando TODOS os candidates têm score < 0.3, log estruturado
`retrieval_zero_hits` salva top-3 preview com snippet.

**UX da `clarification_prompt` (31/07 v2)**: a mensagem retornada
quando retrieval é zero agora lista `source_title` conhecidos do
owner. `scripts/diag_rag_query.py` é o helper de diagnóstico
(read-only, manual).

### Configuração carregada pelo `agent_loader`
- `agents`, `skills`, `tools`, `config/*`.
- `apelidos_custom/{owner_hash}` — consentimento de apelidos.

Regras de isolamento:

- Toda leitura vetorial (`agent-knowledge-v2`, `collective-knowledge-v2`)
  filtra `owner_hash == owner_hash(inbound)`. A coleção pública não
  recebe `owner_hash`.
- Toda leitura em `message-history` filtra
  `where("owner_hash", "==", _owner_hash(phone))` antes de ordenar por
  `created_at` desc.
- Quando o `phone` chega vazio (caso de grupo sem sender identificável),
  a interação é **ignorada** com `status: skipped, reason: missing_phone`
  para evitar mistura entre contas.
- Gmail/Drive/Calendar requerem que o telefone do remetente coincida com o
  `owner_phone` da conta Evolution; tool retorna
  `owner_only_capability` caso contrário.

## 7. Módulo `Agentes Omnichannel` (plano de controle)

Continua dentro do `agents-runtime` em `/admin/dashboard`. Agora:

- Não depende mais de tokens em query string. Aceita `Authorization: Bearer`
  ou Firebase ID token; o bearer é refletido na página apenas para evitar que
  o frontend fique sem credencial em interações locais.
- Mantém abas: **Contas WhatsApp**, **Agentes**, **Skills**, **Tools**,
  **Proprietários**, **Conhecimento**, **Status**.
- Tools são somente leitura no Firestore — a implementação executável continua
  versionada em código.

## 8. Áudio

- Whisper local em `tools/audio_transcribe.py`. Warm-up assíncrono no startup.
- Download valida host, MIME, tamanho (25 MB), duração (5 min) e ausência de
  redirecionamento.
- Em falha técnica (`RuntimeError`, `MemoryError`, timeout) o `core/audio_transcribe`
  aciona o fallback Gemini 2.5 Flash **apenas** se houver consentimento
  registrado (`STT_FALLBACK_CONSENT=true` ou `audio_consent_external=true`).
- Limite diário: 20 chamadas (configurável via `STT_FALLBACK_DAILY_LIMIT`).
- Áudio bruto nunca é persistido; arquivos temporários são apagados em
  `finally` e a transcrição é mascarada antes de chegar ao LLM ou ao vetor.

## 9. Custos e limites

- Cascade LLM com MiniMax M2.7 Highspeed como entrada minimiza tokens.
- Limite diário de fallback Gemini (20/dia) impede surpresas de billing.
- Pub/Sub: idempotência garantida pelo ledger evita a antiga tempestade de 44k
  requisições/dia.
- Firestore Vector: retém coleções por 90 dias (`RETENTION_DAYS`).

## 10. Conformidade

- LGPD: `scripts/check_lgpd_compliance.py` roda no CI e valida `LGPD.md`,
  `TERMOS.md`, snippets obrigatórios, Dockerfile.
- Tokens OAuth são persistidos sem `client_secret` no documento (strip no
  `oauth_per_user._persist_token`).
- Auditoria registra `actor`, `action`, `target`, `phone_hash` (truncado).
- Retenção de logs 5 anos (LGPD Art. 37).

## 11. Pendências conhecidas

> Lista autoritativa de pendências (ativas + histórico) vive em
> [`STATE.md`](../STATE.md) na raiz do repo, atualizado a cada sessão.
> Itens resolvidos e datas de fechamento estão lá.
>
> Itens remanescentes nesta versão (30/07/2026):
> - RAG backfill de embeddings legados sob o antigo `_owner_hash(phone)` —
>   trackado em STATE.md.
> - `agents_runtime/README.md` menciona contagens antigas — trackado em STATE.md.
>
> Item resolvido desde o commit desta versão: WhatsappAgente + service
> legado (`agents-runtime-prod` pausado, repo deletado).