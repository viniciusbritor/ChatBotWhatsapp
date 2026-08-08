"""Knowledge retriever (Fase H).

Decides *whether* a user message refers to knowledge previously stored in
Firestore Vector, picks the correct scope (private vs group), and returns
matching chunks. When the message is in a group and the relevant document
is private, creates a ``pending_action`` of type
``share_private_knowledge_in_group`` so the user can explicitly approve
sharing before the content is exposed.

Architecture:

- **Heuristic** (`_looks_like_rag_query`): detects obvious RAG keywords.
- **LLM tie-breaker** (DeepSeek V4 Flash): decides only when the
  heuristic is inconclusive and the message has enough context.
- **Scope decision** (`_decide_scope`): private vs group based on JID.
- **Cross-scope prompt** (`_maybe_request_share`): creates the
  ``pending_action`` payload when needed.

Retrieval reuses ``core.rag.search_legal_knowledge`` (private) and
``tools.group.search_group_knowledge`` (group). Threshold comes from
``RAG_RETRIEVE_MIN_SCORE`` (default 0.5).
"""
from __future__ import annotations

import asyncio
import unicodedata
import hashlib
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from core.rag import RAG_RETRIEVE_MIN_SCORE, search_legal_knowledge
from tools.group import search_group_knowledge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory retrieval cache (Fase I subfase 2)
# ---------------------------------------------------------------------------
# Lives in the Cloud Run process memory. Max 256 entries; LRU-evicted
# on overflow. TTL 5 min (configurable via RAG_CACHE_TTL_SEC).
# Survives only as long as the container instance is warm.

_RETRIEVAL_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SEC = int(os.getenv("RAG_CACHE_TTL_SEC", "300"))


def _cache_key(
    envelope: Dict[str, Any],
    query: str,
    limit: int,
    min_score: float,
) -> str:
    phone = _extract_phone(envelope) if envelope else ""
    return hashlib.md5(
        f"{phone}|{_normalize(query)}|{limit}|{min_score}".encode("utf-8")
    ).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _RETRIEVAL_CACHE.get(key)
    if not entry:
        return None
    if (time.time() - entry["ts"]) > _CACHE_TTL_SEC:
        _RETRIEVAL_CACHE.pop(key, None)
        return None
    return entry["result"]


def _cache_set(key: str, result: Dict[str, Any]) -> None:
    _RETRIEVAL_CACHE[key] = {"ts": time.time(), "result": result}
    if len(_RETRIEVAL_CACHE) > 256:
        oldest = min(_RETRIEVAL_CACHE.items(), key=lambda kv: kv[1]["ts"])
        _RETRIEVAL_CACHE.pop(oldest[0], None)


def _normalize(text: str) -> str:
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents).strip()


_TOC_LINE_RE = re.compile(r"^.{5,80}\.{3,}\s*\d+\s*$")


def _is_toc_chunk(text: str) -> bool:
    if not text or len(text) < 20:
        return False
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    toc_lines = 0
    for line in lines:
        if _TOC_LINE_RE.match(line.strip()):
            toc_lines += 1
    return toc_lines >= max(1, len(lines) * 0.5)


def _results_are_toc_only(chunks: List[Dict[str, Any]]) -> bool:
    if not chunks:
        return False
    if len(chunks) == 1 and _is_toc_chunk(chunks[0].get("text", "")):
        return True
    toc_count = sum(1 for c in chunks if _is_toc_chunk(c.get("text", "")))
    return toc_count >= len(chunks) * 0.5


async def _toc_escape(
    phone: str,
    hits: Dict[str, Any],
    resolved_source: Optional[str] = None,
) -> Dict[str, Any]:
    chunks = hits.get("results", [])
    if not _results_are_toc_only(chunks):
        return hits
    source = resolved_source or (chunks[0].get("source", "") if chunks else "")
    if not source or not phone:
        return hits
    full_text = await _fetch_full_document(phone, source)
    if full_text and len(full_text.strip()) >= 500:
        logger.info("toc_escape_activated source=%s chars=%d", source, len(full_text))
        hits["results"] = [{"text": full_text, "score": 0.95, "source": source, "class": "full_document", "group": "full_document"}]
        hits["count"] = 1
        hits["toc_escaped"] = True
    return hits


async def _fetch_full_document(phone: str, source_title: str, max_chars: int = 12000) -> str:
    import asyncio as _asyncio

    try:
        from core.rag import KNOWLEDGE_DATABASE, _get_firestore, _owner_hash
        db = _get_firestore()
        if db is None:
            return ""
        owner_hash = _owner_hash(phone)

        def fetch():
            return list(
                db.collection(KNOWLEDGE_DATABASE)
                .where("scope", "==", "private")
                .where("owner_hash", "==", owner_hash)
                .where("source_title", "==", source_title)
                .stream()
            )

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
        _skip_re = re.compile(
            r"senado federal|mesa diretora|bi[êe]nio|coordena[çc][ãa]o\s+de\s+edi[çc]|"
            r"secretaria de editora|ficha catalogr[áa]fica|suplentes?\s+de\s+secret[áa]rio|"
            r"quarto-secret[áa]rio|presidente|vice-presidente|sum[áa]rio",
            re.IGNORECASE,
        )
        for _, text in ordered:
            clean = text.strip()
            if not clean or _skip_re.search(clean):
                continue
            if total + len(clean) > max_chars:
                break
            parts.append(clean)
            total += len(clean)

        from core.text_cleaner import clean_portuguese

        return clean_portuguese("\n\n".join(parts))
    except Exception as exc:
        logger.warning("toc_escape_fetch_failed: %s", exc)
        return ""


