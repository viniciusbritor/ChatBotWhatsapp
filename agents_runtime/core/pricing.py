"""Pricing referencia para FinOps (Fase E 30/07/2026).

Precos aproximados por 1M tokens (USD). Atualizar quando a
DeepSeek ou OpenAI mudarem. Para workloads nominais
(~100 msgs/dia), variacoes de 10% sao desprezíveis (< 1 USD/mes).

Fontes:
- DeepSeek pricing: https://platform.deepseek.com/pricing
- OpenAI Embeddings: https://openai.com/api/pricing/

Modelo principal: deepseek-v4-flash
- Input cache hit: $0.014/1M (10x mais barato)
- Input normal:   $0.14/1M
- Output:         $0.28/1M

deepseek-v4-pro (NAO usado em producao desde 11/08/2026 — removido do
doc_pipeline). Mantido aqui como referencia de custo caso seja avaliado
no futuro. Precos sao aproximados e variam com a oferta do fornecedor.

Embeddings: text-embedding-3-small
- Input: $0.02/1M
"""
from __future__ import annotations

from typing import Dict


DEEPSEEK_V4_FLASH = {
    "input_per_1m": 0.14,
    "output_per_1m": 0.28,
    "cache_hit_per_1m": 0.014,
}


DEEPSEEK_V4_PRO = {
    "input_per_1m": 0.55,
    "output_per_1m": 2.19,
    "cache_hit_per_1m": 0.055,
}


OPENAI_EMBEDDING_SMALL = {
    "input_per_1m": 0.02,
}


PROVIDERS: Dict[str, Dict[str, float]] = {
    "deepseek_v4_flash": DEEPSEEK_V4_FLASH,
    "deepseek_v4_pro": DEEPSEEK_V4_PRO,
    "openai_embedding_small": OPENAI_EMBEDDING_SMALL,
}


_KEY_RATE_MAP = {
    "deepseek_input_tokens": ("deepseek_v4_flash", "input_per_1m"),
    "deepseek_output_tokens": ("deepseek_v4_flash", "output_per_1m"),
    "deepseek_cache_hit_tokens": ("deepseek_v4_flash", "cache_hit_per_1m"),
    "openai_embedding_input_tokens": ("openai_embedding_small", "input_per_1m"),
}


def estimate_cost_usd(costs: Dict[str, int]) -> float:
    """Estima custo USD agregado a partir de dict de tokens.

    Cada chave de token tem um provider + rate mapeado em
    _KEY_RATE_MAP. Custos desconhecidos sao ignorados (fail-safe).

    Args:
        costs: dict com chaves como 'deepseek_input_tokens',
            'deepseek_output_tokens', 'openai_embedding_input_tokens'.

    Returns:
        Custo estimado em USD (float).

    Note:
        Tokens zero ou None sao ignorados. Custos acumulados
        do tracker via add_cost().
    """
    total = 0.0
    for key, value in costs.items():
        if not value:
            continue
        rate_ref = _KEY_RATE_MAP.get(key)
        if rate_ref is None:
            continue
        provider, rate_name = rate_ref
        rates = PROVIDERS.get(provider)
        if not rates:
            continue
        rate_per_1m = rates.get(rate_name)
        if rate_per_1m is None:
            continue
        total += (int(value) / 1_000_000.0) * rate_per_1m
    return total


__all__ = [
    "DEEPSEEK_V4_FLASH",
    "OPENAI_EMBEDDING_SMALL",
    "PROVIDERS",
    "estimate_cost_usd",
]
