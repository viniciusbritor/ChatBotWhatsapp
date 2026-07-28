"""Tests for agent_orchestration/categorizer.py (Fase F4d.6)."""
import pytest


class TestHeuristic:
    def test_cdc_falls_into_legal(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Texto do Codigo de Defesa do Consumidor com artigos.",
            "cdc-portugues-2013.pdf",
        )
        assert result["class"] == "legal"
        assert result["group"] == "legislacao"

    def test_edital_falls_into_edital(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Pregao eletronico para contratacao de TI.",
            "edital-pregao.pdf",
        )
        assert result["class"] == "edital"
        assert result["group"] == "licitacao"

    def test_manual_falls_into_manual(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Manual de procedimento operacional padrao.",
            "manual-pop.pdf",
        )
        assert result["class"] == "manual"
        assert result["group"] == "processos"

    def test_probabilidade_falls_into_academico(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Introducao a teoria das probabilidades.",
            "livro-probabilidade.pdf",
        )
        assert result["class"] == "academico"
        assert result["group"] == "probabilidade"

    def test_saude_falls_into_saude(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Protocolo clinico de medicina para tratar doencas.",
            "bula-medicamento.pdf",
        )
        assert result["class"] == "saude"
        assert result["group"] == "protocolo"

    def test_unknown_falls_into_outros(self):
        from agent_orchestration.categorizer import _heuristic_categorize

        result = _heuristic_categorize(
            "Texto sem marcadores claros.",
            "random.bin",
        )
        assert result["class"] == "outros"
        assert result["group"] == "outros"


class TestCoerce:
    def test_coerce_rejects_invalid_class(self):
        from agent_orchestration.categorizer import _coerce

        result = _coerce(
            {"class": "inventado", "group": "x", "theme": "x", "confidence": 0.5},
            "x.pdf",
        )
        assert result["class"] == "outros"

    def test_coerce_rejects_invalid_group_for_class(self):
        from agent_orchestration.categorizer import _coerce

        result = _coerce(
            {"class": "legal", "group": "estatistica", "theme": "x", "confidence": 0.5},
            "x.pdf",
        )
        assert result["group"] == "outros"

    def test_coerce_keeps_valid_values(self):
        from agent_orchestration.categorizer import _coerce

        result = _coerce(
            {
                "class": "academico",
                "group": "livro",
                "theme": "Probabilidade",
                "confidence": 0.9,
            },
            "x.pdf",
        )
        assert result["class"] == "academico"
        assert result["group"] == "livro"
        assert result["theme"] == "Probabilidade"
        assert result["confidence"] == 0.9

    def test_coerce_falls_back_to_source_name_for_theme(self):
        from agent_orchestration.categorizer import _coerce

        result = _coerce({"class": "outros", "group": "outros"}, "doc.pdf")
        assert result["theme"] == "doc.pdf"


class TestCategorizeEndToEnd:
    @pytest.mark.asyncio
    async def test_uses_heuristic_when_llm_fails(self, monkeypatch):
        from agent_orchestration import categorizer

        async def fake_llm(text, source_name):
            return {}
        monkeypatch.setattr(categorizer, "_llm_categorize", fake_llm)
        result = await categorizer.categorize(
            "Texto do Codigo de Defesa do Consumidor",
            "cdc-2026.pdf",
        )
        assert result["class"] == "legal"
        assert result["group"] == "legislacao"

    @pytest.mark.asyncio
    async def test_uses_llm_when_available(self, monkeypatch):
        from agent_orchestration import categorizer

        async def fake_llm(text, source_name):
            return {
                "class": "academico",
                "group": "livro",
                "theme": "Probabilidade",
                "confidence": 0.8,
            }
        monkeypatch.setattr(categorizer, "_llm_categorize", fake_llm)
        result = await categorizer.categorize("Texto", "x.pdf")
        assert result["class"] == "academico"
        assert result["group"] == "livro"
        assert result["confidence"] == 0.8
