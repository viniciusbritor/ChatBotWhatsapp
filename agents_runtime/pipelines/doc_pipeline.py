"""Doc pipeline — RAG vs Drive routing with DeepSeek V4 Pro.

Detect: document keywords (pdf, docx, ata, documento, pasta, etc.)
Disambiguate: keywords explicitos → fast path
               ambiguous → DeepSeek V4 Pro
               Pro down → "clarify" (ask user)
Run:
  RAG path → knowledge retriever (no OAuth guard)
  Drive path → guard → ack → prefetch → agent
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

DOC_KEYWORDS = (
    "documento", "documentos", "arquivo", "arquivos", "pdf", "docx",
    "xlsx", "planilha", "ata", "atas", "minuta", "relatorio",
    "apresentacao", "apresentação", "pasta", "upload",
    "leia o arquivo", "leia a ata", "abra o arquivo",
    "buscar arquivo", "buscar arquivos", "procurar documento",
    "conteudo do arquivo", "conteudo da pasta",
    "base de conhecimento", "base de dados", "conhecimento",
    "busque", "buscar", "busca", "procure", "procurar",
    "ache", "achar", "encontre", "encontrar",
    "localize", "localizar", "pesquise", "pesquisar",
    "gdrive", "meu drive", "no drive",
    "meus arquivos", "meus documentos", "minha pasta",
    "custo", "custos", "orcamento", "orçamento",
)

_RAG_ONLY_KEYWORDS = (
    "base de conhecimento", "knowledge base", "memorizou", "memorizado",
    "indexou", "indexado", "no vector", "no firestore", "no rag",
    "sua memoria", "sua base", "voce guardou", "voce salvou",
    "que voce sabe sobre", "o que voce tem sobre",
    "vc memorizou", "vc guardou", "vc salvou",
    "documentos salvos", "documentos indexados", "arquivos salvos",
    "seus documentos", "meus documentos", "no conhecimento",
)

_DRIVE_ONLY_KEYWORDS = (
    "meu drive", "no drive", "no gdrive", "google drive",
    "pasta do drive", "arquivos do drive", "liste os arquivos",
    "meu gdrive", "salvar no drive", "guarda no drive",
    "dentro do drive", "dentro desse drive", "nesse drive",
    "faca upload", "upload", "salva no drive",
    "gdrive", "no omnichannel", "na omnichannel", "pasta omnichannel",
    "meu omnichannel",
)

_LIST_KEYWORDS = (
    "o que voce sabe", "o que você sabe", "o que vc sabe",
    "liste os documentos", "lista os documentos", "listar documentos",
    "qual o conteudo da base", "qual o conteúdo da base",
    "quais documentos voce tem", "quais documentos você tem",
    "o que tem na base", "o que esta na base", "o que está na base",
    "documentos na base", "documentos salvos", "documentos indexados",
    "me mostre o que tem", "mostre os documentos",
    "mostre o que voce tem", "mostre o que você tem",
    "o que voce tem", "o que você tem",
    "o que ja foi indexado", "o que foi memorizado", "o que foi guardado",
    "base de conhecimento", "sua base", "minha base",
    "o que tem ai", "o que tem aí",
    "sua memoria", "sua memória",
    "o que voce lembra", "o que você lembra",
    "tem documento", "quais documentos",
    "o que esta salvo", "o que está salvo",
    "o que foi guardado", "liste a base",
    "liste sua base", "lista sua base",
)


async def _list_knowledge_base(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Lista todos os documentos indexados na base de conhecimento."""
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    extra = payload.get("extra", {}) or {}

    try:
        from pipelines._ack import send_ack
        await send_ack(instance, phone, "rag", extra)
    except Exception:
        pass

    try:
        from agent_orchestration.knowledge_retriever import _list_known_sources
        sources = await _list_known_sources(phone)
        if not sources:
            return {
                "reply": "Nao tenho nenhum documento na base de conhecimento ainda. "
                         "Envie um PDF, DOCX, XLSX ou texto que eu memorizo pra voce!",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "list_documents": True, "count": 0, "skip_image_report": True},
            }
        lista = "\n".join(f"• {s}" for s in sources)
        prompt = f"Pergunte sobre qualquer um deles! Ex: 'o que diz {sources[0]}?'" if sources else ""
        return {
            "reply": (
                f"📚 Documentos na minha base de conhecimento:\n\n{lista}\n\n{prompt}"
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "agent-knowledge-retriever", "list_documents": True, "count": len(sources), "skip_image_report": True},
        }
    except Exception as exc:
        return {
            "reply": "Desculpe, nao consegui listar os documentos agora.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "agent-knowledge-retriever", "error": str(exc)[:200]},
        }


_DISAMBIGUATOR_PROMPT = (
    "O usuario disse: '{text}'\n"
    "Contexto recente: {context}\n\n"
    "Ele quer acessar:\n"
    "- RAG: base de conhecimento vetorial (editais, leis, teses indexadas no Firestore)\n"
    "- DRIVE: Google Drive pessoal (arquivos do dia a dia, PPTs, planilhas)\n\n"
    "Responda apenas RAG ou DRIVE."
)


def detect(text: str) -> bool:
    t = text.lower()
    for kw in DOC_KEYWORDS:
        if kw in t:
            return True
    for kw in _LIST_KEYWORDS:
        if kw in t:
            return True
    is_attachment = any(
        kw in t for kw in (
            "memorize", "memorizar", "guarde", "guardar",
            "indexe", "indexar", "salve isso", "salvar isso",
            "guarda isso", "armazene", "armazenar",
        )
    )
    return is_attachment


