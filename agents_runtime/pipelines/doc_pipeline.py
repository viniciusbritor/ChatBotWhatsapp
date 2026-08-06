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
    "exclua", "excluir", "limpe", "limpar",
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
        lista = "\n".join(f"• {s.get('document_title', s.get('source_title', ''))}" for s in sources)
        prompt = f"Pergunte sobre qualquer um deles! Ex: 'o que diz {sources[0].get('document_title', sources[0].get('source_title',''))}?'" if sources else ""
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
    if any(kw in t for kw in _DELETE_MARKERS):
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

    import re as _re
    _DOC_EXT_RE = _re.compile(
        r'\.(?:pdf|docx|xlsx|txt|md|csv)\b', _re.IGNORECASE,
    )
    if _DOC_EXT_RE.search(text) and not any(kw in t for kw in _DRIVE_ONLY_KEYWORDS):
        _QUESTION_HINTS = (
            "me diga", "comente", "explique", "sobre o que", "qual a",
            "qual o", "o que é", "o que e", "resuma", "fale sobre",
            "conceito", "quem é", "quem e", "introducao", "introdução",
            "resumo", "conteudo", "conteúdo", "o que diz",
        )
        if any(kw in t for kw in _QUESTION_HINTS):
            return "rag"
        return "clarify"

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

        resolved_source = None
        filters = result.get("filters") or {}
        if isinstance(filters, dict):
            resolved_source = filters.get("source_title")

        if result.get("clarification_prompt") and not resolved_source:
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
            if not resolved_source:
                try:
                    from agent_orchestration.knowledge_retriever import _list_known_sources
                    sources = await _list_known_sources(phone)
                    if sources and len(sources) <= 2:
                        resolved_source = sources[0].get("source_title", sources[0]) if isinstance(sources[0], dict) else sources[0]
                except Exception:
                    pass
            if resolved_source:
                full_text = await _retrieve_full_document(phone, resolved_source)
                if full_text and len(full_text.strip()) >= 500:
                    resposta = await _synthesize_full_document(text, full_text, resolved_source)
                    await ack_task
                    return {
                        "reply": resposta,
                        "delay_ms": 500,
                        "presence": "composing",
                        "metadata": {"agent_id": "agent-knowledge-retriever", "mode": "full_document", "source_title": resolved_source, "skip_image_report": True},
                    }
            await ack_task
            return {
                "reply": "Nao encontrei nada sobre isso na base de conhecimento.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "count": 0, "skip_image_report": True},
            }

        # Etapa 1: se documento especifico foi resolvido, usa texto completo

        full_text = ""
        if resolved_source:
            full_text = await _retrieve_full_document(phone, resolved_source)

        if full_text and len(full_text.strip()) >= 500:
            resposta = await _synthesize_full_document(text, full_text, resolved_source)
            await ack_task
            return {
                "reply": resposta,
                "delay_ms": 500,
                "presence": "composing",
                "metadata": {
                    "agent_id": "agent-knowledge-retriever",
                    "count": len(chunks),
                    "scope": result.get("scope", "private"),
                    "mode": "full_document",
                    "source_title": resolved_source,
                    "skip_image_report": True,
                },
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


async def _retrieve_full_document(
    phone: str,
    source_title: str,
    max_chars: int = 12000,
) -> str:
    """Busca texto completo de um documento nomeado no plain collection.

    Quando o usuario nomeia um documento especifico ('a dissertacao',
    'a tese vinicius'), o RAG por chunks perde contexto. Este path
    busca todos os chunks do plain collection, ordena por chunk_index,
    concatena (respeitando max_chars) e devolve o texto completo.
    """
    if not phone or not source_title:
        return ""
    try:
        from core.rag import KNOWLEDGE_DATABASE, _get_firestore, _owner_hash
        db = _get_firestore()
        if db is None:
            return ""
        owner_hash = _owner_hash(phone)

        def fetch() -> list:
            return list(
                db.collection(KNOWLEDGE_DATABASE)
                .where("scope", "==", "private")
                .where("owner_hash", "==", owner_hash)
                .where("source_title", "==", source_title)
                .stream()
            )

        import asyncio as _asyncio
        docs = await _asyncio.to_thread(fetch)
        if not docs:
            return ""

        ordered = []
        for d in docs:
            data = d.to_dict() or {}
            ordered.append((int(data.get("chunk_index", 0)), data.get("text_content", "")))
        ordered.sort(key=lambda x: x[0])

        parts = []
        total = 0
        for _, text in ordered:
            clean = text.strip()
            if not clean:
                continue
            if total + len(clean) > max_chars:
                break
            parts.append(clean)
            total += len(clean)

        from core.text_cleaner import clean_portuguese
        return clean_portuguese("\n\n".join(parts))
    except Exception as exc:
        logger.warning("full_document_retrieval_failed: %s", exc)
        return ""


async def _synthesize_full_document(query: str, full_text: str, source_title: str) -> str:
    """Sintetiza resposta a partir do texto COMPLETO do documento.

    Diferente do chunk-based, o LLM recebe ate 12000 chars do documento
    inteiro e pode responder com contexto real, nao fragmentos.
    """
    from langchain_openai import ChatOpenAI

    api_key = (os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
    if not api_key:
        return _fallback_raw_chunks([{"source": source_title, "text": full_text[:1500]}])

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()

    user_prompt = (
        f"Pergunta: {query}\n\n"
        f"Conteudo do documento '{source_title}':\n"
        f"{full_text[:12000]}\n\n"
        f"Resposta:"
    )

    try:
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,
            max_tokens=700,
            timeout=30,
            model_kwargs={"thinking": {"type": "disabled"}},
        )
        response = await asyncio.to_thread(llm.invoke, [
            {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        content = getattr(response, "content", str(response))
        if isinstance(content, str) and len(content.strip()) >= 30:
            return content.strip()
    except Exception as exc:
        logger.warning("full_document synthesis failed: %s", exc)

    return _fallback_raw_chunks([{"source": source_title, "text": full_text[:1500]}])


_SYNTHESIS_SYSTEM_PROMPT = (
    "Voce e a Jennifer, assistente virtual no WhatsApp. "
    "Use APENAS os trechos abaixo para responder a pergunta do usuario. "
    "NAO invente informacao que nao esta nos trechos. "
    "Se os trechos nao contiverem a resposta, diga que nao encontrou. "
    "Responda em portugues brasileiro.\n\n"
    "FORMATACAO (WhatsApp):\n"
    "- Use *negrito* para titulos, conceitos-chave e nomes de arquivos. "
    "Ex: *Tese Vinicius.pdf*\n"
    "- Use _italico_ para termos tecnicos ou estrangeiros.\n"
    "- Use bullets com • para listas. Ex:\n"
    "  • Primeiro item\n"
    "  • Segundo item\n"
    "- Separe ideias diferentes com linha em branco (paragrafo).\n"
    "- Dados numericos ou comparacoes: use formato tabular com "
    "espacamento fixo (fonte monospace). Ex:\n"
    "  Variavel      | Valor  | Unidade\n"
    "  Temperatura   | 25.3   | C\n"
    "- Limite: maximo 15 linhas no total. Seja conciso.\n"
    "- Cite a fonte entre colchetes no inicio: [fonte.pdf]"
)


def _fallback_raw_chunks(chunks: list) -> str:
    """Fallback: dump estruturado de chunks com clean_portuguese aplicado."""
    from core.text_cleaner import clean_portuguese
    lines = []
    for c in chunks[:4]:
        clean = clean_portuguese(c.get("text", "")).strip()
        if not clean:
            continue
        source = c.get("source", "?")
        section = c.get("section_title", "")
        prefix = f"[{source[:40]}]"
        if section:
            prefix = f"[{source[:40]} | {section}]"
        lines.append(f"{prefix} {clean[:300]}")
    return "\n\n".join(lines) if lines else "Nao encontrei nada sobre isso na base de conhecimento."


def _format_chunk_context(c: dict) -> str:
    section = c.get("section_title", "")
    source = c.get("source", "?")
    text = c.get("text", "")[:1500]
    if section:
        return f"[Fonte: {source} | Seção: {section}] {text}"
    return f"[Fonte: {source}] {text}"


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
        _format_chunk_context(c) for c in chunks[:5]
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


_CONTENT_HINT_KEYWORDS = (
    "resumo", "abstract", "introdu", "propoe", "propõe", "apresenta",
    "este trabalho", "este estudo", "esta disserta", "este documento",
    "o objetivo", "os objetivos", "metodologia", "resultados",
    "conclui", "conclus", "tema", "trata", "aborda", "objetivo",
    "palavras-chave", "palavras chave", "keywords",
)


def _prioritize_content_chunks(query: str, chunks: list) -> list:
    """Reordena chunks priorizando conteudo substantivo para about queries.

    Quando a query pergunta 'sobre o que e / qual o tema / quem e o autor',
    chunks de resumo/introducao/abstract sao mais relevantes que a ficha
    catalografica. Detecta pelo section_title e pelo texto do chunk.
    """
    from agent_orchestration.knowledge_retriever import _is_about_query
    if not chunks or not _is_about_query(query):
        return chunks

    def score(c: dict) -> int:
        s = 0
        section = (c.get("section_title") or "").lower()
        text = (c.get("text") or "").lower()
        if any(kw in section for kw in ("resumo", "abstract", "introdu")):
            s += 3
        if any(kw in section for kw in ("conclus", "metodologia", "referen")):
            s += 2
        if any(kw in text for kw in _CONTENT_HINT_KEYWORDS):
            s += 1
        return s

    return sorted(chunks, key=score, reverse=True)


async def _synthesize_rag_answer(query: str, chunks: list) -> str:
    """Sintetiza resposta a partir dos chunks.
    Flash (primary) → Pro (fallback) → raw chunks (last resort).
    """
    if not chunks:
        return "Nao encontrei nada sobre isso na base de conhecimento."

    chunks = _prioritize_content_chunks(query, chunks)

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
    _CONTENT_MARKERS = ("diz", "fala", "capitulo", "artigo", "lei", "sobre", "resuma", "explique", "qual o", "quais os", "comente", "comentar", "descreva", "introducao", "introdução", "conteudo", "conteúdo")
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

    if has_delete:
        if any(kw in t for kw in _DRIVE_ONLY_KEYWORDS):
            decision = "drive"
        else:
            decision = "rag"
    else:
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
                source_base = source.lower().rsplit(".", 1)[0]
                if source.lower() in t_lower or source_base in t_lower:
                    instance = payload.get("instance", "jennifer")
                    extra = payload.get("extra", {}) or {}
                    try:
                        from core.delay_calculator import calculate_delay_ms
                        from core.evolution_client import send_text
                        ack_msg = f"Entendido, vou remover '{source}' da base de conhecimento..."
                        delay_ms = max(1500, calculate_delay_ms(ack_msg))
                        await send_text(
                            instance=instance,
                            phone=phone,
                            text=ack_msg,
                            delay_ms=delay_ms,
                            presence="composing",
                            remote_jid=extra.get("remote_jid", ""),
                        )
                    except Exception:
                        pass
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
        doc_list = ", ".join(f"'{s}'" for s in sources[:5])
        return {
            "reply": (
                f"Nao identifiquei qual documento da base voce quer apagar. "
                f"Documentos disponiveis: {doc_list}. "
                "Pode citar o nome exato do arquivo?"
            ),
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {
                "agent_id": "agent-knowledge-retriever",
                "needs_clarification": True,
                "skip_image_report": True,
            },
        }

    if decision == "drive":
        return await _run_drive(payload)
    return await _run_rag(payload)