RAG_KEYWORDS_RAW = {
    "memorizei", "memorizado", "memorizada", "memorizou", "memorizaram",
    "indexado", "indexada", "indexados", "no rag", "no vector",
    "base de conhecimento", "knowledge base", "conhecimento",
    "salvou", "salvamos", "gravamos", "guardamos", "armazenamos",
    "ata que", "documento que", "pdf que", "planilha que",
    "docx que", "arquivo que",
    "esse documento", "este documento", "desse documento",
    "deste documento", "o documento", "o arquivo",
    "esse pdf", "esse docx", "essa planilha", "dessa planilha",
    "desse pdf", "desse arquivo", "deste arquivo",
    "sobre o que é", "sobre o que", "do que se trata",
    "qual o tema", "qual é o tema", "de que trata",
    "quem é o autor", "qual o autor", "qual é o autor",
    "quem escreveu", "de quem é", "conteudo do",
    "conteudo da", "conteudo desse", "conteudo deste",
    "busque na sua base", "busque na sua base de conhecimento",
    "use conhecimento", "use a base de conhecimento",
    "consulte a base", "pesquise na memoria",
    "na sua memoria", "o que voce guardou", "o que voce armazenou",
    "o que voce memorizou", "recupere da base", "do que voce lembra",
    "lembre-se", "recorde",
    "como memorizou", "como guardou", "como salvou",
    "voce memorizou", "voce guardou", "voce salvou",
    "vc memorizou", "vc guardou", "vc salvou",
    "que guardou", "que salvou", "que memorizou",
    "do que guardou", "do que salvou", "do que memorizou",
    "qual arquivo", "qual doc", "que arquivo", "que doc",
    "o arquivo que", "o doc que", "do arquivo", "do doc",
    "sobre o arquivo", "sobre o doc", "no arquivo", "no doc",
    "me fala sobre", "me mostra o", "me diga o",
    "conteudo da introducao", "texto da introducao",
    "introducao do", "conteudo do", "resumo do",
    # PT8: queries genericas sobre 'documentos' (sem keyword de Drive)
    "quais documentos", "lista documentos", "lista os documentos",
    "meus documentos", "seus documentos", "todos os documentos",
    "documentos salvos", "documentos memorizados", "documentos indexados",
}

RAG_KEYWORDS = frozenset(_normalize(kw) for kw in RAG_KEYWORDS_RAW)

QUESTION_KEYWORDS = {
    "tem alguma coisa sobre",
    "existe algum documento",
}


_RECENT_INDEXING: Dict[str, float] = {}
RECENT_INDEXING_WINDOW_SEC = int(os.getenv("RECENT_INDEXING_WINDOW_SEC", "1800"))


def register_indexing(scope_key: str) -> None:
    """Marca que um documento foi indexado para este scope.

    ``scope_key`` deve ser:
    - phone (e.g. ``+5511966830020``) para conversa 1:1
    - group_jid (e.g. ``120363...@g.us``) para conversa em grupo

    No fluxo de grupo, o orchestrator registra TANTO o group_jid quanto
    cada phone visto, para que qualquer membro possa consultar.

    Janela definida por ``RECENT_INDEXING_WINDOW_SEC`` (default 1800s =
    30min), configuravel via env var.
    """
    if not scope_key:
        return
    _RECENT_INDEXING[scope_key] = time.time()


def _had_recent_indexing(scope_key: str) -> bool:
    """Retorna True se houve indexing para este scope nos ultimos N segundos."""
    if not scope_key:
        return False
    ts = _RECENT_INDEXING.get(scope_key)
    if not ts:
        return False
    return (time.time() - ts) < RECENT_INDEXING_WINDOW_SEC


def _looks_like_rag_query(text: str) -> bool:
    """Heuristic: explicit RAG keyword present, or a question form.

    Returns True when the message clearly refers to previously stored
    knowledge. Returns False when the message is a command, greeting, or
    unrelated question.
    """
    normalized = _normalize(text)
    if not normalized:
        return False
    if any(kw in normalized for kw in RAG_KEYWORDS):
        return True
    if any(kw in normalized for kw in QUESTION_KEYWORDS):
        return True
    return False


