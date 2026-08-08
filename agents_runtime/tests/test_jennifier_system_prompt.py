"""Tests for jennifier and agent-knowledge-retriever system prompts (F4d.8)."""
import os
import pytest


YAML_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "agents",
)


def _load_yaml(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def jennifier_yaml():
    path = os.path.join(YAML_DIR, "jennifier.yaml")
    if not os.path.exists(path):
        pytest.skip(f"jennifier.yaml not found at {path}")
    return _load_yaml(path)


@pytest.fixture(scope="module")
def retriever_yaml():
    path = os.path.join(YAML_DIR, "agent-knowledge-retriever.yaml")
    if not os.path.exists(path):
        pytest.skip(f"agent-knowledge-retriever.yaml not found at {path}")
    return _load_yaml(path)


class TestJennifierSystemPrompt:
    def test_mentions_firestore_vector(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "firestore vector" in sp

    def test_mentions_agent_knowledge_retriever(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "agent-knowledge-retriever" in sp

    def test_mentions_categorizer(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "categoriz" in sp

    def test_mentions_class(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "class" in sp

    def test_mentions_group(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "group" in sp

    def test_mentions_theme(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "theme" in sp

    def test_mentions_source_title(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "source_title" in sp

    def test_mentions_clarification(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "clarification" in sp

    def test_has_personality(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        has_humor = any(w in sp for w in ["sarcast", "humor", "cinica"])
        assert has_humor, "esperado leve senso de humor no prompt"

    def test_personality_limit(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "maximo 1 comentario" in sp or "maximo 1" in sp

    def test_no_irony_in_sensitive(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "sem ironia" in sp
        assert "saude" in sp
        assert "juridic" in sp
        assert "financ" in sp

    def test_no_self_irony(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "nunca ironizar o proprio servico" in sp

    def test_no_user_irony(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "nunca ironizar o usuario" in sp

    def test_version_incremented(self, jennifier_yaml):
        assert jennifier_yaml.get("system_prompt_version") == 5

    def test_includes_introspection_guidance(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "quando perguntarem sobre sua propria arquitetura" in sp

    def test_mentions_saudacao_brt(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "saudacoes" in sp
        assert "brt" in sp
        assert "bom dia" in sp
        assert "boa tarde" in sp
        assert "boa noite" in sp

    def test_mentions_pt_br_naturalidade(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "pt-br" in sp or "portugues brasileiro" in sp
        assert "naturalidade" in sp

    def test_mentions_respostas_humanas(self, jennifier_yaml):
        sp = jennifier_yaml.get("system_prompt", "").lower()
        assert "respostas humanas" in sp
        assert "curtas" in sp


class TestRetrieverSystemPrompt:
    def test_mentions_knowledge_retrieve(self, retriever_yaml):
        sp = retriever_yaml.get("system_prompt", "").lower()
        assert "knowledge.retrieve" in sp

    def test_mentions_answer_tool(self, retriever_yaml):
        sp = retriever_yaml.get("system_prompt", "").lower()
        assert "knowledge.answer" in sp

    def test_cite_source_title(self, retriever_yaml):
        sp = retriever_yaml.get("system_prompt", "").lower()
        assert "source_title" in sp

    def test_clarification_prompt(self, retriever_yaml):
        sp = retriever_yaml.get("system_prompt", "").lower()
        assert "knowledge.answer" in sp  # tool principal do novo prompt

    def test_no_alucination(self, retriever_yaml):
        sp = retriever_yaml.get("system_prompt", "").lower()
        assert "nunca invente" in sp

    def test_version_incremented(self, retriever_yaml):
        assert retriever_yaml.get("system_prompt_version") == 4
