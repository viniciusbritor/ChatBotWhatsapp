"""Tool Registry - central map of tool_id -> implementation function.

Each tool has:
- id: unique identifier
- function: callable
- description: for LLM schema
- parameters_schema: OpenAI-compatible JSON schema
"""
import copy
import logging
from typing import Dict, Any, Callable, Awaitable

from tools import google_calendar, google_drive, google_gmail, web_search, nickname
from tools import locomotion, youtube, group, correction, chat_history

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[Dict[str, Any]]]
USER_SCOPED_TOOL_PREFIXES = ("calendar.", "drive.", "gmail.")


def is_user_scoped_tool(tool_id: str) -> bool:
    return tool_id.startswith(USER_SCOPED_TOOL_PREFIXES)


async def _rag_search_knowledge(**kwargs):
    from core.rag import search_knowledge

    return await search_knowledge(kwargs.get("query", ""), kwargs.get("limit", 5))


async def _rag_search_legal_knowledge(**kwargs):
    from core.rag import search_legal_knowledge

    return await search_legal_knowledge(
        kwargs.get("phone", ""),
        kwargs.get("query", ""),
        kwargs.get("k", 5),
    )


async def _route_attachment(**kwargs):
    from agent_orchestration.knowledge_router import (
        categorize_and_extract,
        route_attachment,
    )

    envelope = kwargs.get("envelope") or {}
    user_text = kwargs.get("user_text", "")
    decision = await route_attachment(envelope, user_text)
    skill = decision.get("skill")
    extracted = decision.get("extracted")
    if skill is not None:
        if extracted is None and decision.get("decision") != "drive":
            extraction = await categorize_and_extract(envelope, skill)
            extracted = extraction.get("extracted")
            category = extraction.get("category")
            decision["extracted"] = extracted
            decision["category"] = category
        if decision.get("decision") == "drive":
            extracted = envelope.get("_drive_extracted")
            decision["extracted"] = extracted
        if extracted:
            persist_result = await skill.persist(
                envelope,
                extracted,
                decision.get("scope", "private"),
                metadata=decision.get("category") or {},
            )
        else:
            persist_result = {"error": "extraction_failed"}
        decision["persist_result"] = persist_result
    return decision


async def _retrieve_knowledge(**kwargs):
    from agent_orchestration.knowledge_retriever import retrieve

    envelope = kwargs.get("envelope") or {}
    query = kwargs.get("query", "")
    limit = kwargs.get("limit")
    min_score = kwargs.get("min_score")
    return await retrieve(
        envelope=envelope, query=query, limit=limit, min_score=min_score
    )


async def _categorize(**kwargs):
    from agent_orchestration.categorizer import categorize

    text = kwargs.get("text", "")
    source_name = kwargs.get("source_name", "")
    return await categorize(text=text, source_name=source_name)


async def _delete_knowledge(**kwargs):
    import hashlib
    from google.cloud import firestore

    source_title = kwargs.get("source_title", "")
    phone = kwargs.get("phone", "")
    if not source_title or not phone:
        return {"error": "source_title and phone are required", "deleted": 0}

    normalized = "".join(c for c in str(phone) if c.isdigit())
    owner_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    db = firestore.Client(project="coherence-ominichannel-fs")
    total = 0
    for collection in ("agent-knowledge-v2", "agent-knowledge-v2-plain"):
        docs = list(
            db.collection(collection)
            .where("owner_hash", "==", owner_hash)
            .where("source_title", "==", source_title)
            .stream()
        )
        for doc in docs:
            doc.reference.delete()
            total += 1

    return {
        "deleted": total,
        "source_title": source_title,
        "collections_cleared": ["agent-knowledge-v2", "agent-knowledge-v2-plain"],
    }


async def _list_knowledge(**kwargs):
    from agent_orchestration.knowledge_retriever import _list_known_sources

    phone = kwargs.get("phone", "")
    if not phone:
        return {"error": "phone is required", "documents": []}
    sources = await _list_known_sources(phone, limit=200)
    return {"documents": sources, "count": len(sources)}


async def _stats_knowledge(**kwargs):
    from agent_orchestration.knowledge_retriever import _list_knowledge_stats

    phone = kwargs.get("phone", "")
    if not phone:
        return {"error": "phone is required", "stats": {}}
    return await _list_knowledge_stats(phone)