async def _llm_is_rag_query(
    text: str,
    recent_context: str = "",
) -> Optional[bool]:
    """Tie-breaker using DeepSeek V4 Flash. Returns True/False/None.

    ``recent_context`` carries the last 1-2 messages of the phone so
    the LLM can interpret conversational references like "esse documento"
    as RAG queries when the previous turn was about indexing.
    """
    if not text.strip():
        return None
    try:
        from langchain_openai import ChatOpenAI

        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or os.getenv("NVIDIA_API_KEY", "").strip()
            or ""
        )
        if not api_key:
            return None
        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        ).strip()
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=5,
            timeout=8,
            model_kwargs={"extra_body": {"cache_mode": "default"}},
        )
        prompt = (
            "O usuario esta pedindo algo que foi previamente salvo/armazenado "
            "no Firestore Vector (base de conhecimento da Jennifer)?\n"
            "Considere o historico recente para avaliar referencias como "
            "'esse documento' ou 'o que voce memorizou'.\n"
            f"Historico: {recent_context[:300]}\n"
            f"Mensagem: {text.strip()[:400]}\n"
            "Responda apenas 'sim' ou 'nao':"
        )
        result = await asyncio.to_thread(llm.invoke, prompt)
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        cleaned = _normalize(raw).strip(" .!?\":'").lower()
        if cleaned.startswith("sim"):
            return True
        if cleaned.startswith("nao") or cleaned.startswith("não"):
            return False
        return None
    except Exception as exc:
        logger.warning("llm_is_rag_query failed: %s", exc)
        return None


async def is_rag_query(
    text: str,
    recent_context: str = "",
    phone: str = "",
) -> bool:
    """Returns True when the message refers to previously stored knowledge."""
    if _had_recent_indexing(phone):
        return True
    if _looks_like_rag_query(text):
        return True
    llm_answer = await _llm_is_rag_query(text, recent_context=recent_context)
    return bool(llm_answer)


def _is_group(envelope: Dict[str, Any]) -> bool:
    extra = envelope.get("extra", {}) or {}
    return "@g.us" in str(extra.get("remote_jid", ""))


def _is_user_member(db, group_jid: str, phone: str) -> bool:
    """Returns True when ``phone`` is an active member of ``group_jid``."""
    try:
        doc = (
            db.collection("grupos")
            .document(group_jid.replace("/", "_"))
            .collection("membros")
            .document(phone)
            .get()
        )
        if doc.exists:
            return bool(doc.to_dict().get("is_active", False))
    except Exception:
        return False
    return False


def _extract_title_fallback(data: Dict[str, Any]) -> str:
    sec = (data.get("section_title") or "").strip()
    if sec and len(sec) > 10:
        if not re.search(
            r"senado federal|mesa diretora|bi[êe]nio|coordena[çc][ãa]o de edi[çc][õo]es|"
            r"secretaria de editora[çc][ãa]o|ficha catalogr[áa]fica|sum[áa]rio|"
            r"presidente|vice-presidente",
            sec, re.IGNORECASE,
        ):
            return sec[:80]
    src = data.get("source_title") or ""
    base = src.rsplit(".", 1)[0].replace("_", " ").strip()
    return base[:80] if base else src[:80]


async def _list_known_sources(phone: str, limit: int = 10) -> List[Dict[str, str]]:
    """Return distinct documentos com titulo real e source_title.
    
    Extrai document_title do melhor section_title (primeiro nao-front-matter).
    Usado pela UX da listagem e clarification_prompt."""
    try:
        from core.rag import PRIVATE_COLLECTION, _owner_hash

        db_ref = None
        try:
            from core.rag import _get_firestore
            db_ref = _get_firestore()
        except Exception:
            db_ref = None
        if db_ref is None:
            return []

        owner_hash = _owner_hash(phone)
        grouped: Dict[str, str] = {}

        def fetch():
            return list(
                db_ref.collection(PRIVATE_COLLECTION)
                .where("scope", "==", "private")
                .where("owner_hash", "==", owner_hash)
                .limit(300)
                .stream()
            )

        import asyncio as _asyncio
        docs = await _asyncio.to_thread(fetch)
        for doc in docs:
            data = doc.to_dict() or {}
            src = data.get("source_title") or ""
            doc_title = data.get("document_title") or ""
            if src not in grouped:
                grouped[src] = {
                    "document_title": doc_title if doc_title else _extract_title_fallback(data),
                    "class": data.get("class", ""),
                    "group": data.get("group", ""),
                    "theme": data.get("theme", ""),
                    "chunk_count": 0,
                }
            grouped[src]["chunk_count"] += 1

        results: List[Dict[str, str]] = []
        for source_title in sorted(grouped):
            meta = grouped[source_title]
            results.append({
                "source_title": source_title,
                "document_title": meta.get("document_title") or source_title,
                "class": meta.get("class") or "",
                "group": meta.get("group") or "",
                "theme": meta.get("theme") or "",
                "chunk_count": meta.get("chunk_count", 0),
            })
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


async def _list_knowledge_stats(phone: str) -> Dict[str, Any]:
    if not phone:
        return {"stats": {}}
    sources = await _list_known_sources(phone, limit=500)
    class_counts: Dict[str, int] = {}
    group_counts: Dict[str, int] = {}
    total_docs = 0
    total_chunks = 0
    for s in sources:
        if not isinstance(s, dict):
            continue
        total_docs += 1
        total_chunks += s.get("chunk_count", 0)
        cls = s.get("class") or "outros"
        grp = s.get("group") or "outros"
        class_counts[cls] = class_counts.get(cls, 0) + 1
        group_counts[f"{cls}/{grp}"] = group_counts.get(f"{cls}/{grp}", 0) + 1
    return {
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "by_class": dict(sorted(class_counts.items(), key=lambda x: -x[1])),
        "by_group": dict(sorted(group_counts.items(), key=lambda x: -x[1])),
    }


