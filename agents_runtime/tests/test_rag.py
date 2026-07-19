import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_embedding_model_default_is_openai():
    from core.rag import EMBEDDING_BASE_URL, EMBEDDING_MODEL

    assert EMBEDDING_MODEL == "text-embedding-3-small"
    assert EMBEDDING_BASE_URL == "https://api.openai.com/v1/embeddings"


class FakeVectorQuery:
    def __init__(self, documents=None):
        self.documents = documents or []
        self.filters = []
        self.nearest = None

    def where(self, filter):
        self.filters.append(filter)
        return self

    def find_nearest(self, **kwargs):
        self.nearest = kwargs
        return self

    def get(self):
        return self.documents


class FakeDatabase:
    def __init__(self, query):
        self.query = query
        self.collection_name = None

    def collection(self, name):
        self.collection_name = name
        return self.query


class FakeDocument:
    def __init__(self, document_id, data):
        self.id = document_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class TestOpenAIEmbeddingContract:
    def test_direct_request_uses_openai_endpoint(self, monkeypatch):
        from core import rag

        monkeypatch.setattr(rag, "EMBEDDING_BASE_URL", "https://api.openai.com/v1/embeddings")
        monkeypatch.setattr(rag, "EMBEDDING_MODEL", "text-embedding-3-small")
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json or {}
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "data": [{"embedding": [0.1] * rag.EMBEDDING_DIM}],
            }
            return response

        with patch("core.rag.get_secret", return_value="sk-test"):
            with patch("core.rag.requests.post", side_effect=fake_post):
                vector = rag._embed_direct("texto")

        assert vector and len(vector) == rag.EMBEDDING_DIM
        assert captured["url"] == "https://api.openai.com/v1/embeddings"
        assert captured["headers"].get("Authorization") == "Bearer sk-test"
        assert captured["json"]["model"] == "text-embedding-3-small"
        assert captured["json"]["encoding_format"] == "float"
        assert captured["json"]["input"] == "texto"

    def test_direct_request_returns_none_on_http_error(self, monkeypatch):
        from core import rag

        def fake_post(url, headers=None, json=None, timeout=None):
            response = MagicMock()
            response.status_code = 429
            response.text = "rate limit"
            return response

        with patch("core.rag.get_secret", return_value="sk-test"):
            with patch("core.rag.requests.post", side_effect=fake_post):
                assert rag._embed_direct("texto") is None

    def test_direct_request_returns_none_on_missing_key(self, monkeypatch):
        from core import rag

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch("core.rag.get_secret", return_value=None):
            assert rag._embed_direct("texto") is None


class TestEmbeddingContract:
    def test_owner_hash_normalizes_phone(self):
        from core.rag import _owner_hash

        assert _owner_hash("+55 11 96683-0020") == _owner_hash("5511966830020")

    def test_validate_embedding_accepts_canonical_dimension(self):
        from core.rag import EMBEDDING_DIM, _validate_embedding

        vector = [0.1] * EMBEDDING_DIM
        assert _validate_embedding(vector) == vector

    def test_validate_embedding_rejects_mixed_dimension(self):
        from core.rag import _validate_embedding

        assert _validate_embedding([0.1] * 1024) is None

    def test_embed_best_has_no_dimensional_fallback(self):
        from core.rag import embed_best

        with patch("core.rag._embed_direct", return_value=None) as direct:
            assert embed_best("texto") is None
        direct.assert_called_once_with("texto")

    @pytest.mark.asyncio
    async def test_embed_query_masks_pii_before_provider(self):
        from core.rag import EMBEDDING_DIM, embed_query

        captured = []

        def fake_embed(text):
            captured.append(text)
            return [0.1] * EMBEDDING_DIM

        with patch("core.rag.embed_best", side_effect=fake_embed):
            result = await embed_query("Meu email e pessoa@example.com")

        assert len(result) == EMBEDDING_DIM
        assert "pessoa@example.com" not in captured[0]
        assert "[MASK_EMAIL]" in captured[0]


