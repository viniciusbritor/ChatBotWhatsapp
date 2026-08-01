"""Tests para o system prompt do manager-group-rag (commit 01/08/2026).

REGRAS de visibilidade (default = group, public soh explicito).
"""
import pytest

from deepagent_layer.agents import MANAGER_PROMPTS


@pytest.fixture(scope="module")
def group_rag_prompt() -> str:
    return MANAGER_PROMPTS["manager-group-rag"]


class TestGroupRagVisibilityDefault:
    """Patch 01/08/2026: anexo em grupo default = visibility='group'.

    Antes: perguntava 'so membros ou publico?' a cada anexo.
    Depois: indexa direto com visibility='group' (default do
    contexto), vira 'public' soh via comando explicito.
    """

    def test_default_visibility_is_group(self, group_rag_prompt: str):
        low = group_rag_prompt.lower()
        assert "default" in low
        assert "visibility" in low
        assert "'group'" in low

    def test_no_question_about_visibility(self, group_rag_prompt: str):
        """Nao pergunta 'so membros ou publico?' mais."""
        low = group_rag_prompt.lower()
        # ANTES do patch essa string existia ("pergunte a visibilidade")
        # DEPOIS do patch nao existe mais
        assert "pergunte a visibilidade" not in low
        assert "so membros ou publico" not in low

    def test_explicit_public_command_phrase(self, group_rag_prompt: str):
        """Lista frases-ativadoras que VAO virar public."""
        low = group_rag_prompt.lower()
        assert "deixe publico" in low
        assert "compartilhe com qualquer pessoa" in low
        assert "publique isso" in low
        assert "para todos os usuarios" in low
        assert "fora do grupo" in low

    def test_keeps_group_as_default_on_ambiguous(self, group_rag_prompt: str):
        """Em caso ambiguo, mantem 'group' (fail-safe para privacidade)."""
        low = group_rag_prompt.lower()
        assert "ambiguo" in low or "qualquer outro caso" in low
        assert "mantenha group" in low

    def test_justification_present(self, group_rag_prompt: str):
        """Explica o porque do default = group."""
        low = group_rag_prompt.lower()
        assert "contexto" in low
        assert "escopo natural" in low or "escopo do grupo" in low


class TestGroupRagPersistsOtherBehavior:
    """Patch nao quebrou nada do comportamento ja existente."""

    def test_keep_warm_messages(self, group_rag_prompt: str):
        low = group_rag_prompt.lower()
        assert "ok. pode deixar" in low
        assert "estou memorizando o conteudo" in low
        assert "feito!" in low
        assert "quer me perguntar" in low

    def test_keep_themes_taxonomy(self, group_rag_prompt: str):
        low = group_rag_prompt.lower()
        assert "ata_reuniao" in low
        assert "dados_financeiros" in low
        assert "apresentacao" in low
        assert "contrato" in low
        assert "documentacao" in low

    def test_keep_needs_overwrite_handling(self, group_rag_prompt: str):
        low = group_rag_prompt.lower()
        assert "needs_overwrite" in low
        assert "sobrescrever" in low

    def test_keep_large_file_warning(self, group_rag_prompt: str):
        low = group_rag_prompt.lower()
        assert "50.000" in low or "50000" in low