def _build_clarification_prompt(known_sources: List[Dict[str, str]], query: str) -> str:
    """Mensagem de clarification quando retrieval retorna 0 hits.

    Lista os titulos reais conhecidos do owner se houver, dando
    ao user uma ancora concreta para refinar a busca.
    """
    base = "N\u00e3o encontrei nada sobre isso no que memorizei at\u00e9 agora."
    if known_sources:
        names = []
        for s in known_sources[:8]:
            if isinstance(s, dict):
                names.append(s.get("document_title") or s.get("source_title", ""))
            else:
                names.append(str(s))
        lista = ", ".join(f"'{n}'" for n in names)
        return (
            f"{base} Voc\u00ea tem esses documentos salvos na sua base: {lista}. "
            "Quer tentar uma busca mais espec\u00edfica, citando o nome do "
            "arquivo ou outro termo?"
        )
    return f"{base} Quer me dar mais detalhes ou outro termo?"


def _extract_group_jid(envelope: Dict[str, Any]) -> str:
    extra = envelope.get("extra", {}) or {}
    remote_jid = str(extra.get("remote_jid", ""))
    if "@g.us" in remote_jid:
        return remote_jid.split("@")[0] + "@g.us"
    return ""


def _extract_phone(envelope: Optional[Dict[str, Any]]) -> str:
    """Extrai o phone do user a partir do envelope.

    Aceita 3 formatos (em ordem de precedencia):
    1. webhook canonico: envelope["phone"]
    2. DeepAgents state: envelope["user"]["phone"]
    3. vazio (sinal de bug ou envelope malformado).

    Patch 01/08/2026: fallback adicionado para o formato interno
    do DeepAgents harness (que monta o state do LangGraph com
    user aninhado). Sem fallback, _owner_hash("") virava hash de
    string vazia e o find_nearest buscava owner_hash inexistente
    no Firestore -> 0 hits para todo RAG privado via DeepAgents.
    """
    if not envelope or not isinstance(envelope, dict):
        return ""
    phone = str(envelope.get("phone") or "")
    if phone:
        return phone
    user = envelope.get("user")
    if isinstance(user, dict):
        phone = str(user.get("phone") or "")
        if phone:
            return phone
    # Patch 02/08/2026: formato flat do DeepAgents state v2 (atual 0.6.12)
    # tem user_phone na raiz, nao em user.phone.
    phone = str(envelope.get("user_phone") or "")
    if phone:
        return phone
    phone = str(envelope.get("sender_phone") or "")
    if phone:
        return phone
    logger.warning("extract_phone_empty envelope_keys=%s", list(envelope.keys())[:8])
    return ""


_ABOUT_QUERY_MARKERS = (
    "sobre o que", "do que se trata", "do que trata",
    "me explique", "me resuma", "qual o tema", "qual o assunto",
    "o que e", "o que sao", "sobre o que e", "resumo do",
    "conteudo do", "me fala sobre", "qual o conteudo",
    "qual e o conteudo", "qual o conteudo de",
    "qual o resumo", "sobre qual tema", "qual e o tema",
    "explique sobre", "resuma o", "resuma a",
    "fale sobre", "o que voce sabe sobre", "o que vc sabe sobre",
)


def _is_about_query(query: str) -> bool:
    return any(m in _normalize(query) for m in _ABOUT_QUERY_MARKERS)


_DOC_HINT = re.compile(
    r"[\w\u00C0-\u017F][\w\-\.\(\)\u00C0-\u017F ]*\.(?:pdf|docx|xlsx|txt|md|csv)",
    re.IGNORECASE,
)


_FILENAME_STOPWORDS = frozenset({
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "pra", "por", "pelo", "pela", "com", "sem",
    "que", "qual", "quais", "quem", "quando", "onde", "como",
    "sobre", "apos", "depois", "antes", "entre",
    "arquivo", "arquivos", "documento", "documentos", "doc", "docs",
    "pdf", "planilha", "planilhas", "relatorio", "relatorios",
    "este", "esta", "esse", "essa", "isto", "isso", "aquilo",
    "tem", "tenho", "tinha", "tens",
    "fala", "fale", "falei", "falam", "me", "te", "se",
    "do", "da", "e", "ou", "mas", "pois",
    "chamado", "chamada", "nome", "titulo", "conteudo",
    "informacao", "informacoes", "dados", "lista",
    "todos", "todas", "todo", "toda", "algum", "alguma",
    "alguns", "algumas", "qualquer", "quaisquer",
})


def _extract_source_title_hint(query: str) -> Optional[str]:
    """Extract the longest filename-like token from the query.

    The regex accepts internal spaces and Latin-1 accented letters so
    that filenames like 'dissertação vinicius.pdf' are captured in full.

    After the regex match, leading stopwords/prepositions are trimmed
    so that phrases like 'me fale sobre dissertação vinicius.pdf' yield
    'dissertação vinicius.pdf' instead of the whole prefix.
    """
    raw = (query or "").strip()
    if not raw:
        return None
    match = _DOC_HINT.search(raw)
    if not match:
        return None
    candidate = match.group(0).strip(".,;:!?()\"' \t\n\r\u00A0")
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate:
        return None

    words = candidate.split(" ")
    while len(words) > 1 and _normalize(words[0]) in _FILENAME_STOPWORDS:
        words.pop(0)
    candidate = " ".join(words)
    return candidate or None


