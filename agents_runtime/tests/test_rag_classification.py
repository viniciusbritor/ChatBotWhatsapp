"""Tests for core/rag.py with class/group/theme support (Fase F4d.6)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestIndexPrivateDocumentClassification:
    @pytest.mark.asyncio
    async def test_classification_metadata_persisted(self):
        from core.rag import index_private_document

        database = MagicMock()

        async def _fake_embed(texts):
            return [[0.1] * 1536 for _ in texts]

        with patch("core.rag._get_firestore", return_value=database):
            with patch("core.rag.embed_documents", side_effect=_fake_embed):
                result = await index_private_document(
                    phone="5511999",
                    text_content="Trecho de exemplo do CDC.",
                    source_title="cdc.pdf",
                    class_="legal",
                    group="legislacao",
                    theme="Codigo de Defesa do Consumidor",
                )
        assert result["class"] == "legal"
        assert result["group"] == "legislacao"
        assert result["theme"] == "Codigo de Defesa do Consumidor"
        last_set_call = database.batch.return_value.set.call_args_list[-1]
        data = last_set_call.args[1]
        assert data["class"] == "legal"
        assert data["group"] == "legislacao"
        assert data["theme"] == "Codigo de Defesa do Consumidor"


class TestSearchLegalKnowledgeFilters:
    @pytest.mark.asyncio
    async def test_filters_by_source_title(self):
        from core.rag import search_legal_knowledge

        async def fake_find_nearest(*args, **kwargs):
            return []

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch(
                "core.rag._find_nearest",
                side_effect=fake_find_nearest,
            ) as mock_find:
                with patch(
                    "core.rag.embed_query",
                    AsyncMock(return_value=[0.1] * 1536),
                ):
                    await search_legal_knowledge(
                        phone="5511999",
                        query="cdc",
                        source_title="cdc.pdf",
                    )
        mock_find.assert_awaited_once()
        filters = mock_find.call_args.args[4]
        assert ("source_title", "==", "cdc.pdf") in filters

    @pytest.mark.asyncio
    async def test_filters_by_class(self):
        from core.rag import search_legal_knowledge

        async def fake_find_nearest(*args, **kwargs):
            return []

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch(
                "core.rag._find_nearest",
                side_effect=fake_find_nearest,
            ) as mock_find:
                with patch(
                    "core.rag.embed_query",
                    AsyncMock(return_value=[0.1] * 1536),
                ):
                    await search_legal_knowledge(
                        phone="5511999",
                        query="edital",
                        class_="edital",
                    )
        mock_find.assert_awaited_once()
        filters = mock_find.call_args.args[4]
        assert ("class", "==", "edital") in filters

    @pytest.mark.asyncio
    async def test_no_filters_when_unused(self):
        from core.rag import search_legal_knowledge

        async def fake_find_nearest(*args, **kwargs):
            return []

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch(
                "core.rag._find_nearest",
                side_effect=fake_find_nearest,
            ) as mock_find:
                with patch(
                    "core.rag.embed_query",
                    AsyncMock(return_value=[0.1] * 1536),
                ):
                    await search_legal_knowledge(phone="5511999", query="x")
        mock_find.assert_awaited_once()
        filters = mock_find.call_args.args[4]
        assert ("source_title", "==", "cdc.pdf") not in filters
        assert ("class", "==", "edital") not in filters