async def _disambiguate_rag_vs_drive(
    text: str,
    recent_context: str = "",
) -> str:
    """DeepSeek V4 Pro: decide RAG vs Drive.

    Returns: "rag" | "drive" | "clarify"
    """
    t = text.lower()

    for kw in _RAG_ONLY_KEYWORDS:
        if kw in t:
            return "rag"
    for kw in _DRIVE_ONLY_KEYWORDS:
        if kw in t:
            return "drive"

    try:
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return "clarify"

        base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        ).strip()

        model = ChatOpenAI(
            model="deepseek-v4-pro",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=10,
            timeout=5,
        )

        prompt = _DISAMBIGUATOR_PROMPT.format(
            text=text[:500],
            context=recent_context[:300] or "nenhum contexto recente",
        )

        import asyncio
        response = await asyncio.to_thread(model.invoke, prompt)
        raw = (
            getattr(response, "content", str(response))
            if not isinstance(response, dict)
            else response.get("content", "")
        )
        cleaned = raw.strip().upper()
        if "RAG" in cleaned:
            return "rag"
        return "drive"

    except Exception as exc:
        logger.warning("DeepSeek Pro indisponivel: %s — solicitando clarificacao", exc)
        return "clarify"


async def _run_rag(payload: Dict[str, Any]) -> Dict[str, Any]:
    """RAG path: search knowledge base (no OAuth guard)."""
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    try:
        from pipelines._ack import send_ack
        await send_ack(instance, phone, "rag", extra)
    except Exception:
        pass

    try:
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": phone,
            "extra": {
                "remote_jid": extra.get("remote_jid", f"{phone}@s.whatsapp.net"),
            },
        }

        result = await retrieve(envelope, text)

        if result.get("clarification_prompt"):
            return {
                "reply": result["clarification_prompt"],
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "needs_clarification": True, "skip_image_report": True},
            }

        chunks = result.get("results", [])
        if not chunks:
            return {
                "reply": "Nao encontrei nada sobre isso na base de conhecimento.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "count": 0, "skip_image_report": True},
            }

        resposta = "\n\n".join(
            f"[{c.get('source', '?')[:40]}] {c.get('text', '')[:300]}"
            for c in chunks[:3]
        )
        return {
            "reply": resposta,
            "delay_ms": 500,
            "presence": "composing",
            "metadata": {
                "agent_id": "agent-knowledge-retriever",
                "count": len(chunks),
                "scope": result.get("scope", "private"),
                "skip_image_report": True,
            },
        }
    except Exception as exc:
        logger.error("rag_retrieve_failed error=%s", exc)
        return {
            "reply": "Desculpe, nao consegui buscar na base de conhecimento agora.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "agent-knowledge-retriever", "error": str(exc)[:200], "skip_image_report": True},
        }


async def _run_drive(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drive path: guard → ack → prefetch → agent."""
    instance = payload.get("instance", "jennifer")
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

    from pipelines._guard import check_google_access, blocked_response

    guard = await check_google_access(instance, phone, "drive")
    if guard.get("verdict") != "allow":
        return blocked_response(guard)

    from pipelines._ack import send_ack

    try:
        await send_ack(instance, phone, "drive", extra)
    except Exception:
        pass

    from pipelines._prefetch import prefetch_for_agent

    prefetch = None
    try:
        prefetch = await prefetch_for_agent(phone, instance, "drive", text=text)
    except Exception:
        pass

    from pipelines._executor import run_agent

    return await run_agent(
        "manager-drive",
        text,
        payload,
        extra,
        prefetch=prefetch,
        prefetch_label="DRIVE",
        tone_guide="Responda em portugues brasileiro com tom caloroso. "
                   "Liste arquivos com nome, tipo e data de modificacao.",
    )


async def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Detect → disambiguate → route to RAG or Drive."""
    text = payload.get("text", "")
    phone = payload.get("phone", "")

    if not text.strip():
        return await _run_rag(payload)

    # Fast path: listar documentos da base (somente se nao for query de conteudo)
    t = text.lower()
    _CONTENT_MARKERS = ("diz", "fala", "capitulo", "artigo", "lei", "sobre", "resuma", "explique", "qual o", "quais os")
    has_list_kw = any(kw in t for kw in _LIST_KEYWORDS)
    has_content = any(mk in t for mk in _CONTENT_MARKERS)
    if has_list_kw and not has_content:
        return await _list_knowledge_base(payload)

    recent_context = ""
    try:
        from orchestrator import _get_conversation_history
        recent_context = (
            _get_conversation_history(phone, limit=2) or ""
        )
    except Exception:
        pass

    decision = await _disambiguate_rag_vs_drive(text, recent_context)

    if decision == "clarify":
        return {
            "reply": (
                "Nao entendi se voce quer buscar na:\n\n"
                "• Base de conhecimento (editais, leis, teses que indexamos)\n"
                "• Google Drive (seus arquivos, PPTs, planilhas)\n\n"
                "E so me dizer: 'base de conhecimento' ou 'drive'?"
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "doc-disambiguator",
                "needs_clarification": True,
            },
        }

    if decision == "drive":
        return await _run_drive(payload)
    return await _run_rag(payload)
