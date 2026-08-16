"""Tests for jennifier system prompt compression."""

from __future__ import annotations

import pytest

import yaml


@pytest.fixture(scope="module")
def jennifier_yaml():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    yaml_path = repo_root / "data" / "agents" / "jennifier.yaml"
    with open(yaml_path) as f:
        return yaml.safe_load(f)


class TestPromptCompression:
    def test_prompt_under_5kb(self, jennifier_yaml):
        """System prompt deve ser menor que 5KB apos compressao."""
        prompt = jennifier_yaml["system_prompt"]
        size = len(prompt)
        assert size < 5000, f"Prompt too large: {size} chars (must be < 5000)"

    def test_prompt_size_reduced_from_original(self, jennifier_yaml):
        """Verifica reducao de pelo menos 30% vs original (8.5KB)."""
        prompt = jennifier_yaml["system_prompt"]
        original_size = 8550
        new_size = len(prompt)
        reduction = (1 - new_size / original_size) * 100
        assert reduction >= 30, f"Reduction only {reduction:.1f}% (expected >= 30%)"

    def test_prompt_keeps_critical_keywords(self, jennifier_yaml):
        """Regras criticas devem permanecer no prompt."""
        prompt = jennifier_yaml["system_prompt"].lower()
        critical_keywords = [
            "secretaria",
            "rag",
            "drive",
            "calendar",
            "gmail",
            "onboarding",  # PT22
            "source_title",
            "voce utiliza",  # capability assertion
            "nunca",
            "task",
        ]
        for kw in critical_keywords:
            assert kw in prompt, f"Missing critical keyword: {kw!r}"

    def test_prompt_keeps_tool_tools_section(self, jennifier_yaml):
        """Tools mapping section deve estar presente."""
        prompt = jennifier_yaml["system_prompt"].lower()
        assert "manager-calendar" in prompt or "calendar" in prompt
        assert "manager-email" in prompt or "gmail" in prompt
        assert "manager-drive" in prompt or "drive" in prompt

    def test_prompt_keeps_routing_rules(self, jennifier_yaml):
        """PT8 (RAG vs Drive) ainda explicado."""
        prompt = jennifier_yaml["system_prompt"].lower()
        assert "rag" in prompt
        assert "drive" in prompt
        # PT9 knowledge.answer como fallback principal
        assert "knowledge.answer" in prompt or "answer" in prompt

    def test_prompt_keeps_mandamentos(self, jennifier_yaml):
        """Mandamentos obrigatorios (citacao, no-alucinacao)."""
        prompt = jennifier_yaml["system_prompt"].lower()
        # source_title sempre antes de chunks
        assert "source_title" in prompt
        # Max 1 ironico por resposta
        assert "1" in prompt and "ironic" in prompt
        # Nunca lembre de falhas
        assert "falhas" in prompt or "ferramentas" in prompt

    def test_prompt_keeps_horario_triggers(self, jennifier_yaml):
        """Saudacao por horario BRT removido (otimizacao) ou mantido."""
        prompt = jennifier_yaml["system_prompt"].lower()
        # Deve manter alguma menção a saudacao
        assert "saudac" in prompt or "bom dia" in prompt or "boa tarde" in prompt

    def test_prompt_skip_long_examples(self, jennifier_yaml):
        """Exemplos longos (CDC, Hygienization) devem ter saido."""
        prompt = jennifier_yaml["system_prompt"]
        # "Higiene das maos" example was removed
        assert "higiene das maos" not in prompt.lower()
        # "capitulos do CDC" example was removed
        assert "capitulos do cdc" not in prompt.lower()

    def test_prompt_keeps_short_model_identity(self, jennifier_yaml):
        """Identidade e tom permanecem."""
        prompt = jennifier_yaml["system_prompt"].lower()
        assert "jennifer" in prompt
        assert "whatsapp" in prompt
        assert "pt-br" in prompt or "português" in prompt

    def test_yaml_loads_without_error(self, jennifier_yaml):
        """Sanity check: YAML intacto."""
        assert "name" in jennifier_yaml
        assert "model" in jennifier_yaml
        assert "system_prompt" in jennifier_yaml
        assert jennifier_yaml["model"] == "deepseek-v4-flash"
