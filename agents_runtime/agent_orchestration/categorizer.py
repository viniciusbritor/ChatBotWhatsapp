"""Knowledge categorizer (Fase F4d.6).

Decide a taxonomia (class, group, theme) de um documento antes de
armazená-lo no Firestore Vector. Usa DeepSeek V4 Flash com system
prompt que carrega a taxonomia em texto. Em caso de falha, devolve
fallback seguro (class=outros, group=outros, theme=source_name).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


CLASS_VALUES = [
    "legal",
    "edital",
    "jurisprudencia",
    "manual",
    "empresa",
    "corporativo",
    "academico",
    "educacional",
    "tecnico",
    "saude",
    "financeiro",
    "governamental",
    "marketing",
    "jornalismo",
    "outros",
]

GROUP_VALUES = {
    "legal": ["legislacao", "contrato", "parecer"],
    "edital": ["licitacao", "concessao", "concurso", "chamada_publica"],
    "jurisprudencia": ["decisao", "sumula", "acordao"],
    "manual": ["processos", "operacao", "instalacao", "seguranca", "manutencao"],
    "empresa": ["politica", "rh", "financeiro", "processos", "comercial"],
    "corporativo": ["telecom", "energia", "varejo", "financeiro_setorial", "saude_setorial"],
    "academico": ["livro", "paper", "tese", "dissertacao", "manual", "probabilidade", "estatistica"],
    "educacional": ["apostila", "ementa", "curso", "plano_de_aula"],
    "tecnico": ["api", "especificacao", "engenharia", "protocolo"],
    "saude": ["protocolo", "estudo", "bula", "diretrizes", "epidemiologia"],
    "financeiro": ["relatorio", "demonstrativo", "orcamento", "audit"],
    "governamental": ["oficio", "portaria", "circular", "parecer"],
    "marketing": ["catalogo", "apresentacao", "brochure"],
    "jornalismo": ["noticia", "artigo", "materia"],
    "outros": ["outros"],
}

SYSTEM_PROMPT = (
    "Voce e o agente categorizador do ChatBotWhatsapp. "
    "Analise o TEXTO e o NOME do arquivo. Responda SOMENTE com JSON valido, "
    "sem texto antes ou depois. Use os seguintes valores:\n"
    f"CLASS: {', '.join(CLASS_VALUES)}\n"
    "GROUP depende de CLASS. Para cada CLASS, GROUP pode ser:\n"
    + "\n".join(
        f"- {cls}: {', '.join(groups)}"
        for cls, groups in GROUP_VALUES.items()
    )
    + "\n\nTHEME: resumo de 1 linha (max 80 chars) sem aspas.\n"
    "Use SEMPRE 'outros' se nao tiver certeza. "
    "Nao invente class ou group fora da lista."
)


def _extract_json(raw: str) -> Dict[str, Any]:
    """Tenta extrair JSON de uma resposta mesmo com lixo ao redor."""
    if not raw:
        return {}
    match = re.search(r"\{[^{}]*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        import json

        return json.loads(match.group(0))
    except Exception:
        return {}


def _coerce(parsed: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    """Valida e normaliza o JSON retornado pelo LLM."""
    raw_class = str(parsed.get("class", "outros")).strip().lower()
    if raw_class not in CLASS_VALUES:
        raw_class = "outros"

    allowed_groups = GROUP_VALUES.get(raw_class, ["outros"])
    raw_group = str(parsed.get("group", "outros")).strip().lower()
    if raw_group not in allowed_groups:
        raw_group = "outros"

    raw_theme = str(parsed.get("theme", "")).strip()
    if not raw_theme or len(raw_theme) > 200:
        raw_theme = source_name or raw_class

    try:
        raw_conf = float(parsed.get("confidence", 0.5))
    except Exception:
        raw_conf = 0.5
    raw_conf = max(0.0, min(1.0, raw_conf))

    return {
        "class": raw_class,
        "group": raw_group,
        "theme": raw_theme,
        "confidence": round(raw_conf, 3),
    }


async def _llm_categorize(
    text: str,
    source_name: str,
) -> Dict[str, Any]:
    try:
        from langchain_openai import ChatOpenAI

        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or os.getenv("NVIDIA_API_KEY", "").strip()
            or ""
        )
        if not api_key:
            return {}
        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        ).strip()
        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=120,
            timeout=10,
            model_kwargs={"extra_body": {"cache_mode": "default"}},
        )
        sample = (text or "")[:2500]
        user_prompt = (
            f"Source name: {source_name}\n\n"
            f"Texto (amostra):\n{sample}\n\n"
            "Responda SOMENTE com JSON no formato:\n"
            '{"class": "...", "group": "...", "theme": "...", "confidence": 0.0-1.0}'
        )
        result = await asyncio.to_thread(
            llm.invoke, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
        )
        raw = (
            getattr(result, "content", str(result))
            if not isinstance(result, dict)
            else result.get("content", "")
        )
        return _extract_json(str(raw))
    except Exception as exc:
        logger.warning("llm_categorize failed: %s", exc)
        return {}


def _heuristic_categorize(text: str, source_name: str) -> Dict[str, Any]:
    """Heuristica deterministica usada como fallback.

    Palavras-chave identificam class e group. theme recebe nome do arquivo.
    """
    import unicodedata

    raw = f"{source_name}\n{text or ''}"
    normalized = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    blob = without_accents.lower()
    if any(
        kw in blob
        for kw in ("codigo de defesa do consumidor", "cdc", "lei ", "decreto")
    ):
        return {"class": "legal", "group": "legislacao", "theme": source_name or "legal", "confidence": 0.7}
    if any(kw in blob for kw in ("edital", "licitacao", "pregao", "concorrencia")):
        return {"class": "edital", "group": "licitacao", "theme": source_name or "edital", "confidence": 0.7}
    if any(kw in blob for kw in ("manual", "procedimento", "pop ", "sop ", "runbook")):
        return {"class": "manual", "group": "processos", "theme": source_name or "manual", "confidence": 0.6}
    if any(kw in blob for kw in ("probabilidade", "estatistica", "livro didatico", "tese", "dissertacao")):
        return {"class": "academico", "group": "probabilidade", "theme": source_name or "academico", "confidence": 0.6}
    if any(kw in blob for kw in ("bula", "protocolo clinico", "estudo clinico", "medicina")):
        return {"class": "saude", "group": "protocolo", "theme": source_name or "saude", "confidence": 0.6}
    if any(kw in blob for kw in ("dissertacao", "monografia", "tcc", "tese")):
        return {"class": "academico", "group": "dissertacao", "theme": source_name or "academico", "confidence": 0.7}
    return {"class": "outros", "group": "outros", "theme": source_name or "outros", "confidence": 0.3}


async def categorize(
    text: str,
    source_name: str = "",
) -> Dict[str, Any]:
    """Categoriza um documento. Devolve ``{class, group, theme, confidence}``.

    Ordem de tentativas: LLM (DeepSeek V4 Flash) -> heuristica local ->
    fallback minimo (outros/outros/theme=source_name).
    """
    parsed = await _llm_categorize(text or "", source_name or "")
    if parsed:
        return _coerce(parsed, source_name)

    return _heuristic_categorize(text or "", source_name or "")


__all__ = [
    "categorize",
    "CLASS_VALUES",
    "GROUP_VALUES",
    "SYSTEM_PROMPT",
]