async def _sections_knowledge(**kwargs):
    phone = kwargs.get("phone", "")
    source_title = kwargs.get("source_title", "")
    if not phone or not source_title:
        return {"error": "phone and source_title are required", "text": ""}

    from pipelines.doc_pipeline import _retrieve_full_document

    text = await _retrieve_full_document(phone, source_title, max_chars=30000)
    return {"source_title": source_title, "text": text, "chars": len(text)}


async def _search_all_knowledge(**kwargs):
    from core.rag import search_legal_knowledge

    phone = kwargs.get("phone", "")
    query = kwargs.get("query", "")
    limit = kwargs.get("limit", 10)
    min_score = kwargs.get("min_score", 0.35)
    if not phone or not query:
        return {"error": "phone and query are required", "results": []}
    return await search_legal_knowledge(
        phone=phone,
        query=query,
        k=limit,
        min_score=min_score,
    )


async def _render_image_report(**kwargs):
    from tools.image_report import render_report

    title = kwargs.get("title", "Relatorio")
    rows = kwargs.get("rows") or []
    headers = kwargs.get("headers")
    return render_report(
        title=title,
        rows=rows,
        headers=headers,
        emoji_header=kwargs.get("emoji_header", ""),
        footer=kwargs.get("footer", ""),
        accent=kwargs.get("accent", "#1A6B52"),
        max_width_px=int(kwargs.get("max_width_px", 1024)),
    )


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "calendar.list_events": {
        "function": google_calendar.list_events,
        "implementation": "google_calendar",
        "description": "Lista eventos do Google Calendar entre time_min e time_max. IMPORTANTE: sempre passe o telefone (phone) do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "ISO 8601 datetime inicio"},
                "time_max": {"type": "string", "description": "ISO 8601 datetime fim"},
                "calendar_id": {"type": "string", "description": "ID do calendario (default: primary)"},
                "max_results": {"type": "integer", "description": "Maximo de eventos (default: 50)"},
                "phone": {"type": "string", "description": "Telefone do usuario para usar o token OAuth dele"},
            },
            "required": ["time_min", "time_max"],
        },
    },
    "calendar.create_event": {
        "function": google_calendar.create_event,
        "implementation": "google_calendar",
        "description": "Cria um novo evento no Google Calendar. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO 8601 datetime inicio"},
                "end": {"type": "string", "description": "ISO 8601 datetime fim"},
                "summary": {"type": "string", "description": "Titulo do evento"},
                "description": {"type": "string", "description": "Descricao opcional"},
                "attendees": {"type": "array", "items": {"type": "string"}, "description": "Lista de emails"},
                "location": {"type": "string", "description": "Local do evento"},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["start", "end", "summary"],
        },
    },
    "calendar.update_event": {
        "function": google_calendar.update_event,
        "implementation": "google_calendar",
        "description": "Atualiza um evento existente.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["event_id"],
        },
    },
    "calendar.delete_event": {
        "function": google_calendar.delete_event,
        "implementation": "google_calendar",
        "description": "Deleta um evento do calendar.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["event_id"],
        },
    },
    "calendar.freebusy": {
        "function": google_calendar.freebusy,
        "implementation": "google_calendar",
        "description": "Consulta free/busy de calendarios.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "calendars": {"type": "array", "items": {"type": "string"}},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["time_min", "time_max"],
        },
    },
    "drive.search_files": {
        "function": google_drive.search_files,
        "implementation": "google_drive",
        "description": "Busca arquivos no Google Drive por nome. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "folder_id": {"type": "string"},
                "mime_type": {"type": "string"},
                "max_results": {"type": "integer"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["query"],
        },
    },
    "drive.upload_file": {
        "function": google_drive.upload_file,
        "implementation": "google_drive",
        "description": "Faz upload de arquivo para uma pasta do Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string"},
                "filename": {"type": "string"},
                "content": {"type": "string"},
                "mime_type": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["folder_id", "filename", "content"],
        },
    },
    "drive.list_folder": {
        "function": google_drive.list_folder,
        "implementation": "google_drive",
        "description": "Lista conteudo de uma pasta do Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string"},
                "max_results": {"type": "integer"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
        },
    },
    "drive.create_folder": {
        "function": google_drive.create_folder,
        "implementation": "google_drive",
        "description": "Cria uma pasta no Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["name"],
        },
    },
    "drive.read_file_content": {
        "function": google_drive.read_file_content,
        "implementation": "google_drive",
        "description": (
            "Baixa e extrai o conteudo de texto de um arquivo do Google Drive "
            "(PDF, DOCX, XLSX, texto puro, Google Docs, Google Sheets, Google Slides). "
            "Passe o file_id retornado por drive.search_files. Phone obrigatorio."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "ID do arquivo no Google Drive"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["file_id"],
        },
    },
    "drive.deep_search_drive": {
        "function": google_drive.deep_search_drive,
        "implementation": "google_drive",
        "description": (
            "Busca recursiva em pastas e subpastas do Google Drive. "
            "Varre a arvore de pastas a partir de parent_folder_id (ou 'root' para tudo), "
            "casando nomes de arquivos e pastas com a query. Suporta shared drives. "
            "Ideal para 'ache a ata', 'procure o relatorio', 'busque o orcamento'. "
            "Passe o phone do usuario."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca (ex: ata, relatorio, orcamento)"},
                "parent_folder_id": {"type": "string", "description": "Pasta de partida (default: 'root' para todos os drives)"},
                "max_depth": {"type": "integer", "description": "Profundidade maxima de recursao (default 3)"},
                "max_results": {"type": "integer", "description": "Maximo de resultados (default 50)"},
                "include_shared_drives": {"type": "boolean", "description": "Incluir shared drives (default true)"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["query"],
        },
    },
    "gmail.search_messages": {
        "function": google_gmail.search_messages,
        "implementation": "google_gmail",
        "description": "Busca mensagens no Gmail por query. Passe o phone do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "label_ids": {"type": "array", "items": {"type": "string"}},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["query"],
        },
    },
    "gmail.get_thread": {
        "function": google_gmail.get_thread,
        "implementation": "google_gmail",
        "description": "Retorna todas as mensagens de uma thread.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["thread_id"],
        },
    },
    "gmail.send_message": {
        "function": google_gmail.send_message,
        "implementation": "google_gmail",
        "description": "Envia um email.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "thread_id": {"type": "string"},
                "html": {"type": "boolean"},
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "web.search": {
        "function": web_search.serper_search,
        "implementation": "web_search",
        "description": "Busca na web via Serper.dev (com cache 24h).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num": {"type": "integer", "description": "Numero de resultados (default: 10)"},
            },
            "required": ["query"],
        },
    },
    "correction.detect": {
        "function": correction.detect_correction,
        "implementation": "correction",
        "description": (
            "Detecta se uma mensagem do usuario contem uma correcao. "
            "Retorna is_correction, confidence (0-1), target (preferred_name/"
            "agent_behavior/agent_fact) e extracted (trecho original)."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto da mensagem do usuario"},
            },
            "required": ["text"],
        },
    },
    "correction.log": {
        "function": correction.log_correction,
        "implementation": "correction",
        "description": (
            "Registra uma correcao confirmada no Firestore contatos/{phone}/corrections. "
            "Chame APOS o usuario confirmar com 'sim'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "user_quote": {"type": "string", "description": "Frase original do usuario"},
                "target": {"type": "string", "description": "Tipo de correcao (preferred_name, agent_behavior, agent_fact)"},
                "before": {"type": "string", "description": "Valor antes da correcao"},
                "after": {"type": "string", "description": "Valor corrigido"},
                "confirmed": {"type": "boolean", "description": "Se o usuario confirmou"},
            },
            "required": ["phone", "user_quote", "target", "before", "after", "confirmed"],
        },
    },
    "correction.apply_patch": {
        "function": correction.apply_patch,
        "implementation": "correction",
        "description": (
            "Aplica uma correcao ao system_prompt de um agente no Firestore. "
            "Use APENAS apos confirmacao do usuario."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "ID do agente a atualizar"},
                "target": {"type": "string", "description": "Campo alvo (system_prompt ou replace:old:new)"},
                "patch_text": {"type": "string", "description": "Novo texto para o campo"},
            },
            "required": ["agent_id", "target", "patch_text"],
        },
    },
    "group.index_document": {
        "function": group.index_group_document,
        "implementation": "group",
        "description": (
            "Indexa um documento (PDF, DOCX, planilha) no conhecimento do grupo. "
            "Faz chunking 1200 chars x 15% overlap, embedding OpenAI text-embedding-3-small, "
            "classifica tema (ata_reuniao, dados_financeiros, apresentacao, contrato, documentacao). "
            "Use apos ler o arquivo com drive.read_file_content. "
            "Pede consentimento de visibilidade: 'apenas grupo' ou 'publico'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "group_jid": {"type": "string", "description": "JID do grupo WhatsApp"},
                "text": {"type": "string", "description": "Conteudo do documento"},
                "visibility": {"type": "string", "description": "'group' ou 'public'"},
                "source_name": {"type": "string", "description": "Nome do arquivo original"},
                "force_overwrite": {"type": "boolean", "description": "Sobrescrever se ja existe (default false)"},
            },
            "required": ["phone", "group_jid", "text", "visibility"],
        },
    },
    "group.search_knowledge": {
        "function": group.search_group_knowledge,
        "implementation": "group",
        "description": (
            "Busca no conhecimento RAG do grupo e publico. "
            "Retorna os top-N trechos mais semanticamente similares a query. "
            "Use quando o usuario pergunta 'o que foi decidido sobre X?' ou 'tem algum documento sobre Y?'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "group_jid": {"type": "string", "description": "JID do grupo WhatsApp"},
                "query": {"type": "string", "description": "Texto de busca"},
                "limit": {"type": "integer", "description": "Maximo de resultados (default 5)"},
            },
            "required": ["group_jid", "query"],
        },
    },
    "knowledge.route_attachment": {
        "function": _route_attachment,
        "implementation": "knowledge_router",
        "description": (
            "Roteia um anexo recebido no WhatsApp para a skill apropriada de "
            "armazenamento. Decide entre Firestore Vector (default) e Google "
            "Drive (so se o user pedir explicitamente). Retorna status rag_*, "
            "drive_* ou error."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object", "description": "Envelope do webhook"},
                "user_text": {"type": "string", "description": "Texto da mensagem do user"},
            },
            "required": ["envelope", "user_text"],
        },
    },
    "knowledge.retrieve": {
        "function": _retrieve_knowledge,
        "implementation": "knowledge_retriever",
        "description": (
            "Recupera trechos previamente armazenados na base de conhecimento "
            "do user (agent-knowledge-v2) ou do grupo (group-knowledge-v2). "
            "Quando a pergunta vem em grupo e ha match apenas em RAG privado, "
            "cria pending_action share_private_knowledge_in_group para pedir "
            "consentimento antes de compartilhar."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "envelope": {"type": "object", "description": "Envelope do webhook"},
                "query": {"type": "string", "description": "Pergunta do user"},
                "limit": {"type": "integer", "description": "Maximo de resultados (default 5)"},
                "min_score": {"type": "number", "description": "Score minimo (default 0.5)"},
            },
            "required": ["envelope", "query"],
        },
    },
    "knowledge.categorize": {
        "function": _categorize,
        "implementation": "knowledge_categorizer",
        "description": (
            "Categoriza um documento (PDF, DOCX, XLSX, texto) em "
            "{class, group, theme, confidence} antes de armazenar. "
            "Use apos extrair o texto do anexo. Se o LLM falhar, "
            "usa heuristica local; em ultimo caso, devolve outros/outros."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto extraido do documento"},
                "source_name": {"type": "string", "description": "Nome do arquivo original"},
            },
            "required": ["text", "source_name"],
        },
    },
    "knowledge.delete": {
        "function": _delete_knowledge,
        "implementation": "knowledge_delete",
        "description": (
            "Remove todos os chunks de um documento especifico da base de conhecimento "
            "do usuario. Use quando o usuario pedir para apagar, remover, deletar ou "
            "retirar um documento da base. O parametro source_title deve ser o nome "
            "exato do arquivo (ex: 'lgpd-capitulo-1.pdf')."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "source_title": {"type": "string", "description": "Nome exato do arquivo a deletar"},
                "phone": {"type": "string", "description": "Telefone do usuario owner"},
            },
            "required": ["source_title", "phone"],
        },
    },
    "knowledge.list": {
        "function": _list_knowledge,
        "implementation": "knowledge_lister",
        "description": (
            "Lista todos os documentos indexados na base de conhecimento "
            "do usuario (agent-knowledge-v2). Retorna source_title, "
            "document_title, class, group, theme e total de chunks por doc. "
            "Use quando o usuario perguntar 'quais documentos tenho?' ou "
            "'o que esta na minha base?'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
            },
            "required": ["phone"],
        },
    },
    "knowledge.stats": {
        "function": _stats_knowledge,
        "implementation": "knowledge_stats",
        "description": (
            "Retorna estatisticas agregadas da base de conhecimento: "
            "quantos documentos por class (legal, academico, edital, etc.) "
            "e por group (legislacao, tese, licitacao, etc.). "
            "Use quando o usuario perguntar 'que tipo de documento tenho?' "
            "ou 'quantas leis eu indexei?'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
            },
            "required": ["phone"],
        },
    },
    "knowledge.sections": {
        "function": _sections_knowledge,
        "implementation": "knowledge_sections",
        "description": (
            "Recupera o texto COMPLETO de um documento nomeado da base, "
            "concatenando todos os chunks em ordem (ate 30000 chars). "
            "Use quando o usuario pedir detalhes de um documento especifico "
            "por nome exato: 'me mostre a tese vinicius.pdf' ou 'extraia "
            "o capitulo 3 do lgpd'."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "source_title": {"type": "string", "description": "Nome exato do arquivo"},
            },
            "required": ["phone", "source_title"],
        },
    },
    "knowledge.search_all": {
        "function": _search_all_knowledge,
        "implementation": "knowledge_search_all",
        "description": (
            "Busca semantica na base de conhecimento SEM filtros de class, "
            "group ou source_title. Retorna os top-N chunks mais similares "
            "com score >= min_score (default 0.35). "
            "Use como escape hatch quando knowledge.retrieve retorna 0 hits "
            "ou quando o usuario quer buscar 'tudo' sem restricao."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "query": {"type": "string", "description": "Pergunta ou termo de busca"},
                "limit": {"type": "integer", "description": "Maximo de resultados (default 10)"},
                "min_score": {"type": "number", "description": "Score minimo (default 0.35)"},
            },
            "required": ["phone", "query"],
        },
    },
    "image_report.render": {
        "function": _render_image_report,
        "implementation": "image_report",
        "description": (
            "Renderiza uma tabela como imagem PNG formatada para "
            "preview do WhatsApp. Retorna bytes PNG e data URI. "
            "Usar quando o resultado for uma lista (Drive, RAG, "
            "anotacoes) que ficaria mais clara visualmente como "
            "tabela do que como texto puro. Trunca acima de "
            "IMAGE_REPORT_MAX_ROWS (default 12)."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo do relatorio"},
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "Linhas de dados (strings)",
                },
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cabecalhos das colunas (opcional)",
                },
                "emoji_header": {"type": "string", "description": "Emoji antes do titulo (opcional)"},
                "footer": {"type": "string", "description": "Rodape (opcional)"},
                "accent": {"type": "string", "description": "Cor de destaque em hex (#RRGGBB)"},
                "max_width_px": {"type": "integer", "description": "Largura em px (default 1024)"},
            },
            "required": ["title", "rows"],
        },
    },
    "web.fetch_url": {
        "function": web_search.fetch_url,
        "implementation": "web_search",
        "description": "Faz fetch do conteudo de uma URL.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["url"],
        },
    },
    "nickname.lookup": {
        "function": nickname.lookup,
        "implementation": "nickname",
        "description": "Busca apelidos conhecidos para um nome.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    "nickname.set_consent": {
        "function": nickname.set_consent,
        "implementation": "nickname",
        "description": "Registra consentimento do usuario sobre um apelido.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "name": {"type": "string"},
                "nickname": {"type": "string"},
                "accepted": {"type": "boolean"},
            },
            "required": ["phone", "name", "nickname"],
        },
    },
    "nickname.get_preferred_name": {
        "function": nickname.get_preferred_name,
        "implementation": "nickname",
        "description": "Retorna o nome preferido (apelido aceito) do usuario.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    "drive.find_omnichannel_atas_folder": {
        "function": google_drive.find_omnichannel_atas_folder,
        "implementation": "google_drive",
        "description": "Encontra a pasta Omnichannel/Atas/ no Drive.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario para token OAuth"},
            },
        },
    },
    "locomotion.calc_route": {
        "function": locomotion.calc_route,
        "implementation": "locomotion",
        "description": "Calcula rota entre dois enderecos. Retorna distancia, duracao, preco estimado Uber e 99.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Endereco de partida"},
                "destino": {"type": "string", "description": "Endereco de chegada"},
            },
            "required": ["origem", "destino"],
        },
    },
    "locomotion.geocode": {
        "function": locomotion.geocode,
        "implementation": "locomotion",
        "description": "Converte endereco em coordenadas e endereco formatado.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "endereco": {"type": "string", "description": "Endereco para geocodificar"},
            },
            "required": ["endereco"],
        },
    },
    "locomotion.search_places": {
        "function": locomotion.search_places,
        "implementation": "locomotion",
        "description": "Busca lugares proximos (restaurantes, farmacias, etc).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "local": {"type": "string", "description": "Localizacao de referencia"},
                "tipo": {"type": "string", "description": "Tipo: restaurant, pharmacy, gas_station"},
            },
            "required": ["local"],
        },
    },
    "youtube.search_videos": {
        "function": youtube.search_videos,
        "implementation": "youtube",
        "description": "Busca videos no YouTube e retorna titulo, canal e link.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca"},
                "max_results": {"type": "integer", "description": "Maximo de resultados (default 3)"},
            },
            "required": ["query"],
        },
    },
    "group.get_info": {
        "function": group.get_group_info,
        "implementation": "group",
        "description": "Retorna dados do grupo e contagem de membros confirmados.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "group_jid": {"type": "string", "description": "JID do grupo WhatsApp"},
            },
            "required": ["group_jid"],
        },
    },
    "rag.search_knowledge": {
        "function": _rag_search_knowledge,
        "implementation": "rag",
        "description": "Busca semantica na base de conhecimento publica (leis, editais, livros).",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca semantica"},
                "limit": {"type": "integer", "description": "Maximo de resultados"},
            },
            "required": ["query"],
        },
    },
    "rag.search_legal_knowledge": {
        "function": _rag_search_legal_knowledge,
        "implementation": "rag",
        "description": "Busca semantica em legislacao (leis penais, editais) no banco privado do agente.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "query": {"type": "string", "description": "Termo de busca semantica"},
                "k": {"type": "integer", "description": "Maximo de resultados"},
            },
            "required": ["phone", "query"],
        },
    },
    "chat_history.search": {
        "function": chat_history.search_chat_history,
        "implementation": "chat_history",
        "description": (
            "Busca no historico de conversas por topico ou palavra-chave. "
            "Use quando o usuario fizer referencia a algo ja discutido antes, "
            "como 'voce lembra', 'falamos sobre', 'semana passada'. "
            "Retorna trechos relevantes com data."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "query": {"type": "string", "description": "Palavra-chave ou topico a buscar"},
                "limit": {"type": "integer", "description": "Maximo de resultados (default 5)"},
            },
            "required": ["phone", "query"],
        },
    },
    "chat_history.context": {
        "function": chat_history.get_chat_context,
        "implementation": "chat_history",
        "description": (
            "Retorna os ultimos N turnos da conversa com o usuario. "
            "Use para recuperar o fio da conversa recente."
        ),
        "parameters_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefone do usuario"},
                "limit": {"type": "integer", "description": "Numero de turnos (default 10)"},
            },
            "required": ["phone"],
        },
    },
}


def get_tool(tool_id: str):
    """Get tool function by id."""
    entry = TOOL_REGISTRY.get(tool_id)
    if entry:
        return entry["function"]
    return None


def get_tool_schema(tool_id: str):
    """Get tool schema for LLM."""
    entry = TOOL_REGISTRY.get(tool_id)
    if entry:
        parameters = copy.deepcopy(entry["parameters_schema"])
        description = entry["description"]
        if is_user_scoped_tool(tool_id):
            parameters.get("properties", {}).pop("phone", None)
            parameters["required"] = [
                value for value in parameters.get("required", []) if value != "phone"
            ]
            description = description.replace(
                " IMPORTANTE: sempre passe o telefone (phone) do usuario.", ""
            ).replace(" Passe o phone do usuario.", "")
        return {
            "name": tool_id,
            "description": description,
            "parameters": parameters,
        }
    return None


def list_tool_ids() -> list:
    """List all registered tool IDs."""
    return list(TOOL_REGISTRY.keys())


def get_tools_for_agent(tool_ids: list) -> list:
    """Get tool schemas for an agent."""
    return [get_tool_schema(tid) for tid in tool_ids if get_tool_schema(tid)]
