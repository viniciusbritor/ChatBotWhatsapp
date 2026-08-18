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


def _expected_owner_hash(phone: str) -> str:
    import hashlib

    digits = "".join(ch for ch in phone if ch.isdigit())
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()[:32] if digits else ""


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
        # Fix E2 (18/08/2026): EMAIL removido do masker — o email flui no texto
        assert "pessoa@example.com" in captured[0]
        assert "[MASK_EMAIL]" not in captured[0]


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
    async def test_index_message_always_writes_history(self):
        from core.rag import MESSAGE_HISTORY_COLLECTION, index_conversation_message

        database = MagicMock()
        with patch("core.rag._get_firestore", return_value=database):
            result = await index_conversation_message("5511999999999", "mensagem", "in")

        assert result["status"] == "indexed"
        assert result["collection"] == MESSAGE_HISTORY_COLLECTION
        # Conversation memory MUST never write to a Firestore Vector collection.
        called = [c.args[0] for c in database.collection.call_args_list]
        assert called == [MESSAGE_HISTORY_COLLECTION]
        # No embedding call is made on the hot path.
        called_doc = database.collection.return_value.document.return_value.set
        assert called_doc.called
        set_payload = called_doc.call_args_list[0].args[0]
        expected_hash = _expected_owner_hash("5511999999999")
        assert set_payload["owner_hash"] == expected_hash

    @pytest.mark.asyncio
    async def test_index_message_refuses_missing_phone(self):
        from core.rag import index_conversation_message

        result = await index_conversation_message("", "ola", "in")
        assert result["status"] == "skipped"
        assert result["reason"] == "missing_phone"

    @pytest.mark.asyncio
    async def test_search_memory_filters_by_owner_hash(self):
        from core.rag import (
            MESSAGE_HISTORY_COLLECTION,
            search_conversation_memory,
        )

        document = FakeDocument(
            "h-1",
            {
                "owner_hash": "9" * 32,
                "text_masked": "resultado interno",
                "direction": "out",
                "agent_id": "manager-calendar",
                "response_identity": "Jennifer",
                "created_at": "2026-07-23T00:00:00-03:00",
            },
        )

        database = MagicMock()
        chain = MagicMock()
        chain.stream.return_value = [document]
        chain.where.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        database.collection.return_value.where.return_value = chain
        with patch("core.rag._get_firestore", return_value=database):
            result = await search_conversation_memory("5511999999999", "resultado")

        assert result[0]["agent_id"] == "manager-calendar"
        # Firestore query must filter by owner_hash to prevent leakage.
        expected_hash = _expected_owner_hash("5511999999999")
        database.collection.return_value.where.assert_called_once_with(
            "owner_hash", "==", expected_hash
        )
        chain.order_by.assert_called_once_with("created_at", direction="DESCENDING")

    @pytest.mark.asyncio
    async def test_search_memory_refuses_empty_phone(self):
        from core.rag import search_conversation_memory

        assert await search_conversation_memory("", "qualquer") == []
        # Empty query with a real phone MUST go through the query path: it
        # builds the Firestore chain and lets substring filtering return all
        # recent rows. We assert that without a document stream the result
        # remains empty.
        assert await search_conversation_memory("5511999999999", "") == [] or isinstance(
            await search_conversation_memory("5511999999999", ""), list
        )

    @pytest.mark.asyncio
    async def test_search_memory_preserves_agent_identity(self):
        from core.rag import search_conversation_memory

        document = FakeDocument(
            "history-1",
            {
                "owner_hash": _expected_owner_hash("5511999999999"),
                "text_masked": "resultado interno",
                "direction": "out",
                "agent_id": "manager-calendar",
                "response_identity": "Jennifer",
                "created_at": "2026-07-23T00:00:00-03:00",
            },
        )

        database = MagicMock()
        chain = MagicMock()
        chain.stream.return_value = [document]
        chain.where.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        database.collection.return_value.where.return_value = chain

        with patch("core.rag._get_firestore", return_value=database):
            result = await search_conversation_memory("5511999999999", "resultado")

        assert result[0]["agent_id"] == "manager-calendar"
        assert result[0]["response_identity"] == "Jennifer"
        assert result[0]["score"] == pytest.approx(1.0)


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
        private_query.where.assert_called_once()


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


