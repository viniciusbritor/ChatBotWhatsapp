```mermaid
flowchart TB
    subgraph USER["Usuário"]
        WA["WhatsApp no celular"]
    end

    subgraph EVO["Evolution API (projeto EvolutionWhatsapp)"]
        EVO_API["API Evolution\n(Mongo + WebSocket)"]
    end

    subgraph GCP["GCP Project coherence-ominichannel-fs"]
        WEBHOOK["POST /webhook\n(agents-runtime-test)"]

        subgraph ORCH["orchestrator.py"]
            DETECT["_detect_intent()"]
            GUARD["_run_guard_graph()"]
            EXEC["_execute_agent()"]
        end

        subgraph GRAPH["agent_orchestration/graph.py\n(LangGraph StateGraph)"]
            J["jennifier_node"]
            CI["classify_intent_node"]
            GD["guard_node\n(access_guardian.py)"]
            MG["manager_node"]
            RL["reply_node"]
        end

        subgraph DEEP["deepagent_layer/"]
            DTOOLS["tools.py\n(LangChain @tool wrappers)"]
            DAGENTS["agents.py\n(create_deep_agent)"]
            LADAPT["langchain_adapter/\n(wrapper estável)"]
        end

        subgraph TOOLS["tools/ (código puro, sem LangChain)"]
            TGMAIL["google_gmail.py\n@_owner_guard"]
            TCAL["google_calendar.py\n@_owner_guard"]
            TDRIVE["google_drive.py\n@_owner_guard"]
            TWEB["web_search.py"]
        end

        LLM["ChatOpenAI(\n  model='deepseek-v4-flash',\n  base_url='https://api.deepseek.com/v1'\n)"]

        subgraph SUB["Subprocessos / Jobs"]
            ATAW["ata_worker/main.py\n(deepseek-v4-pro)"]
            PROW["proactive_worker/main.py\n(deepseek-v4-flash)"]
        end

        subgraph FS["Firestore coherence-ominichannel-fs"]
            AGENTS["agents/"]
            SKILLS["skills/"]
            TOOLS_CFG["tools/"]
            WHATSAPP_ACCOUNTS["whatsapp_accounts/\n(owner_phone)"]
            USERS["usuarios/{phone}\n(google_oauth_token)"]
            NICKNAMES["apelidos_custom/"]
            LEDGER["message-processing/{id}\n(idempotência)"]
            HISTORY["message-history/{id}\n(owner_hash)"]
            KNOWLEDGE["agent-knowledge-v2 (Vector)"]
            COLLECTIVE["collective-knowledge-v2"]
            PUBLIC["public-knowledge-v2"]
            AUDIT["audit/* (5y)"]
        end

        subgraph SEC["Secret Manager"]
            S_OPENAI["OPENAI_API_KEY"]
            S_EVO["EVOLUTION_API_KEY"]
            S_DEEPSEEK["DEEPSEEK_API_KEY"]
            S_GEMINI["GEMINI_API_KEY\n(STT only)"]
            S_SERPER["SERPER_API_KEY"]
            S_OAUTH["OAUTH_CLIENT_SECRET"]
            S_SA["agents-runtime-sa-token"]
        end

        subgraph PUBSUB["Pub/Sub"]
            TOPIC["chatbotwhatsapp-messages"]
            DLQ["chatbotwhatsapp-dlq (nativa)"]
        end

        OUT_EVO["POST /message/sendText/Jennifer"]
    end

    WA -->|"mensagem"| EVO_API
    EVO_API -->|"POST /webhook"| WEBHOOK
    WEBHOOK -->|"publica"| TOPIC
    TOPIC -->|"push /pubsub/push"| WEBHOOK
    WEBHOOK -->|"/orchestrate()"| ORCH

    ORCH --> DETECT
    DETECT -->|"intent (calendar/email/drive/web)"| GUARD
    GUARD -->|"graph.ainvoke()"| GRAPH

    GRAPH --> J
    J --> CI
    CI --> GD
    GD -->|"verdict=allow"| MG
    MG -->|"prefetch (opcional)"| TOOLS
    MG --> RL

    GD -->|"verdict=deny/request_oauth"| RL
    RL -->|"resposta bloqueada"| OUT_EVO

    EXEC -->|_execute_deep_agent (manager-calendar/email/drive)| DAGENTS
    DAGENTS -->|"system_prompt"| DTOOLS
    DTOOLS -->|"@tool wrappers"| LADAPT
    LADAPT -->|"ChatOpenAI(base_url=DeepSeek)"| LLM

    DTOOLS -->|"async call"| TOOLS
    TOOLS -->|"Google APIs (OAuth per-user)"| USERS
    USERS -->|"verifica owner_phone"| WHATSAPP_ACCOUNTS

    DTOOLS -->|"result"| DAGENTS
    DAGENTS -->|"answer"| ORCH

    ORCH -->|"/pubsub/push 200 OK"| PUBSUB
    ORCH -->|"send_text"| EVO_API
    EVO_API -->|"WhatsApp"| WA

    EXEC -.->|"fallback legacy\n(chat_with_tools)"| LLM

    AGENTS --> DAGENTS
    SKILLS --> DAGENTS
    TOOLS_CFG --> DAGENTS

    EXEC -->|"RAG indexing"| HISTORY
    ORCH -->|"message-processing"| LEDGER

    ATAW --> LLM
    PROW --> LLM

    S_DEEPSEEK --> LLM
    S_OPENAI -->|"embeddings\nRAG"| KNOWLEDGE
    S_EVO --> OUT_EVO

    ORCH --> AUDIT

    classDef llm fill:#f9e79f,stroke:#333,stroke-width:2px
    classDef firestore fill:#d5dbdb,stroke:#333,stroke-width:1px
    classDef google fill:#a9cce3,stroke:#333,stroke-width:1px
    classDef secret fill:#fadbd8,stroke:#333,stroke-width:1px

    class LLM llm
    class AGENTS,SKILLS,TOOLS_CFG,WHATSAPP_ACCOUNTS,USERS,NICKNAMES,LEDGER,HISTORY,KNOWLEDGE,COLLECTIVE,PUBLIC,AUDIT firestore
    class TGMAIL,TCAL,TDRIVE,TWEB google
    class S_OPENAI,S_EVO,S_DEEPSEEK,S_GEMINI,S_SERPER,S_OAUTH,S_SA secret
```