class TestVectorQuery:
    @pytest.mark.asyncio
    async def test_find_nearest_uses_native_vector_query(self):
        from core.rag import EMBEDDING_DIM, _find_nearest

        query = FakeVectorQuery()
        database = FakeDatabase(query)
        result = await _find_nearest(
            database,
            "conversation-memory-v2",
            [0.1] * EMBEDDING_DIM,
            5,
            [("owner_hash", "==", "owner")],
        )

        assert result == []
        assert database.collection_name == "conversation-memory-v2"
        assert len(query.filters) == 1
        assert query.nearest["vector_field"] == "vector_embedding"
        assert query.nearest["distance_result_field"] == "vector_distance"

    @pytest.mark.asyncio
    async def test_search_knowledge_uses_shared_v2_collection(self):
        from core.rag import EMBEDDING_DIM, SHARED_COLLECTION, search_knowledge

        document = FakeDocument(
            "doc-1",
            {
                "titulo": "Lei",
                "conteudo": "Conteudo",
                "categoria": "legislacao",
                "fonte": "Fonte",
                "vector_distance": 0.1,
            },
        )
        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=[0.1] * EMBEDDING_DIM):
                with patch("core.rag._find_nearest", new_callable=AsyncMock, return_value=[document]) as nearest:
                    result = await search_knowledge("lei", limit=3)

        assert result[0]["similarity"] == 0.9
        assert nearest.await_args.args[1] == SHARED_COLLECTION
        database.collection.return_value.stream.assert_not_called()


class TestConversationMemory:
    @pytest.mark.asyncio
    async def test_index_message_skips_missing_embedding(self):
        from core.rag import index_conversation_message

        with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=None):
            with patch("core.rag._get_firestore") as firestore:
                result = await index_conversation_message("5511999999999", "mensagem", "in")

        assert result == {"status": "skipped", "reason": "embedding_unavailable"}
        firestore.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_message_writes_masked_v2_document(self):
        from core.rag import EMBEDDING_DIM, MEMORY_COLLECTION, SCHEMA_VERSION, index_conversation_message

        database = MagicMock()
        with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=[0.1] * EMBEDDING_DIM):
            with patch("core.rag._get_firestore", return_value=database):
                result = await index_conversation_message(
                    "+5511999999999",
                    "Email pessoa@example.com",
                    "in",
                    message_id="message-1",
                    conversation_id="conversation-1",
                    turn_id="turn-1",
                    agent_id="jennifier",
                )

        assert result["status"] == "indexed"
        database.collection.assert_called_once_with(MEMORY_COLLECTION)
        data = database.collection.return_value.document.return_value.set.call_args.args[0]
        assert data["schema_version"] == SCHEMA_VERSION
        assert data["embedding_dim"] == EMBEDDING_DIM
        assert data["text_masked"] == "Email [MASK_EMAIL]"
        assert "5511999999999" not in str(data)
        assert data["expires_at"].endswith("-03:00")

    @pytest.mark.asyncio
    async def test_search_memory_preserves_agent_identity(self):
        from core.rag import EMBEDDING_DIM, search_conversation_memory

        document = FakeDocument(
            "memory-1",
            {
                "text_masked": "resultado interno",
                "direction": "out",
                "agent_id": "manager-web",
                "response_identity": "Jennifer",
                "vector_distance": 0.2,
            },
        )
        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=[0.1] * EMBEDDING_DIM):
                with patch("core.rag._find_nearest", new_callable=AsyncMock, return_value=[document]):
                    result = await search_conversation_memory("5511999999999", "resultado")

        assert result[0]["agent_id"] == "manager-web"
        assert result[0]["response_identity"] == "Jennifer"
        assert result[0]["score"] == pytest.approx(0.8)


