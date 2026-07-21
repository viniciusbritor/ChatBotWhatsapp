"""Tests for core.escalation module."""
from core.escalation import compute_confidence_score, should_escalate


class TestComputeConfidenceScore:
    def test_empty_text(self):
        score = compute_confidence_score("")
        assert score <= -2

    def test_none_input(self):
        score = compute_confidence_score(None)
        assert score <= -2

    def test_short_response_low_confidence(self):
        score = compute_confidence_score("sim")
        assert score <= -2

    def test_normal_response_zero_or_positive(self):
        score = compute_confidence_score(
            "Oi Vinicius! Sua reuniao com Joao esta marcada para amanha as 14h. "
            "Voce quer que eu faca a ata? Bom trabalho!"
        )
        assert score >= 0

    def test_low_confidence_phrase(self):
        score = compute_confidence_score(
            "Desculpe, nao tenho certeza sobre isso. Talvez voce deva verificar com outra pessoa."
        )
        assert score <= -2

    def test_excessive_questions(self):
        score = compute_confidence_score(
            "Como? Quando? Onde? Por que? Quem? O que? "
        )
        assert score <= -2

    def test_invalid_json_format(self):
        score = compute_confidence_score('{"foo": "bar"')
        assert score <= -2


class TestShouldEscalate:
    def test_escalate_when_score_below_threshold(self):
        assert should_escalate(-3, threshold=-2) is True
        assert should_escalate(-5, threshold=-2) is True

    def test_no_escalate_when_score_above_threshold(self):
        assert should_escalate(0, threshold=-2) is False
        assert should_escalate(2, threshold=-2) is False
        assert should_escalate(-1, threshold=-2) is False

    def test_threshold_boundary(self):
        assert should_escalate(-2, threshold=-2) is True
        assert should_escalate(-1, threshold=-2) is False

    def test_custom_threshold(self):
        assert should_escalate(-1, threshold=-1) is True
        assert should_escalate(0, threshold=-1) is False