CLASS_HINTS = {
    "legal": ["lei", "cdc", "codigo de defesa", "legislacao", "regulamento"],
    "edital": ["edital", "licitacao", "pregao", "concurso"],
    "jurisprudencia": ["jurisprudencia", "acordao", "sumula", "decisao judicial"],
    "manual": ["manual", "procedimento", "pop", "sop", "runbook"],
    "empresa": ["empresa", "processo interno", "politica interna"],
    "corporativo": ["segmento", "indústria", "setor"],
    "academico": ["livro", "artigo", "paper", "tese", "dissertacao", "probabilidade"],
    "saude": ["saude", "medicina", "bula", "protocolo clinico"],
    "financeiro": ["financeiro", "balanço", "relatorio", "orcamento"],
    "outros": [],
}


def _extract_class_hint(query: str) -> Optional[str]:
    text = _normalize(query)
    scores: Dict[str, int] = {}
    for cls, keywords in CLASS_HINTS.items():
        for kw in keywords:
            if kw in text:
                scores[cls] = scores.get(cls, 0) + 1
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


async def _match_source_title_dynamic(phone: str, query: str) -> Optional[str]:
    """Auto-discovery: match query terms against known Firestore doc filenames.

    No hardcoded aliases. Works with ANY document indexed in Firestore.
    Requires 2+ non-stopword words from the query to match words in a
    known document filename.
    """
    if not phone or not query:
        return None
    try:
        sources = await _list_known_sources(phone, limit=50)
        if not sources:
            return None
        query_words = set(
            w.strip(".,;:!?()\"'\u00A0")
            for w in _normalize(query).split()
            if w.strip(".,;:!?()\"'\u00A0") and w not in _FILENAME_STOPWORDS
        )
        if len(query_words) < 2:
            return None
        best_match = None
        best_score = 0
        for src in sources:
            source_name = src["source_title"] if isinstance(src, dict) else str(src)
            src_root = _normalize(source_name).rsplit(".", 1)[0]
            src_words = set(re.split(r'[\s_\-\.\+]+', src_root))
            common = query_words & src_words
            score = len(common)
            if score > best_score:
                best_score = score
                best_match = source_name
        return best_match if best_score >= 2 else None
    except Exception:
        return None


_LLM_ENRICH_PROMPT = (
    "Analise a pergunta do usuario e extraia:\n"
    "1. enriched_query: a query em portugues com os termos principais "
    "para busca semantica (max 100 chars)\n"
    "2. source_hint: palavra-chave que identifica o documento mencionado "
    "('cdc', 'lgpd', 'tese', 'dissertacao', 'edital', 'lei', etc) ou vazio\n"
    "3. class_hint: categoria do documento ('legal', 'academico', "
    "'edital', 'financeiro', 'saude', 'manual', 'outros') ou vazio\n\n"
    "Responda APENAS com um JSON: "
    '{{"enriched_query":"...", "source_hint":"...", "class_hint":"..."}}\n\n'
    "Pergunta: {query}"
)


async def _llm_enrich_query(query: str) -> Dict[str, str]:
    """Extrai assunto principal, source hint e class hint via DeepSeek Flash.

    Usado como complemento ao pipeline de hints: quando heuristica e
    aliases nao encontram source_title ou class, o LLM preenche as lacunas.
    Retorna dict com enriched_query, source_hint, class_hint.
    Se o LLM falhar, enriched_query = query original (fallback transparente).
    """
    if not query.strip():
        return {"enriched_query": query, "source_hint": "", "class_hint": ""}

    try:
        api_key = (os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
        if not api_key:
            return {"enriched_query": query, "source_hint": "", "class_hint": ""}

        from langchain_openai import ChatOpenAI

        base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        ).strip()

        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=150,
            timeout=8,
            model_kwargs={"extra_body": {"cache_mode": "default"}},
        )

        prompt = _LLM_ENRICH_PROMPT.format(query=query.strip()[:300])
        result = await asyncio.to_thread(llm.invoke, prompt)
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )

        import json as _json
        match = re.search(r"\{[^}]+\}", raw)
        if match:
            data = _json.loads(match.group(0))
            return {
                "enriched_query": str(data.get("enriched_query", "") or "").strip()[:150] or query,
                "source_hint": str(data.get("source_hint", "") or "").strip(),
                "class_hint": str(data.get("class_hint", "") or "").strip(),
            }

        return {"enriched_query": query, "source_hint": "", "class_hint": ""}
    except Exception as exc:
        logger.warning("llm_enrich_query failed: %s", exc)
        return {"enriched_query": query, "source_hint": "", "class_hint": ""}


async def _extract_query_hints(phone: str, query: str) -> Dict[str, str]:
    hints: Dict[str, str] = {}
    source_title = (
        _extract_source_title_hint(query)
        or await _match_source_title_dynamic(phone, query)
    )
    if source_title:
        hints["source_title"] = source_title
    cls = _extract_class_hint(query)
    if cls:
        hints["class"] = cls

    # LLM enrichment preenche lacunas e gera enriched_query
    enrichment = await _llm_enrich_query(query)
    hints["enriched_query"] = enrichment["enriched_query"]
    if not hints.get("source_title") and enrichment.get("source_hint"):
        hints["source_title"] = enrichment["source_hint"]
    if not hints.get("class") and enrichment.get("class_hint"):
        hints["class"] = enrichment["class_hint"]

    return hints


