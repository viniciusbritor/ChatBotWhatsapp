"""Tests for memory tools (structured user facts)."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest


class TestMemorySaveFact:
    def test_save_requires_phone(self):
        from tools.memory import save_fact

        result = asyncio.run(save_fact(key="k", value="v"))
        assert result.get("error") == "missing_phone"

    def test_save_requires_key_and_value(self):
        from tools.memory import save_fact

        result = asyncio.run(save_fact(key="", value="", phone="5511"))
        assert result.get("error") == "key_e_value_obrigatorios"

    def test_save_persists_to_firestore(self):
        from tools.memory import save_fact

        mock_doc = MagicMock()
        mock_doc.set.return_value = None
        mock_facts_coll = MagicMock()
        mock_facts_coll.document.return_value = mock_doc
        mock_user_doc = MagicMock()
        mock_user_doc.collection.return_value = mock_facts_coll
        mock_user = MagicMock()
        mock_user.document.return_value = mock_user_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_user

        with patch("tools.memory._get_firestore", return_value=mock_db):
            result = asyncio.run(
                save_fact(key="endereco_casa", value="Av. Portugal, 401", phone="5511966830020")
            )

        assert result.get("saved") is True
        assert result.get("key") == "endereco_casa"
        assert mock_facts_coll.document.called


class TestMemorySearchFacts:
    def test_search_requires_phone(self):
        from tools.memory import search_facts

        result = asyncio.run(search_facts(query="x"))
        assert result.get("error") == "missing_phone"

    def test_search_filters_by_query(self):
        from tools.memory import search_facts

        doc1 = MagicMock()
        doc1.to_dict.return_value = {"key": "endereco_casa", "value": "Av. Portugal, 401", "category": "endereco"}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {"key": "cor_bandeira", "value": "vermelha", "category": "preferencia"}
        mock_facts_coll = MagicMock()
        mock_facts_coll.limit.return_value.stream.return_value = [doc1, doc2]
        mock_user_doc = MagicMock()
        mock_user_doc.collection.return_value = mock_facts_coll
        mock_user = MagicMock()
        mock_user.document.return_value = mock_user_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_user

        with patch("tools.memory._get_firestore", return_value=mock_db):
            result = asyncio.run(search_facts(query="endereco", phone="5511"))

        assert result.get("count") == 1
        assert result["results"][0]["key"] == "endereco_casa"


class TestMemoryDeleteFact:
    def test_delete_requires_phone_and_key(self):
        from tools.memory import delete_fact

        result = asyncio.run(delete_fact(key="k"))
        assert result.get("error") == "phone_e_key_obrigatorios"

    def test_delete_calls_firestore(self):
        from tools.memory import delete_fact

        mock_doc = MagicMock()
        mock_doc.delete.return_value = None
        mock_facts_coll = MagicMock()
        mock_facts_coll.document.return_value = mock_doc
        mock_user_doc = MagicMock()
        mock_user_doc.collection.return_value = mock_facts_coll
        mock_user = MagicMock()
        mock_user.document.return_value = mock_user_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_user

        with patch("tools.memory._get_firestore", return_value=mock_db):
            result = asyncio.run(delete_fact(key="endereco_casa", phone="5511"))

        assert result.get("deleted") is True
        assert mock_doc.delete.called