class TestKnowledgeIndexing:
    @pytest.mark.asyncio
    async def test_private_document_uses_fixed_collection_and_vector(self):
        from core.rag import EMBEDDING_DIM, PRIVATE_COLLECTION, index_private_document

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch("core.rag.embed_documents", new_callable=AsyncMock, return_value=[[0.1] * EMBEDDING_DIM]):
                result = await index_private_document(
                    "+5511999999999",
                    "conteudo juridico",
                    "fonte juridica",
                )

        assert result["chunks"] == 1
        reference = database.collection.return_value.document.return_value
        database.collection.assert_called_with(PRIVATE_COLLECTION)
        data = database.batch.return_value.set.call_args.args[1]
        assert data["embedding_dim"] == EMBEDDING_DIM
        assert data["owner_hash"] == result["owner_hash"]
        assert data["vector_embedding"].__class__.__name__ == "Vector"
        assert reference is not None

    @pytest.mark.asyncio
    async def test_shared_document_rejects_failed_embedding(self):
        from core.rag import index_shared_document

        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=None):
                with pytest.raises(ValueError, match="embedding_failed"):
                    await index_shared_document("titulo", "conteudo")

    @pytest.mark.asyncio
    async def test_shared_document_id_is_idempotent(self):
        from core.rag import EMBEDDING_DIM, SHARED_COLLECTION, index_shared_document

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=[0.1] * EMBEDDING_DIM):
                first = await index_shared_document("titulo", "conteudo")
                second = await index_shared_document("titulo", "conteudo")

        assert first == second
        assert database.collection.call_args.args[0] == SHARED_COLLECTION
        data = database.collection.return_value.document.return_value.set.call_args.args[0]
        assert data["vector_embedding"].__class__.__name__ == "Vector"
        assert data["created_at"].endswith("-03:00")

    @pytest.mark.asyncio
    async def test_legal_search_uses_cosine_similarity_without_division(self):
        from core.rag import EMBEDDING_DIM, search_legal_knowledge

        document = FakeDocument(
            "legal-1",
            {
                "text_content": "artigo",
                "source_title": "codigo",
                "vector_distance": 0.2,
            },
        )
        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", new_callable=AsyncMock, return_value=[0.1] * EMBEDDING_DIM):
                with patch("core.rag._find_nearest", new_callable=AsyncMock, return_value=[document]):
                    result = await search_legal_knowledge("5511999999999", "artigo")

        assert result["results"][0]["score"] == pytest.approx(0.8)


class TestVectorLGPD:
    def test_delete_user_data_removes_vector_collections(self):
        from core.lgpd import RAG_MEMORY_COLLECTION, RAG_PRIVATE_COLLECTION, delete_user_data

        database = MagicMock()
        contact_reference = MagicMock()
        contact_reference.collection.return_value.stream.return_value = []
        contacts = MagicMock()
        contacts.document.return_value = contact_reference
        nickname_collection = MagicMock()
        memory_collection = MagicMock()
        private_collection = MagicMock()
        memory_query = MagicMock()
        private_query = MagicMock()
        memory_collection.where.return_value = memory_query
        private_collection.where.return_value = private_query
        memory_query.limit.return_value.stream.return_value = []
        private_query.limit.return_value.stream.return_value = []

        def collection(name):
            if name == "contatos":
                return contacts
            if name == "apelidos_custom":
                return nickname_collection
            if name == RAG_MEMORY_COLLECTION:
                return memory_collection
            if name == RAG_PRIVATE_COLLECTION:
                return private_collection
            return MagicMock()

        database.collection.side_effect = collection
        with patch("core.lgpd._get_firestore", return_value=database):
            result = delete_user_data("+5511999999999")

        assert f"{RAG_MEMORY_COLLECTION}:0" in result["deleted"]
        assert f"{RAG_PRIVATE_COLLECTION}:0" in result["deleted"]
        memory_collection.where.assert_called_once()
        private_collection.where.assert_called_once()


class TestIndexTaskTracking:
    @pytest.mark.asyncio
    async def test_indexing_task_is_tracked_until_completion(self):
        from orchestrator import _indexing_tasks, _schedule_indexing

        async def work():
            return True

        task = _schedule_indexing(work())
        assert task in _indexing_tasks
        result = await task
        assert result is True
        assert task not in _indexing_tasks