async def _retrieve_private(
    phone: str,
    query: str,
    limit: int,
    min_score: float,
    source_title: Optional[str] = None,
    class_: Optional[str] = None,
    group: Optional[str] = None,
    language: Optional[str] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    result = await search_legal_knowledge(
        phone=phone,
        query=query,
        k=limit,
        min_score=min_score,
        source_title=source_title,
        class_=class_,
        group=group,
        language=language,
        since=since,
    )
    # Fallback 1: se o filtro de classe zerou a busca, tentar sem ele
    chunks = result.get("results", []) if isinstance(result, dict) else []
    if not chunks and class_:
        logger.info("class_filter_blocked_retrieval class=%s — retrying without", class_)
        result = await search_legal_knowledge(
            phone=phone,
            query=query,
            k=limit,
            min_score=min_score,
            source_title=source_title,
            class_=None,
            group=group,
            language=language,
            since=since,
        )
        chunks = result.get("results", []) if isinstance(result, dict) else []
    # Fallback 2: se ainda 0 hits, reduzir threshold progressivamente (piso 0.35)
    if not chunks and min_score > 0.35:
        relaxed = max(0.35, round(min_score * 0.6, 2))
        logger.info("score_threshold_blocked_retrieval min_score=%s — retrying with %s", min_score, relaxed)
        result = await search_legal_knowledge(
            phone=phone,
            query=query,
            k=limit,
            min_score=relaxed,
            source_title=source_title,
            class_=class_,
            group=group,
            language=language,
            since=since,
        )
        chunks = result.get("results", []) if isinstance(result, dict) else []
    return {
        "scope": "private",
        "results": chunks,
        "count": len(chunks),
        "min_score": min_score,
        "owner_hash": result.get("owner_hash") if isinstance(result, dict) else None,
        "filters": result.get("filters") if isinstance(result, dict) else None,
    }


async def _retrieve_group(
    group_jid: str,
    query: str,
    limit: int,
    min_score: float,
) -> Dict[str, Any]:
    result = await search_group_knowledge(
        group_jid=group_jid, query=query, limit=limit
    )
    raw_results = result.get("results", []) if isinstance(result, dict) else []
    filtered = [
        item for item in raw_results
        if float(item.get("score", 0.0)) >= min_score
    ]
    return {
        "scope": "group",
        "results": filtered,
        "count": len(filtered),
        "min_score": min_score,
        "group_jid": group_jid,
    }


async def _rerank_with_llm(
    query: str,
    chunks: List[Dict[str, Any]],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """Re-rank retrieved chunks using DeepSeek V4 Flash.

    Takes the top-k (k=10) chunks and re-orders them by relevance to
    the query using a small LLM. Returns the top_n (3) most relevant.
    The LLM does not generate text; it only returns a JSON array of
    indices, e.g., [3, 0, 7, 1, 9].
    """
    if len(chunks) <= top_n:
        return chunks
    if not os.getenv("DEEPSEEK_API_KEY"):
        return chunks
    try:
        from langchain_openai import ChatOpenAI

        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        )
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=base_url,
            temperature=0,
            max_tokens=200,
            timeout=10,
            model_kwargs={"extra_body": {"cache_mode": "default"}},
        )
        chunk_lines = []
        for i, c in enumerate(chunks):
            text = (c.get("text") or "")[:500]
            chunk_lines.append(f"[{i}] (score={c.get('score', 0):.2f}) {text}")
        chunks_blob = "\n".join(chunk_lines)
        about_hint = ""
        if _is_about_query(query):
            about_hint = (
                "\nIMPORTANTE: A query pergunta SOBRE O QUE E o documento. "
                "Priorize chunks com CONTEUDO SUBSTANTIVO (resumo, introducao, "
                "metodologia, conclusao, resultados) sobre chunks com METADADOS "
                "(folha de rosto, agradecimentos, ficha catalografica, creditos, "
                "cabecalhos institucionais). "
                "Chunks de cabecalho so devem ser priorizados se contiverem "
                "informacao substantiva sobre o tema do documento.\n"
            )
        prompt = (
            "Re-ordene os chunks abaixo por relevancia para a query. "
            "Retorne SOMENTE um JSON array de indices, do mais "
            f"relevante para o menos relevante, max {top_n} itens."
            f"{about_hint}\n"
            f"Query: {query}\n\n"
            f"Chunks:\n{chunks_blob}\n\n"
            f"Resposta (JSON array de {top_n} indices):"
        )
        result = await asyncio.to_thread(
            llm.invoke,
            [{"role": "user", "content": prompt}],
        )
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        import json as _json
        match = re.search(r"\[[\d,\s]+\]", raw)
        if not match:
            return chunks[:top_n]
        indices = _json.loads(match.group(0))
        re_ranked = []
        for idx in indices:
            if 0 <= idx < len(chunks):
                re_ranked.append(chunks[idx])
        for c in chunks:
            if c not in re_ranked:
                re_ranked.append(c)
        return re_ranked[:top_n]
    except Exception as exc:
        logger.warning("LLM re-ranking failed: %s", exc)
        return chunks[:top_n]


