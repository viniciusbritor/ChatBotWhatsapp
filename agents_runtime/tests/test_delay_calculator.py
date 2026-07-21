"""Tests for core.delay_calculator module."""
from core.delay_calculator import calculate_delay_ms, calculate_presence


class TestCalculateDelayMs:
    def test_empty_text(self):
        assert calculate_delay_ms("") == 0

    def test_none_input(self):
        assert calculate_delay_ms(None) == 0

    def test_single_word(self):
        delay = calculate_delay_ms("oi")
        assert delay == int(0.6 * 1 * 1000)  # 600ms

    def test_normal_text(self):
        text = "Oi Vinicius, tudo bem? Sua reuniao comeca em uma hora."
        word_count = len(text.split())
        expected = int(0.6 * word_count * 1000)
        assert calculate_delay_ms(text) == expected

    def test_cap_at_15_seconds(self):
        text = " ".join(["palavra"] * 100)
        delay = calculate_delay_ms(text)
        assert delay == 15000

    def test_custom_ms_per_word(self):
        delay = calculate_delay_ms("uma duas tres", ms_per_word=1000)
        assert delay == 3000

    def test_custom_cap(self):
        text = " ".join(["x"] * 10)
        delay = calculate_delay_ms(text, ms_per_word=600, cap_ms=2000)
        assert delay == 2000


class TestCalculatePresence:
    def test_returns_composing(self):
        assert calculate_presence() == "composing"
