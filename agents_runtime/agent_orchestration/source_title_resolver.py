"""Source title resolver — LLM dedicado para matching de documentos.

Desacoplado do knowledge_retriever. Age como pós-processador no
retrieve(): só é chamado quando regex, aliases e dynamic match falham.

Prompt focado em 1 tarefa: "Qual destes documentos corresponde a pergunta?"
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_PROMPT = (
    "Lista de documentos disponiveis:\n"
    "{sources}\n\n"
    "Qual destes documentos corresponde a pergunta do usuario? "
    "Responda APENAS com o nome exato do documento da lista. "
    "Se nenhum corresponder, responda '' (vazio).\n\n"
    "Pergunta: {query}"
)


async def resolve(sources: List[str] | List[Dict[str, str]], query: str) -> Optional[str]:
    if not sources or not query or not query.strip():
        return None

    source_list: List[str] = []
    for s in sources:
        if isinstance(s, dict):
            source_list.append(s["source_title"])
        else:
            source_list.append(s)
    if not source_list:
        return None

    api_key = (os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
    if not api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI

        base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        ).strip()

        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=80,
            timeout=8,
            extra_body={"cache_mode": "default"},
        )

        sources_text = "\n".join(f"- {s}" for s in source_list[:20])
        prompt = _PROMPT.format(sources=sources_text, query=query.strip()[:400])

        result = await asyncio.to_thread(llm.invoke, prompt)
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        candidate = raw.strip().strip(".,;:!?()\"' \t\n\r")

        if candidate and candidate in source_list:
            return candidate
        if candidate:
            for src in source_list:
                if src.lower() == candidate.lower():
                    return src
        return None

    except Exception as exc:
        logger.debug("source_title_resolver llm failed: %s", exc)
        return None


__all__ = ["resolve"]