async def _maybe_request_share(
    phone: str,
    group_jid: str,
    query: str,
) -> Optional[Dict[str, Any]]:
    """Create the cross-scope pending_action.

    Returns the pending action dict if created, else None.
    """
    if not phone or not group_jid:
        return None
    try:
        from core.pending_actions import (
            PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
            set_pending_action,
        )
        return await set_pending_action(
            phone,
            PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
            {
                "phone": phone,
                "group_jid": group_jid,
                "query": query,
                "source": "knowledge_retriever",
            },
            ttl_sec=300,
        )
    except Exception as exc:
        logger.warning("share_private_knowledge pending_action failed: %s", exc)
        return None


async def _request_feedback(
    phone: str,
    query: str,
) -> Optional[Dict[str, Any]]:
    """Create the retrieval_feedback pending_action.

    Triggered when retrieve() returns needs_clarification=True. The
    bot can then ask the user to refine the query or provide more
    context. Returns the pending action dict if created, else None.
    """
    if not phone:
        return None
    try:
        from core.pending_actions import (
            PENDING_ACTION_RETRIEVAL_FEEDBACK,
            set_pending_action,
        )
        return await set_pending_action(
            phone,
            PENDING_ACTION_RETRIEVAL_FEEDBACK,
            {
                "phone": phone,
                "query": query,
                "source": "knowledge_retriever",
            },
            ttl_sec=180,
        )
    except Exception as exc:
        logger.warning("retrieval_feedback pending_action failed: %s", exc)
        return None