## Componentes principais

| Componente | Responsabilidade |
|---|---|
| **Evolution API** | Recebe webhook do WhatsApp, envia mensagens |
| **`/webhook`** | Entry point FastAPI; valida payload, publica Pub/Sub |
| **`orchestrator.py`** | Detecta intent, escolhe specialist, executa agent |
| **`agent_orchestration/graph.py`** | LangGraph StateGraph (jennifier → classify → guard → manager → reply) |
| **`access_guardian.py`** | Decide owner + OAuth + scopes |
| **`deepagent_layer/agents.py`** | Factory que cria um `create_deep_agent` por manager |
| **`deepagent_layer/tools.py`** | Wrappers LangChain `@tool` para Calendar/Email/Drive/Web |
| **`langchain_adapter/`** | Wrapper estável que isola versão LangChain |
| **`ChatOpenAI(base_url=DeepSeek)`** | LLM único (DeepSeek v4-flash, single-provider) |
| **`tools/google_*.py`** | Lógica de negócio + `@_owner_guard` (sem LangChain) |
| **`agent_loader.py`** | Snapshot Firestore de agents/skills/tools (120s polling) |
| **`ata_worker`/`proactive_worker`** | Cloud Run Jobs para gerar atas e proatividade |
| **Firestore** | agents, skills, tools, whatsapp_accounts, usuarios, knowledge |
| **Secret Manager** | DEEPSEEK_API_KEY, OPENAI_API_KEY, EVOLUTION_API_KEY, etc. |

## Caminho crítico: "me de meus últimos 3 emails"

```
1. WhatsApp → Evolution → POST /webhook
2. /webhook → publish chatbotwhatsapp-messages
3. /pubsub/push → /orchestrate(payload)
4. _detect_intent() → is_email=true
5. _run_guard_graph() → guard_node (verify owner + OAuth)
6. _execute_deep_agent(manager-email)
7. create_deep_agent(model=ChatOpenAI(base_url=DeepSeek), tools=[search_gmail, ...])
8. DeepSeek decide chamar search_gmail(phone="+55...", query="in:inbox newer_than:30d")
9. tool_executor → tools/google_gmail.py::search_messages
10. search_messages → Google Gmail API (com OAuth per-user)
11. resultado volta para DeepSeek
12. DeepSeek gera resposta amigável em pt-BR
13. /webhook → POST /message/sendText → Evolution → WhatsApp
```

## Fluxo de dados entre camadas

```
[WhatsApp]
   ↓ HTTP POST
[Evolution API]
   ↓ webhook POST
[Cloud Run: agents-runtime-test]
   ↓ Pub/Sub
   ├→ orchestrator.py
   │   ├→ LangGraph StateGraph (guard)
   │   └→ create_deep_agent
   │       ├→ ChatOpenAI(base_url=api.deepseek.com)  ← LLM (único)
   │       └→ @tool wrappers
   │           └→ tools/google_*.py (@_owner_guard)
   │               ├→ Google Calendar/Drive/Gmail API (OAuth per-user)
   │               └→ Firestore whatsapp_accounts (verifica owner)
   ↓ Pub/Sub ack 200 OK
   ↓ send_text
[Evolution API]
   ↓ HTTP POST
[WhatsApp]
```