"""Tests for group RAG (F4'): chunking, theme, idempotency, validation."""
import pytest
from unittest.mock import patch, MagicMock


class TestChunkTextSmart:
    """Tests for tools.group._chunk_text_smart."""

    def test_basic_chunking_5000_chars(self):
        from tools.group import _chunk_text_smart
        text = "A" * 5000
        chunks = _chunk_text_smart(text, max_chars=1200, overlap_pct=15)
        assert len(chunks) == 5
        assert all(len(c) <= 1200 for c in chunks)
        assert sum(len(c) for c in chunks) >= 5000

    def test_short_text_single_chunk(self):
        from tools.group import _chunk_text_smart
        chunks = _chunk_text_smart("hello world", max_chars=1200, overlap_pct=15)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_boundaries_prefer_double_newline(self):
        from tools.group import _chunk_text_smart
        text = "A" * 1100 + "\n\n" + "B" * 1100
        chunks = _chunk_text_smart(text, max_chars=1200, overlap_pct=15)
        assert len(chunks) >= 2
        assert "A" in chunks[0] and "B" not in chunks[0]
        assert "B" in chunks[1]


class TestClassifyTheme:
    """Tests for tools.group._classify_theme heuristic."""

    def test_heuristic_ata(self):
        from tools.group import _classify_theme
        assert _classify_theme("Ata_reuniao_21_07.pdf", "foo") == "ata_reuniao"

    def test_heuristic_planilha(self):
        from tools.group import _classify_theme
        assert _classify_theme("Custos_2026.xlsx", "foo") == "dados_financeiros"

    def test_heuristic_apresentacao(self):
        from tools.group import _classify_theme
        assert _classify_theme("Investidoras.pptx", "foo") == "apresentacao"

    def test_heuristic_documentacao(self):
        from tools.group import _classify_theme
        assert _classify_theme("Manual_de_uso.pdf", "foo") == "documentacao"

    def test_heuristic_contrato(self):
        from tools.group import _classify_theme
        assert _classify_theme("Contrato_social.pdf", "foo") == "contrato"

    def test_fallback_outros_when_no_match(self):
        from tools.group import _classify_theme
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}, clear=False):
            assert _classify_theme("random_xyz_123.bin", "foo") == "outros"


class TestGroupHash:
    """Tests for tools.group._group_hash."""

    def test_group_hash_stable(self):
        from tools.group import _group_hash
        h1 = _group_hash("120363123@g.us")
        h2 = _group_hash("120363123@g.us")
        assert h1 == h2
        assert len(h1) == 32

    def test_group_hash_unique(self):
        from tools.group import _group_hash
        assert _group_hash("group_a@g.us") != _group_hash("group_b@g.us")


class TestIndexGroupDocumentValidation:
    """Tests for tools.group.index_group_document validation."""

    @pytest.mark.asyncio
    async def test_text_required(self):
        from tools.group import index_group_document
        result = await index_group_document("5511999", "g1@g.us", "", "group")
        assert result.get("error") == "text_and_group_jid_required"

    @pytest.mark.asyncio
    async def test_group_jid_required(self):
        from tools.group import index_group_document
        result = await index_group_document("5511999", "", "text", "group")
        assert result.get("error") == "text_and_group_jid_required"

    @pytest.mark.asyncio
    async def test_visibility_invalid(self):
        from tools.group import index_group_document
        result = await index_group_document("5511999", "g1@g.us", "text", "private")
        assert result.get("error") == "visibility_must_be_group_or_public"

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        from tools.group import index_group_document
        big_text = "A" * 50001
        result = await index_group_document("5511999", "g1@g.us", big_text, "group")
        assert result.get("error") == "file_too_large"
        assert result.get("size") == 50001

    @pytest.mark.asyncio
    async def test_firestore_unavailable(self):
        from tools.group import index_group_document
        with patch("tools.group._get_firestore", return_value=None):
            result = await index_group_document("5511999", "g1@g.us", "text", "group")
        assert result.get("error") == "firestore_unavailable"


class TestSearchGroupKnowledgeValidation:
    """Tests for tools.group.search_group_knowledge validation."""

    @pytest.mark.asyncio
    async def test_query_required(self):
        from tools.group import search_group_knowledge
        result = await search_group_knowledge("g1@g.us", "")
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_firestore_unavailable(self):
        from tools.group import search_group_knowledge
        with patch("tools.group._get_firestore", return_value=None):
            result = await search_group_knowledge("g1@g.us", "query")
        assert result["count"] == 0


class TestToolRegistration:
    """Verify the tools are registered in tool_registry."""

    def test_index_document_registered(self):
        from tool_registry import TOOL_REGISTRY
        assert "group.index_document" in TOOL_REGISTRY

    def test_search_knowledge_registered(self):
        from tool_registry import TOOL_REGISTRY
        assert "group.search_knowledge" in TOOL_REGISTRY

    def test_manager_group_rag_prompt_exists(self):
        from deepagent_layer.agents import MANAGER_PROMPTS
        assert "manager-group-rag" in MANAGER_PROMPTS
        prompt = MANAGER_PROMPTS["manager-group-rag"]
        assert "ok. pode deixar" in prompt
        assert "estou memorizando" in prompt
        assert "Feito!" in prompt