"""Tests para core/pricing.py (Fase E 30/07/2026)."""
import pytest


def test_deepseek_v4_flash_pricing_constants():
    """Precos documentados batem com a tabela atual."""
    from core.pricing import DEEPSEEK_V4_FLASH

    assert DEEPSEEK_V4_FLASH["input_per_1m"] == 0.14
    assert DEEPSEEK_V4_FLASH["output_per_1m"] == 0.28
    assert DEEPSEEK_V4_FLASH["cache_hit_per_1m"] == 0.014


def test_estimate_cost_empty_dict_returns_zero():
    from core.pricing import estimate_cost_usd

    assert estimate_cost_usd({}) == 0.0
    assert estimate_cost_usd({"unknown_key": 1000}) == 0.0


def test_estimate_cost_input_only():
    from core.pricing import estimate_cost_usd

    costs = {"deepseek_input_tokens": 1_000_000}
    assert estimate_cost_usd(costs) == pytest.approx(0.14)


def test_estimate_cost_output_only():
    from core.pricing import estimate_cost_usd

    costs = {"deepseek_output_tokens": 1_000_000}
    assert estimate_cost_usd(costs) == pytest.approx(0.28)


def test_estimate_cost_mixed_tokens():
    from core.pricing import estimate_cost_usd

    costs = {
        "deepseek_input_tokens": 500_000,
        "deepseek_output_tokens": 200_000,
        "deepseek_cache_hit_tokens": 100_000,
    }
    expected = (500_000 / 1e6) * 0.14 + (200_000 / 1e6) * 0.28 + (100_000 / 1e6) * 0.014
    assert estimate_cost_usd(costs) == pytest.approx(expected)


def test_estimate_cost_openai_embedding():
    from core.pricing import estimate_cost_usd

    costs = {"openai_embedding_input_tokens": 1_000_000}
    assert estimate_cost_usd(costs) == pytest.approx(0.02)


def test_estimate_cost_unknown_key_returns_zero():
    """Chave nao registrada -> custo 0 (fail-safe, nao crash)."""
    from core.pricing import estimate_cost_usd

    assert estimate_cost_usd({"unknown_key_thats_not_mapped": 1000}) == 0.0
    assert estimate_cost_usd({"claude_input_tokens": 1000}) == 0.0


def test_provider_ratings_table_has_both():
    from core.pricing import PROVIDERS

    assert "deepseek_v4_flash" in PROVIDERS
    assert "openai_embedding_small" in PROVIDERS


def test_latency_tracker_breakdown_includes_cost_usd():
    """Integracao: tracker.breakdown() retorna cost_usd_estimated."""
    from core.observability import LatencyTracker, reset
    reset()

    tracker = LatencyTracker(enabled=True)
    tracker.add_cost("deepseek_input_tokens", 100_000)
    tracker.add_cost("deepseek_output_tokens", 50_000)
    breakdown = tracker.breakdown()
    assert "cost_usd_estimated" in breakdown
    expected = (100_000 / 1e6) * 0.14 + (50_000 / 1e6) * 0.28
    assert breakdown["cost_usd_estimated"] == pytest.approx(expected)