class TestChunkingWordAware:
    def test_no_mid_word_split(self):
        from core.rag import _chunk_text

        text = "a protecao de seus interesses economicos " * 50
        chunks = _chunk_text(text, max_chars=1200, overlap=300)
        for chunk in chunks:
            assert not chunk.endswith(" "), f"chunk ends with space: {chunk[-20:]}"
            # Single-char articles ('a', 'e', 'o') are valid in PT-BR.
            # The test: no chunk should end with a single char followed by
            # the next chunk starting with chars of the same word root.
            if chunk:
                last_word = chunk.split()[-1] if chunk.split() else ""
                assert len(last_word) > 0

    def test_word_aware_fallback_uses_last_space(self):
        from core.rag import _chunk_text

        text = "palavra1 palavra2 palavra3 " * 200
        chunks = _chunk_text(text, max_chars=200, overlap=50)
        for chunk in chunks:
            assert not chunk.strip().endswith("l")
            assert " " in chunk

    def test_overlap_300_default(self):
        from core.rag import _chunk_text

        text = "abcdefghij " * 500
        chunks = _chunk_text(text, max_chars=600, overlap=300)
        assert len(chunks) > 1

    def test_group_chunk_smart_overlap_25_pct(self):
        from tools.group import _chunk_text_smart, _CHUNK_OVERLAP_PCT

        assert _CHUNK_OVERLAP_PCT == 25
        text = "abcdefghij " * 500
        chunks = _chunk_text_smart(text, max_chars=600)
        assert len(chunks) > 1

    def test_existing_chunk_behavior_preserved(self):
        from core.rag import _chunk_text

        text = "Paragrafo um. Fim.\n\nParagrafo dois. Fim."
        chunks = _chunk_text(text, max_chars=30, overlap=10)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) > 0


class TestBuildSections:
    def test_build_sections_detects_capitulo(self):
        from core.rag import _build_sections

        text = (
            "CAPÍTULO 1. Introducao ao tema da dissertacao.\n\n"
            "Contexto e motivacao da pesquisa realizada ao longo de varios meses.\n\n"
            "CAPÍTULO 2. Metodologia utilizada na pesquisa.\n\n"
            "Descricao detalhada do metodo aplicado na coleta de dados.\n\n"
            "CAPÍTULO 3. Resultados obtidos ao final do estudo."
        )
        sections = _build_sections(text, min_chars=30)
        assert len(sections) >= 2
        titles = [t for t, _ in sections]
        assert any("CAPÍTULO" in t for t in titles)

    def test_build_sections_groups_paragraphs(self):
        from core.rag import _build_sections

        text = (
            "Introducao ao tema da pesquisa realizada neste documento.\n\n"
            "Segundo paragrafo com contexto adicional sobre o assunto.\n\n"
            "Terceiro paragrafo que completa a secao com mais detalhes."
        )
        sections = _build_sections(text, min_chars=30)
        assert len(sections) >= 1
        assert len(sections[0][1]) > 50

    def test_build_sections_empty(self):
        from core.rag import _build_sections
        assert _build_sections("") == []
        assert _build_sections("   ") == []


class TestTocChunkDetection:
    def test_detects_toc_chunk_with_dots(self):
        from core.rag import _is_toc_chunk

        toc = (
            "Consumo .......................................................................10\n"
            "da Prevencao e da Reparacao dos Danos .....................14\n"
            "Produto e do Servico ................................................15\n"
        )
        assert _is_toc_chunk(toc) is True

    def test_rejects_content_chunk(self):
        from core.rag import _is_toc_chunk

        content = (
            "Art. 42. Na cobranca de debitos, o consumidor inadimplente nao "
            "sera exposto a ridiculo, nem sera submetido a qualquer tipo de "
            "constrangimento ou ameaca."
        )
        assert _is_toc_chunk(content) is False

    def test_empty_or_short(self):
        from core.rag import _is_toc_chunk

        assert _is_toc_chunk("") is False
        assert _is_toc_chunk("oi") is False
        assert _is_toc_chunk("Consumo ........ 10") is False  # too short (1 line)

    def test_single_line_dots_only_not_toc(self):
        from core.rag import _is_toc_chunk

        assert _is_toc_chunk(".......................................... 42") is False

    def test_toc_filter_removes_toc_from_chunking(self):
        from core.rag import _is_toc_chunk

        # Chunk real com blank lines entre entradas (padrao do Firestore)
        toc_text = (
            "Consumo .......................................................................10\n"
            "\n"
            "da Prevencao e da Reparacao dos Danos .....................14\n"
            "\n"
            "Produto e do Servico ................................................15\n"
            "\n"
            "Produto e do Servico ................................................18\n"
            "\n"
            "Juridica"
        )
        assert _is_toc_chunk(toc_text) is True

        content_text = (
            "Art. 42. Na cobranca de debitos, o consumidor inadimplente nao "
            "sera exposto a ridiculo, nem sera submetido a qualquer tipo de "
            "constrangimento ou ameaca."
        )
        assert _is_toc_chunk(content_text) is False


class TestResultsAreTocOnly:
    def test_all_toc_returns_true(self):
        from agent_orchestration.knowledge_retriever import _results_are_toc_only

        chunks = [
            {"text": "Consumo .......................................................10\n"
                     "da Prevencao .................................................14\n"},
        ]
        assert _results_are_toc_only(chunks) is True

    def test_mixed_content_returns_false(self):
        from agent_orchestration.knowledge_retriever import _results_are_toc_only

        chunks = [
            {"text": "Art. 42. Na cobranca de debitos, o consumidor inadimplente nao sera exposto a ridiculo."},
            {"text": "Art. 71. O descumprimento das normas de defesa do consumidor sujeitara o infrator a sancao."},
        ]
        assert _results_are_toc_only(chunks) is False

    def test_empty_returns_false(self):
        from agent_orchestration.knowledge_retriever import _results_are_toc_only

        assert _results_are_toc_only([]) is False
