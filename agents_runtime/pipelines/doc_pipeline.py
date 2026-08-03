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
)

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
    phone = payload.get("phone", "")
    text = payload.get("text", "")
    extra = payload.get("extra", {}) or {}

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
                "metadata": {"agent_id": "agent-knowledge-retriever", "needs_clarification": True},
            }

        chunks = result.get("results", [])
        if not chunks:
            return {
                "reply": "Nao encontrei nada sobre isso na base de conhecimento.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "agent-knowledge-retriever", "count": 0},
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
            },
        }
    except Exception as exc:
        logger.error("rag_retrieve_failed error=%s", exc)
        return {
            "reply": "Desculpe, nao consegui buscar na base de conhecimento agora.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "agent-knowledge-retriever", "error": str(exc)[:200]},
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
