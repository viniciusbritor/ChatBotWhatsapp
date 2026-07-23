"""Render a Mermaid diagram of the ChatBotWhatsapp architecture.

Exported to ``docs/diagrams/architecture.mmd`` (plain text) and
``docs/diagrams/architecture.html`` (rendered SVG, self-contained).

The diagram renders the exact runtime topology after the 23/07/2026
cleanup:

- One Cloud Run service (``agents-runtime-test``) handles webhook,
  /pubsub/push, /admin/* and the bundled UI.
- Pub/Sub topics: ``chatbotwhatsapp-messages`` plus native DLQ.
- Firestore plain holds the chat history; Firestore Vector holds only
  documents (books, editais, public).
- GCP Secret Manager serves runtime secrets via --set-secrets.
- Owner-only Google tools run with Firestore-resolved owner ids.
"""
from pathlib import Path

DIAGRAM = """flowchart LR
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
            ORCH["Jennifer Orchestrator"]
            ADMIN["GET/POST /admin/* (Bearer)"]
            UI["HTML do modulo Agentes Omnichannel"]
            WHISPER["Whisper (faster-whisper base)"]
            EMBED["OpenAI Embeddings (somente ingestao)"]
            SUBF["Tools: calendar/drive/gmail/web/nickname"]
            GUARD["Owner Guard (resolve owner_phone)"]
        end

        subgraph PUBSUB["Pub/Sub"]
            TOPIC["chatbotwhatsapp-messages"]
            DLQ["chatbotwhatsapp-dlq (nativa)"]
        end

        subgraph SECRETS["Secret Manager"]
            S_OPENAI["OPENAI_API_KEY"]
            S_EVO["EVOLUTION_API_KEY"]
            S_MINIMAX["MINIMAX_API_KEY"]
            S_DEEPSEEK["DEEPSEEK_API_KEY"]
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
            AUDIT["audit/*"]
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

    ORCH --> GUARD
    GUARD --> ACCOUNTS
    ORCH --> WHISPER
    WHISPER -. "OPENAI_API_KEY" .-> S_OPENAI
    EMBED -. "OPENAI_API_KEY (somente ingestao)" .-> S_OPENAI
    ORCH --> SUBF
    SUBF -. "refresh_token por owner" .-> USERS
    SUBF -- "Calendar/Drive/Gmail" --> USER
    ORCH -- "history.write (always, plain)" --> HISTORY
    ORCH -- "history.read (where owner_hash == ...)" --> HISTORY

    ADMIN -- "Bearer SA" --> S_SA
    S_OPENAI --> EMBED
    S_EVO --> EVO_API
    S_MINIMAX --> ORCH
    S_DEEPSEEK --> ORCH

    GCS -- "scripts/ingest_owner_knowledge.py" --> KNOWLEDGE
    GCS -- "scripts/ingest_collective_memory.py" --> COLLECTIVE
    KNOWLEDGE -- "search_legal_knowledge (kNN, owner_hash filter)" --> ORCH
    COLLECTIVE -- "search_collective (kNN, no owner_hash)" --> ORCH
    PUBLIC -- "search_knowledge (kNN)" --> ORCH

    UI --> ADMIN
    ACCOUNTS --> GUARD
    NICKNAMES --> ORCH
    USERS --> SUBF

    CLOUD_BUILD -- "git push origin/test" --> EDGE
    EDGE -- "deploy" --> RUNTIME
    AUDIT -- "log_action (5y retencao)" --> RUNTIME

    TOPIC -. "5 tentativas" .-> DLQ
"""


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "architecture.mmd"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DIAGRAM, encoding="utf-8")
    print(f"mermaid diagram: {target}")


if __name__ == "__main__":
    main()
