"""Unit tests for FinOps pipeline & cost estimation logic."""
import pytest
from core.pricing import estimate_cost_usd, PROVIDERS


def test_finops_zero_cost_metrics():
    """Verify Groq STT and Gemini Vision calculate as $0.00 in estimate_cost_usd."""
    costs = {
        "groq_stt_seconds": 3600,
        "gemini_vision_requests": 50,
    }
    total = estimate_cost_usd(costs)
    assert total == 0.0


def test_finops_deepseek_cache_hit_pricing():
    """Verify DeepSeek V4 Flash cache hit discount calculation (10x cheaper input)."""
    costs = {
        "deepseek_input_tokens": 1_000_000,
        "deepseek_cache_hit_tokens": 1_000_000,
        "deepseek_output_tokens": 1_000_000,
    }
    total = estimate_cost_usd(costs)
    # 0.14 + 0.014 + 0.28 = 0.434 USD
    assert pytest.approx(total, 0.001) == 0.434


def test_providers_dict_includes_free_tiers():
    """Ensure free tier providers exist in PROVIDERS dictionary."""
    assert "groq_whisper_free" in PROVIDERS
    assert "gemini_flash_free" in PROVIDERS
    assert PROVIDERS["groq_whisper_free"]["second_rate"] == 0.0
    assert PROVIDERS["gemini_flash_free"]["request_rate"] == 0.0
