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

import asyncio
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

_DELETE_MARKERS = (
    "retire", "retirar", "apague", "apagar", "deletar", "delete",
    "remover", "remova", "remove",
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
        await asyncio.sleep(0.8)
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


_DOC_EXCLUDE_PATTERNS = (
    "agenda", "agend", "evento", "eventos", "compromisso",
    "compromissos", "lembrete", "calendario", "disponivel",
    "semana que vem", "proxima semana",
    "email", "e-mail", "emails", "e-mails",
    "caixa de entrada", "caixa postal", "correio", "inbox",
    "gmail", "ler email", "enviar email", "ultimos emails",
    "ultima mensagem", "mensagens",
)


def detect(text: str) -> bool:
    t = text.lower()
    has_calendar_or_email = any(ex in t for ex in _DOC_EXCLUDE_PATTERNS)

    for kw in _LIST_KEYWORDS:
        if kw in t:
            return True
    for kw in DOC_KEYWORDS:
        if kw in t:
            if has_calendar_or_email:
                return False
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

    async def _send_ack_rag():
        try:
            from pipelines._ack import send_ack
            await send_ack(instance, phone, "rag", extra)
            await asyncio.sleep(0.8)
        except Exception:
            pass

    ack_task = asyncio.create_task(_send_ack_rag())

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
            await ack_task
            return {
                "reply": result["clarification_prompt"],
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {
                    "agent_id": "agent-knowledge-retriever",
                    "needs_clarification": True,
                    "skip_image_report": True,
                },
            }

        chunks = result.get("results", [])
        if not chunks:
            await ack_task
            return {
                "reply": "Nao encontrei nada sobre isso na base de conhecimento.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "count": 0, "skip_image_report": True},
            }

        resposta = await _synthesize_rag_answer(text, chunks)
        await ack_task
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
        await ack_task
        logger.error("rag_retrieve_failed error=%s", exc)
        return {
            "reply": "Desculpe, nao consegui buscar na base de conhecimento agora.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "agent-knowledge-retriever", "error": str(exc)[:200], "skip_image_report": True},
        }


_SYNTHESIS_SYSTEM_PROMPT = (
    "Voce e a Jennifer, assistente virtual. Use APENAS os trechos abaixo "
    "para responder a pergunta do usuario de forma clara e direta. "
    "NAO invente informacao que nao esta nos trechos. "
    "Se os trechos nao contiverem a resposta, diga que nao encontrou. "
    "Responda em portugues brasileiro, em no maximo 1 paragrafo. "
    "Sempre cite a fonte entre colchetes."
)


def _fallback_raw_chunks(chunks: list) -> str:
    """Fallback: dump cru de chunks (comportamento legado)."""
    return "\n\n".join(
        f"[{c.get('source', '?')[:40]}] {c.get('text', '')[:300]}"
        for c in chunks[:3]
    )


async def _call_llm_synthesis(
    model: str,
    query: str,
    chunks: list,
    max_tokens: int,
    timeout: int,
    extra_kwargs: dict,
) -> str:
    """Call DeepSeek LLM for RAG synthesis. Returns answer text."""
    from langchain_openai import ChatOpenAI

    api_key = (os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY not set")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()

    context = "\n---\n".join(
        f"[Fonte: {c.get('source', '?')}] {c.get('text', '')[:800]}"
        for c in chunks[:5]
    )

    user_prompt = (
        f"Pergunta: {query}\n\n"
        f"Trechos:\n{context}\n\n"
        f"Resposta:"
    )

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
        max_tokens=max_tokens,
        timeout=timeout,
        model_kwargs=extra_kwargs,
    )

    response = await asyncio.to_thread(llm.invoke, [
        {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    content = getattr(response, "content", str(response))
    if not isinstance(content, str):
        content = str(content)
    return content.strip()


async def _synthesize_rag_answer(query: str, chunks: list) -> str:
    """Sintetiza resposta a partir dos chunks.
    Flash (primary) → Pro (fallback) → raw chunks (last resort).
    """
    if not chunks:
        return "Nao encontrei nada sobre isso na base de conhecimento."

    # --- Tentativa 1: V4 Flash (thinking disabled) ---
    try:
        answer = await _call_llm_synthesis(
            model="deepseek-v4-flash",
            query=query, chunks=chunks,
            max_tokens=600, timeout=15,
            extra_kwargs={"thinking": {"type": "disabled"}},
        )
        if answer and len(answer.strip()) >= 20:
            return answer
    except Exception as exc:
        logger.warning("RAG synthesis Flash failed: %s", exc)

    # --- Tentativa 2: V4 Pro (thinking disabled) ---
    try:
        answer = await _call_llm_synthesis(
            model="deepseek-v4-pro",
            query=query, chunks=chunks,
            max_tokens=600, timeout=20,
            extra_kwargs={"thinking": {"type": "disabled"}},
        )
        if answer and len(answer.strip()) >= 20:
            return answer
    except Exception as exc:
        logger.warning("RAG synthesis Pro fallback failed: %s", exc)

    # --- Fallback 3: dump cru de chunks ---
    return _fallback_raw_chunks(chunks)


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
    extra = payload.get("extra", {}) or {}

    if not text.strip():
        return await _run_rag(payload)

    # Fast path: listar documentos da base (somente se nao for query de conteudo, busca ou exclusao)
    t = text.lower()
    _CONTENT_MARKERS = ("diz", "fala", "capitulo", "artigo", "lei", "sobre", "resuma", "explique", "qual o", "quais os")
    _SEARCH_MARKERS = ("busque", "buscar", "procure", "procurar", "pesquise", "pesquisar", "ache", "achar", "encontre", "encontrar")
    has_list_kw = any(kw in t for kw in _LIST_KEYWORDS)
    has_content = any(mk in t for mk in _CONTENT_MARKERS)
    has_search = any(mk in t for mk in _SEARCH_MARKERS)
    has_delete = any(kw in t for kw in _DELETE_MARKERS)
    if has_list_kw and not has_content and not has_search and not has_delete:
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
                "Nao entendi se voce quer buscar no:\n\n"
                "• Banco semantico (editais, leis, teses que indexei)\n"
                "• Google Drive (seus arquivos, PPTs, planilhas)\n\n"
                "E so me dizer: 'banco semantico' ou 'drive'?"
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "doc-disambiguator",
                "needs_clarification": True,
            },
        }

    if has_delete and decision == "rag":
        from agent_orchestration.knowledge_retriever import _list_known_sources
        sources = await _list_known_sources(phone)
        if sources:
            t_lower = text.lower()
            for source in sorted(sources, key=len, reverse=True):
                if source.lower() in t_lower:
                    from tool_registry import get_tool
                    delete_fn = get_tool("knowledge.delete")
                    result = await delete_fn(source_title=source, phone=phone)
                    deleted = result.get("deleted", 0)
                    if deleted > 0:
                        return {
                            "reply": f"Feito! Removi '{source}' da base de conhecimento.",
                            "delay_ms": 0,
                            "presence": "composing",
                            "metadata": {"agent_id": "agent-knowledge-retriever", "deleted_count": deleted, "source_title": source, "skip_image_report": True},
                        }
                    return {
                        "reply": f"Nao encontrei '{source}' na base de conhecimento.",
                        "delay_ms": 0,
                        "presence": "composing",
                        "metadata": {"agent_id": "agent-knowledge-retriever", "deleted_count": 0, "skip_image_report": True},
                    }
        from pipelines._executor import run_agent
        return await run_agent("agent-knowledge-retriever", text, payload, extra)

    if decision == "drive":
        return await _run_drive(payload)
    return await _run_rag(payload)
