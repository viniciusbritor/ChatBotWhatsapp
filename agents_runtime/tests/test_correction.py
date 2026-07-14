"""Tests for correction tool."""
import pytest
from unittest.mock import patch, MagicMock


class TestDetectCorrection:
    def test_clear_correction(self):
        from tools.correction import detect_correction
        result = detect_correction("Na verdade, meu nome e Vinicius")
        assert result["is_correction"] is True
        assert "na verdade" in result["phrases_matched"]
        assert result["target"] == "preferred_name"

    def test_wrong_detection(self):
        from tools.correction import detect_correction
        result = detect_correction("Oi tudo bem?")
        assert result["is_correction"] is False

    def test_behavior_correction(self):
        from tools.correction import detect_correction
        result = detect_correction("Seu tom esta errado, prefiro mais formal")
        assert result["is_correction"] is True
        assert result["target"] == "agent_behavior"

    def test_fact_correction(self):
        from tools.correction import detect_correction
        result = detect_correction("Esta informacao esta errada")
        assert result["is_correction"] is True
        assert result["target"] == "agent_fact"


class TestGenerateConfirmationMessage:
    def test_preferred_name(self):
        from tools.correction import generate_confirmation_message
        msg = generate_confirmation_message("preferred_name", "meu nome e Vinicius")
        assert "sim" in msg.lower()
        assert "nao" in msg.lower() or "não" in msg.lower()

    def test_behavior(self):
        from tools.correction import generate_confirmation_message
        msg = generate_confirmation_message("agent_behavior", "tom muito formal")
        assert "comportamento" in msg.lower() or "atualizar" in msg.lower()

    def test_generic(self):
        from tools.correction import generate_confirmation_message
        msg = generate_confirmation_message("unknown", "alguma coisa")
        assert "sim" in msg.lower()


class TestLogCorrection:
    @pytest.mark.asyncio
    async def test_log_no_firestore(self):
        from tools.correction import log_correction

        with patch("tools.correction._get_firestore", return_value=None):
            result = await log_correction(
                "+5511999999999",
                "Meu nome e X",
                "preferred_name",
                "Vini",
                "Vinicius",
                confirmed=True,
            )
        assert "error" in result