async def retrieve(
    envelope: Dict[str, Any],
    query: str,
    *,
    limit: Optional[int] = None,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Decide scope and retrieve. Returns a structured dict.

    Shape::

        {
          "scope": "private" | "group" | "none",
          "decision": "private" | "group" | "group_private_share_pending"
                     | "denied" | "no_results" | "needs_clarification",
          "results": [...],
          "count": int,
          "needs_share_prompt": bool,
          "needs_clarification": bool,
          "clarification_prompt": str | None,
          "share_pending_action": dict | None,
          "reason": str | None,
          "filters": {...},
        }
    """
    effective_limit = int(limit) if limit is not None else int(
        os.getenv("RAG_RETRIEVE_K", "10")
    )
    threshold = float(min_score) if min_score is not None else float(
        os.getenv("RAG_RETRIEVE_MIN_SCORE", str(RAG_RETRIEVE_MIN_SCORE))
    )
    cache_key = _cache_key(envelope, query, effective_limit, threshold)
    cached = _cache_get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["cache_hit"] = True
        return cached
    is_group = _is_group(envelope)
    phone = _extract_phone(envelope)
    group_jid = _extract_group_jid(envelope) if is_group else ""
    hints = await _extract_query_hints(phone, query)
    if not hints.get("source_title") and phone:
        sources = await _list_known_sources(phone)
        if sources:
            from agent_orchestration.source_title_resolver import resolve
            hints["source_title"] = await resolve(sources, query) or hints.get("source_title")
    enriched_query = hints.get("enriched_query") or query
    started = time.monotonic()
    query_hash = hashlib.md5(
        (phone + ":" + _normalize(query)).encode("utf-8")
    ).hexdigest()[:12]
    logger.info(
        "retriever_decision",
        extra={
            "event_name": "retriever_decision",
            "scope": "group" if is_group else "private",
            "query_preview": _normalize(query)[:120],
            "hints": hints,
            "k": effective_limit,
            "min_score": threshold,
        },
    )

    def _log_metrics(decision: str, results: List[Dict[str, Any]]) -> None:
        summary = _summarize_results(results)
        metrics = RetrievalMetrics(
            query_hash=query_hash,
            scope="group" if is_group else "private",
            decision=decision,
            min_score=threshold,
            candidates=len(results),
            returned=len(results),
            classes=summary["classes"],
            sources=summary["sources"],
            top_score=summary["top_score"],
            avg_score=summary["avg_score"],
            needs_clarification=decision == "needs_clarification",
            cache_hit=False,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        _emit_retrieval_metrics(metrics)

    try:
        if is_group:
            from core.rag import _get_firestore as _get_db  # type: ignore

            db = _get_db()
            if db is None or not _is_user_member(db, group_jid, phone):
                try:
                    from core.audit import log_action
                    log_action(
                        actor="agent-knowledge-retriever",
                        action="CROSS_SCOPE_ATTEMPT",
                        target=phone,
                        details={
                            "query_preview": _normalize(query)[:120],
                            "group_jid": group_jid,
                            "reason": "not_member_or_firestore_unavailable",
                        },
                    )
                except Exception:
                    pass
                result = {
                    "scope": "group",
                    "decision": "denied",
                    "results": [],
                    "count": 0,
                    "needs_share_prompt": False,
                    "needs_clarification": False,
                    "share_pending_action": None,
                    "reason": "not_member" if db is not None else "firestore_unavailable",
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            group_hits = await _retrieve_group(
                group_jid=group_jid, query=enriched_query, limit=effective_limit, min_score=threshold
            )
            if group_hits["count"] > 0:
                if group_hits["count"] > 3:
                    group_hits["results"] = await _rerank_with_llm(enriched_query, group_hits["results"], top_n=min(group_hits["count"], 5))
                    group_hits["count"] = len(group_hits["results"])
                result = {
                    **group_hits,
                    "decision": "group",
                    "needs_share_prompt": False,
                    "needs_clarification": False,
                    "share_pending_action": None,
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            private_hits = await _retrieve_private(
                phone=phone, query=enriched_query, limit=effective_limit, min_score=threshold,
                source_title=hints.get("source_title"),
                class_=hints.get("class"),
            )
            if private_hits["count"] > 0:
                if private_hits["count"] > 3:
                    private_hits["results"] = await _rerank_with_llm(enriched_query, private_hits["results"], top_n=min(private_hits["count"], 5))
                    private_hits["count"] = len(private_hits["results"])
                # TOC escape: substituir sumarios por texto completo
                private_hits = await _toc_escape(phone, private_hits, hints.get("source_title"))
                pending = await _maybe_request_share(phone, group_jid, query)
                result = {
                    **private_hits,
                    "decision": "group_private_share_pending",
                    "needs_share_prompt": True,
                    "needs_clarification": False,
                    "share_pending_action": pending,
                    "filters": hints,
                }
                _log_metrics(result["decision"], result["results"])
                _cache_set(cache_key, result)
                return result
            result = {
                "scope": "none",
                "decision": "needs_clarification",
                "results": [],
                "count": 0,
                "needs_share_prompt": False,
                "needs_clarification": True,
                "clarification_prompt": _build_clarification_prompt(
                    await _list_known_sources(phone), query
                ),
                "share_pending_action": None,
                "reason": "no_matches",
                "filters": hints,
            }
            _log_metrics(result["decision"], result["results"])
            _cache_set(cache_key, result)
            return result

        private_hits = await _retrieve_private(
            phone=phone, query=enriched_query, limit=effective_limit, min_score=threshold,
            source_title=hints.get("source_title"),
            class_=hints.get("class"),
        )
        if private_hits["count"] > 0:
            if private_hits["count"] > 3:
                private_hits["results"] = await _rerank_with_llm(enriched_query, private_hits["results"], top_n=min(private_hits["count"], 5))
                private_hits["count"] = len(private_hits["results"])
            # TOC escape: substituir sumarios por texto completo
            private_hits = await _toc_escape(phone, private_hits, hints.get("source_title"))
            decision = "private"
            result = {
                **private_hits,
                "decision": decision,
                "needs_share_prompt": False,
                "needs_clarification": False,
                "share_pending_action": None,
                "filters": hints,
            }
            _log_metrics(result["decision"], result["results"])
            _cache_set(cache_key, result)
            return result
        result = {
            **private_hits,
            "decision": "needs_clarification",
            "results": [],
            "count": 0,
            "needs_share_prompt": False,
            "needs_clarification": True,
            "clarification_prompt": _build_clarification_prompt(
                await _list_known_sources(phone), query
            ),
            "share_pending_action": None,
            "reason": "no_matches",
            "filters": hints,
        }
        _log_metrics(result["decision"], result["results"])
        _cache_set(cache_key, result)
        return result
    except Exception:
        _log_metrics("error", [])
        raise


async def share_pending_action_consume(
    phone: str,
) -> Optional[Dict[str, Any]]:
    """Read and consume a pending share_private_knowledge_in_group action."""
    from core.pending_actions import (
        PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE,
        consume_pending_action,
    )

    return await consume_pending_action(phone, PENDING_ACTION_SHARE_PRIVATE_KNOWLEDGE)


@dataclass
class RetrievalMetrics:
    """Structured log of a single retrieval attempt.

    Emitted at the end of every retrieve() call. Aggregating these
    over time lets you answer questions like: "qual a taxa de
    clarification no grupo X?" or "qual a class mais consultada?".
    """

    query_hash: str
    scope: str
    decision: str
    min_score: float
    candidates: int
    returned: int
    classes: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    top_score: float = 0.0
    avg_score: float = 0.0
    needs_clarification: bool = False
    cache_hit: bool = False
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _emit_retrieval_metrics(metrics: RetrievalMetrics) -> None:
    logger.info(
        "retrieval_quality",
        extra={"event_name": "retrieval_quality", **metrics.to_dict()},
    )


def _summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"classes": [], "sources": [], "top_score": 0.0, "avg_score": 0.0}
    scores = [float(r.get("score", 0.0)) for r in results]
    return {
        "classes": [str(r.get("class", "?")) for r in results],
        "sources": [str(r.get("source", "?")) for r in results],
        "top_score": max(scores),
        "avg_score": sum(scores) / len(scores),
    }


__all__ = [
    "is_rag_query",
    "_is_about_query",
    "_llm_enrich_query",
    "_match_source_title_dynamic",
    "_list_known_sources",
    "_list_knowledge_stats",
    "_is_toc_chunk",
    "_results_are_toc_only",
    "_toc_escape",
    "_fetch_full_document",
    "retrieve",
    "share_pending_action_consume",
    "RAG_RETRIEVE_MIN_SCORE",
    "RetrievalMetrics",
]
