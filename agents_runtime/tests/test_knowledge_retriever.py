"""Tests for agent_orchestration/knowledge_retriever.py (Fase H)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRagHeuristic:
    def test_detects_rag_keyword(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("me diz o que memorizei do pdf")
        assert _looks_like_rag_query("tem algo na base de conhecimento sobre isso?")
        assert _looks_like_rag_query("o documento que salvamos ontem")
        assert _looks_like_rag_query("qual era o conteudo do pdf que mandei?")

    def test_does_not_detect_greeting(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert not _looks_like_rag_query("oi")
        assert not _looks_like_rag_query("obrigado")

    def test_empty_returns_false(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert not _looks_like_rag_query("")


class TestRetrievePrivate:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results_from_private_collection(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        fake_chunks = [
            {
                "text": "Chunk A",
                "score": 0.9,
                "source": "doc.pdf",
            }
        ]
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={
                "results": fake_chunks,
                "owner_hash": "abc",
            }),
        ):
            result = await retrieve(envelope, "o que tem no pdf?", limit=3, min_score=0.3)
        assert result["decision"] == "private"
        assert result["count"] == 1
        assert result["results"][0]["source"] == "doc.pdf"

    @pytest.mark.asyncio
    async def test_retrieve_private_no_results(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": [], "owner_hash": "abc"}),
        ):
            result = await retrieve(envelope, "irrelevante", limit=3, min_score=0.5)
        assert result["decision"] == "needs_clarification"
        assert result["count"] == 0


class TestRetrieveGroup:
    @pytest.mark.asyncio
    async def test_group_member_returns_results(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = True
        member_doc.to_dict.return_value = {"is_active": True}
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            with patch(
                "agent_orchestration.knowledge_retriever.search_group_knowledge",
                AsyncMock(return_value={
                    "results": [{"text": "x", "score": 0.7, "source_name": "ata.pdf"}],
                    "count": 1,
                }),
            ):
                result = await retrieve(envelope, "qual a ata?", limit=3, min_score=0.5)
        assert result["decision"] == "group"
        assert result["count"] == 1
        assert result["scope"] == "group"

    @pytest.mark.asyncio
    async def test_group_non_member_denied(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = False
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            result = await retrieve(envelope, "qualquer coisa", limit=3, min_score=0.5)
        assert result["decision"] == "denied"
        assert result["reason"] == "not_member"


class TestCrossScopePrivateInGroup:
    @pytest.mark.asyncio
    async def test_private_match_in_group_creates_pending_share(self):
        from agent_orchestration.knowledge_retriever import retrieve

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "120363123@g.us"},
        }
        db = MagicMock()
        member_doc = MagicMock()
        member_doc.exists = True
        member_doc.to_dict.return_value = {"is_active": True}
        db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = member_doc

        with patch("core.rag._get_firestore", return_value=db):
            with patch(
                "agent_orchestration.knowledge_retriever.search_group_knowledge",
                AsyncMock(return_value={"results": [], "count": 0}),
            ):
                with patch(
                    "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                    AsyncMock(return_value={
                        "results": [{"text": "p", "score": 0.8, "source": "privado.pdf"}],
                        "owner_hash": "abc",
                    }),
                ):
                    with patch(
                        "core.pending_actions.set_pending_action",
                        AsyncMock(return_value={"action_type": "share_private_knowledge_in_group"}),
                    ) as mock_set:
                        result = await retrieve(envelope, "doc privado", limit=3, min_score=0.5)
        assert result["decision"] == "group_private_share_pending"
        assert result["needs_share_prompt"] is True
        assert mock_set.called
        assert mock_set.call_args.args[1] == "share_private_knowledge_in_group"


class TestRetrievalCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(self):
        from agent_orchestration.knowledge_retriever import (
            retrieve, _RETRIEVAL_CACHE,
        )

        _RETRIEVAL_CACHE.clear()
        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        mock = AsyncMock(return_value={
            "results": [
                {"text": "c1", "score": 0.9, "source": "x.pdf", "class": "legal"}
            ],
            "owner_hash": "abc",
        })
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            mock,
        ):
            first = await retrieve(envelope, "minha query")
            second = await retrieve(envelope, "minha query")
        # Only the first call hit search; second was served from cache.
        assert mock.await_count == 1
        assert second.get("cache_hit") is True
        assert first.get("count") == second.get("count") == 1

    @pytest.mark.asyncio
    async def test_cache_miss_different_query(self):
        from agent_orchestration.knowledge_retriever import (
            retrieve, _RETRIEVAL_CACHE,
        )

        _RETRIEVAL_CACHE.clear()
        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        mock = AsyncMock(return_value={
            "results": [], "owner_hash": "abc",
        })
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            mock,
        ):
            await retrieve(envelope, "query A")
            await retrieve(envelope, "query B")
        assert mock.await_count == 2

    def test_cache_set_respects_max_size(self):
        from agent_orchestration.knowledge_retriever import (
            _cache_set, _RETRIEVAL_CACHE,
        )

        _RETRIEVAL_CACHE.clear()
        for i in range(300):
            _cache_set(f"k{i}", {"data": i})
        assert len(_RETRIEVAL_CACHE) <= 256


class TestSharePendingConsume:
    @pytest.mark.asyncio
    async def test_consume_returns_action(self):
        from agent_orchestration import knowledge_retriever

        action = {"action_type": "share_private_knowledge_in_group", "payload": {}}
        with patch(
            "core.pending_actions.consume_pending_action",
            AsyncMock(return_value=action),
        ):
            result = await knowledge_retriever.share_pending_action_consume("5511999")
        assert result["action_type"] == "share_private_knowledge_in_group"


class TestRetrievalMetrics:
    def test_dataclass_serializes(self):
        from agent_orchestration.knowledge_retriever import RetrievalMetrics

        m = RetrievalMetrics(
            query_hash="abc",
            scope="private",
            decision="private",
            min_score=0.7,
            candidates=3,
            returned=3,
        )
        data = m.to_dict()
        assert data["query_hash"] == "abc"
        assert data["scope"] == "private"
        assert data["decision"] == "private"
        assert data["min_score"] == 0.7
        assert data["candidates"] == 3
        assert data["classes"] == []
        assert data["sources"] == []

    def test_summarize_results_empty(self):
        from agent_orchestration.knowledge_retriever import _summarize_results

        s = _summarize_results([])
        assert s["classes"] == []
        assert s["sources"] == []
        assert s["top_score"] == 0.0
        assert s["avg_score"] == 0.0

    def test_summarize_results_with_data(self):
        from agent_orchestration.knowledge_retriever import _summarize_results

        chunks = [
            {"class": "legal", "source": "cdc.pdf", "score": 0.9},
            {"class": "legal", "source": "cdc.pdf", "score": 0.7},
            {"class": "outros", "source": "x.pdf", "score": 0.5},
        ]
        s = _summarize_results(chunks)
        assert s["classes"] == ["legal", "legal", "outros"]
        assert s["sources"] == ["cdc.pdf", "cdc.pdf", "x.pdf"]
        assert s["top_score"] == 0.9
        assert abs(s["avg_score"] - 0.7) < 1e-9


class TestAdaptiveMinScore:
    """Valida o adaptive threshold em core/rag.py::search_legal_knowledge.

    Producao (Fase F4d.6) usa RAG_RETRIEVE_MIN_SCORE=0.7 mas scores
    reais de docs pequenos ficam em 0.4-0.65. Sem o floor, queries
    legitimas como "qual a principal lei do cdc?" (top=0.55) sao
    truncadas para 0 hits.
    """

    @pytest.mark.asyncio
    async def test_adaptive_delivers_below_min_score_when_floor_reached(self):
        """Doc com score 0.5 deve ser entregue mesmo com min_score=0.7."""
        from core.rag import search_legal_knowledge

        fake_doc = _make_fake_doc(
            doc_id="d1",
            source_title="cdc.pdf",
            score=0.5,
            text_content="Disposicoes gerais do CDC",
        )

        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", AsyncMock(return_value=[0.0] * 1536)):
                with patch("core.rag._find_nearest", AsyncMock(return_value=[fake_doc])):
                    with patch("core.rag._vector_filters", return_value=None):
                        result = await search_legal_knowledge(
                            phone="5511966830020",
                            query="cdc disposicoes gerais",
                            k=5,
                            min_score=0.7,
                        )

        assert len(result["results"]) >= 1
        assert result["results"][0]["source"] == "cdc.pdf"
        assert result["results"][0]["score"] == 0.5
        assert result["top_score"] == pytest.approx(0.5, abs=0.01)
        assert result["adaptive_floor"] == 0.3
        assert result["min_score"] == 0.7

    @pytest.mark.asyncio
    async def test_adaptive_skips_below_floor(self):
        """Doc com score 0.2 (abaixo do floor) NAO deve ser entregue."""
        from core.rag import search_legal_knowledge

        fake_doc = _make_fake_doc(
            doc_id="d1",
            source_title="ruido.pdf",
            score=0.2,
            text_content="texto completamente irrelevante",
        )

        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", AsyncMock(return_value=[0.0] * 1536)):
                with patch("core.rag._find_nearest", AsyncMock(return_value=[fake_doc])):
                    with patch("core.rag._vector_filters", return_value=None):
                        result = await search_legal_knowledge(
                            phone="5511966830020",
                            query="cdc",
                            k=5,
                            min_score=0.7,
                        )

        assert result["results"] == []
        assert result["top_score"] == pytest.approx(0.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_adaptive_keeps_top_match_respecting_floor(self):
        """Top-3 com mix de scores: top=0.5 mantido, 0.4 mantido, 0.1 descartado."""
        from core.rag import search_legal_knowledge

        docs = [
            _make_fake_doc(
                doc_id=f"d{i}",
                source_title=f"doc{i}.pdf",
                score=score,
                text_content=f"chunk {i}",
            )
            for i, score in enumerate([0.5, 0.4, 0.1, 0.05])
        ]

        with patch("core.rag._get_firestore", return_value=MagicMock()):
            with patch("core.rag.embed_query", AsyncMock(return_value=[0.0] * 1536)):
                with patch("core.rag._find_nearest", AsyncMock(return_value=docs)):
                    with patch("core.rag._vector_filters", return_value=None):
                        result = await search_legal_knowledge(
                            phone="5511966830020",
                            query="cdc",
                            k=5,
                            min_score=0.7,
                        )

        scores_kept = [c["score"] for c in result["results"]]
        assert 0.5 in scores_kept
        assert 0.4 in scores_kept
        assert 0.1 not in scores_kept
        assert 0.05 not in scores_kept
        assert result["top_score"] == 0.5


def _make_fake_doc(
    doc_id: str,
    source_title: str,
    score: float,
    text_content: str,
):
    class _FakeDoc:
        def __init__(self, doc_id, fields, distance):
            self.id = doc_id
            self._fields = fields

        def to_dict(self):
            return self._fields

    return _FakeDoc(
        doc_id=doc_id,
        fields={
            "source_title": source_title,
            "text_content": text_content,
            "class": "legal",
            "group": "legislacao",
            "theme": "cdc",
            "vector_distance": 1.0 - score,
        },
        distance=1.0 - score,
    )


def _mock_firestore():
    """Stub para ``_get_firestore``: retorna um marker nao-None."""

    def _stub():
        return MagicMock()

    return _stub


class TestClarificationPrompt:
    """UX: clarification_prompt lista source_title conhecidos do owner."""

    def test_prompt_lists_known_sources(self):
        from agent_orchestration.knowledge_retriever import (
            _build_clarification_prompt,
        )

        prompt = _build_clarification_prompt(
            ["cdc-capitulo-1.pdf", "lgpd-capitulo-1.pdf"],
            "edital",
        )
        assert "cdc-capitulo-1.pdf" in prompt
        assert "lgpd-capitulo-1.pdf" in prompt
        assert "N\u00e3o encontrei" in prompt
        # Mensagem deve orientar o user a refinar (mencionar termo/arquivo).
        assert "busca" in prompt.lower() or "arquivo" in prompt.lower() or "termo" in prompt.lower()

    def test_prompt_fallback_when_empty(self):
        from agent_orchestration.knowledge_retriever import (
            _build_clarification_prompt,
        )

        prompt = _build_clarification_prompt([], "qualquer coisa")
        assert "Voc\u00ea tem esses documentos" not in prompt
        assert "N\u00e3o encontrei" in prompt
        assert "mais detalhes" in prompt or "outro termo" in prompt


class TestExtractPhone:
    """Cobre os 3 formatos de envelope que o retriever recebe:

    1. webhook canonico (orchestrator direto): envelope["phone"]
    2. DeepAgents state (via tool de LangChain): envelope["user"]["phone"]
    3. vazio (sinal de bug no caller)

    Patch 01/08/2026: o caminho #2 era ignorado, causando
    _owner_hash("") = hash de string vazia -> find_nearest sem
    owner_match -> 0 hits para qualquer RAG privado via
    DeepAgents (incluindo conversas privadas normais).
    """

    def test_extract_phone_root_canonical(self):
        """Path #1: envelope chega direto do orchestrator com phone na raiz."""
        from agent_orchestration.knowledge_retriever import _extract_phone

        envelope = {"phone": "5511966830020", "remote_jid": "...@s.whatsapp.net"}
        assert _extract_phone(envelope) == "5511966830020"

    def test_extract_phone_user_nested_deepagents(self):
        """Path #2 (BUG): DeepAgents injetou phone em envelope.user.phone."""
        from agent_orchestration.knowledge_retriever import _extract_phone

        envelope = {
            "user": {
                "name": "Vinicius Rocha",
                "phone": "5511966830020",
                "first_name": "Vinicius",
            },
            "message": "...",
        }
        assert _extract_phone(envelope) == "5511966830020"

    def test_extract_phone_root_wins_over_user(self):
        """Path #1 tem prioridade sobre #2 (telefone direto e' mais confiavel)."""
        from agent_orchestration.knowledge_retriever import _extract_phone

        envelope = {
            "phone": "5511966830020",
            "user": {"phone": "5544444444444"},
        }
        assert _extract_phone(envelope) == "5511966830020"

    def test_extract_phone_missing_logs_warning(self):
        """Path #3: envelope sem phone em lugar nenhum -> log warning."""
        from agent_orchestration import knowledge_retriever

        envelope = {"user": {"name": "Vini"}, "message": "..."}  # sem phone
        with patch.object(knowledge_retriever.logger, "warning") as mock_warn:
            result = knowledge_retriever._extract_phone(envelope)
        assert result == ""
        mock_warn.assert_called_once()
        # verifica que a mensagem de warn cita as chaves disponiveis
        assert "extract_phone_empty" in mock_warn.call_args.args[0]
        assert "envelope_keys" in mock_warn.call_args.args[0]

    def test_extract_phone_none_or_empty_input(self):
        """Path #3 edge case: envelope None ou vazio."""
        from agent_orchestration.knowledge_retriever import _extract_phone

        assert _extract_phone(None) == ""
        assert _extract_phone({}) == ""
        assert _extract_phone("") == ""


class TestRerank:
    @pytest.mark.asyncio
    async def test_rerank_skips_when_no_api_key(self):
        from agent_orchestration import knowledge_retriever

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            chunks = [{"text": f"c{i}", "score": 0.9 - i * 0.1} for i in range(5)]
            out = await knowledge_retriever._rerank_with_llm(
                "query", chunks, top_n=3
            )
        # Without DEEPSEEK_API_KEY, re-ranking is skipped entirely.
        assert out == chunks
        assert len(out) == 5

    @pytest.mark.asyncio
    async def test_rerank_skips_when_too_few_chunks(self):
        from agent_orchestration import knowledge_retriever

        chunks = [{"text": "c1", "score": 0.9}]
        out = await knowledge_retriever._rerank_with_llm(
            "query", chunks, top_n=3
        )
        assert out == chunks

    @pytest.mark.asyncio
    async def test_rerank_with_mocked_llm(self):
        from agent_orchestration import knowledge_retriever

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            class FakeLLM:
                def invoke(self, msgs):
                    class R:
                        content = "[2, 0, 1]"
                    return R()

            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = FakeLLM()
                chunks = [
                    {"text": "c0", "score": 0.5},
                    {"text": "c1", "score": 0.6},
                    {"text": "c2", "score": 0.9},
                ]
                out = await knowledge_retriever._rerank_with_llm(
                    "query", chunks, top_n=3
                )
        # The key invariant: chunks all come from the original set.
        assert all(c in chunks for c in out)
        assert len(out) <= 3


    @pytest.mark.asyncio
    async def test_retrieve_emits_metrics_log(self, caplog):
        from agent_orchestration import knowledge_retriever

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        chunks = [
            {"text": "c1", "score": 0.9, "source": "cdc.pdf", "class": "legal"},
            {"text": "c2", "score": 0.7, "source": "cdc.pdf", "class": "legal"},
        ]
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": chunks, "owner_hash": "abc"}),
        ):
            caplog.set_level("INFO")
            await knowledge_retriever.retrieve(envelope, "cdc test")
        # Look for our custom log record
        retrieval_logs = [
            r for r in caplog.records
            if getattr(r, "event_name", "") == "retrieval_quality"
        ]
        assert retrieval_logs, "expected retrieval_quality log"
        rec = retrieval_logs[-1]
        assert rec.decision == "private"
        assert rec.returned == 2
        assert rec.top_score == 0.9
        assert rec.classes == ["legal", "legal"]


class TestAboutQueryDetection:
    def test_detects_about_queries(self):
        from agent_orchestration.knowledge_retriever import _is_about_query

        queries = [
            "sobre o que se trata a dissertação vinicius",
            "do que se trata esse documento?",
            "me explique o conteudo do pdf",
            "qual o tema do arquivo?",
            "o que é esse documento sobre?",
            "me fala sobre o que voce guardou",
            "resuma o documento que voce salvou",
            "sobre qual tema é essa tese?",
            "fale sobre o conteudo da ata",
            "qual o resumo do que voce memorizou?",
        ]
        for q in queries:
            assert _is_about_query(q), f"should detect: {q}"

    def test_rejects_non_about_queries(self):
        from agent_orchestration.knowledge_retriever import _is_about_query

        queries = [
            "oi, tudo bem?",
            "qual o artigo 5 do cdc?",
            "liste os documentos",
            "busque por editais na base",
            "qual o prazo do edital 2024?",
            "memorize esse arquivo",
        ]
        for q in queries:
            assert not _is_about_query(q), f"should NOT detect: {q}"

    def test_detects_normalized_accents(self):
        from agent_orchestration.knowledge_retriever import _is_about_query

        assert _is_about_query("sobre o que é a dissertação?")
        assert _is_about_query("qual é o tema do documento?")
        assert _is_about_query("o que é que voce guardou?")


class TestRerankAntiMetadataHints:
    @pytest.mark.asyncio
    async def test_about_query_injects_hint_into_prompt(self):
        from agent_orchestration import knowledge_retriever

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            captured_prompt = []

            class FakeLLM:
                def invoke(self, msgs):
                    captured_prompt.append(msgs[0]["content"])
                    class R:
                        content = "[2, 1, 0]"
                    return R()

            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = FakeLLM()
                chunks = [
                    {"text": "chunk 0: D.Sc. Prof. orientador... ficha catalografica", "score": 0.9},
                    {"text": "chunk 1: agradecimentos aos professores e familia", "score": 0.85},
                    {"text": "chunk 2: introducao: modelos bayesianos para volatilidade", "score": 0.8},
                    {"text": "chunk 3: metodologia de precificacao de opcoes", "score": 0.75},
                ]
                await knowledge_retriever._rerank_with_llm(
                    "sobre o que se trata a dissertacao?",
                    chunks, top_n=3,
                )

            assert len(captured_prompt) == 1
            prompt = captured_prompt[0]
            assert "IMPORTANTE" in prompt
            assert "CONTEUDO SUBSTANTIVO" in prompt
            assert "METADADOS" in prompt
            assert "folha de rosto" in prompt
            assert "agradecimentos" in prompt

    @pytest.mark.asyncio
    async def test_factual_query_omits_hint(self):
        from agent_orchestration import knowledge_retriever

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            captured_prompt = []

            class FakeLLM:
                def invoke(self, msgs):
                    captured_prompt.append(msgs[0]["content"])
                    class R:
                        content = "[2, 0, 1]"
                    return R()

            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = FakeLLM()
                chunks = [
                    {"text": "c0", "score": 0.9},
                    {"text": "c1", "score": 0.8},
                    {"text": "c2", "score": 0.7},
                    {"text": "c3", "score": 0.6},
                ]
                await knowledge_retriever._rerank_with_llm(
                    "qual o artigo 5 do codigo de defesa do consumidor?",
                    chunks, top_n=3,
                )

            assert len(captured_prompt) == 1
            prompt = captured_prompt[0]
            assert "IMPORTANTE" not in prompt
            assert "CONTEUDO SUBSTANTIVO" not in prompt
            assert "METADADOS" not in prompt


class TestRetrieveWithHints:
    @pytest.mark.asyncio
    async def test_extracts_source_title_from_query(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = await _extract_query_hints("5511999", "o que tem no cdc-portugues-2013.pdf sobre saude?")
        assert hints.get("source_title") == "cdc-portugues-2013.pdf"

    @pytest.mark.asyncio
    async def test_extracts_class_hint(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = await _extract_query_hints("5511999", "tem algum edital de licitacao?")
        assert hints.get("class") == "edital"

    @pytest.mark.asyncio
    async def test_no_hints_when_unrelated(self):
        from agent_orchestration.knowledge_retriever import _extract_query_hints

        hints = await _extract_query_hints("5511999", "oi, tudo bem?")
        assert "source_title" not in hints
        assert "class" not in hints

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self):
        from agent_orchestration.knowledge_retriever import retrieve, _RETRIEVAL_CACHE

        _RETRIEVAL_CACHE.clear()
        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        # Mock that respects k=10 by truncating client-side.
        def fake_search(**kwargs):
            k = kwargs.get("k", 10)
            return {"results": [{"text": f"c{i}", "score": 0.9, "source": "x.pdf"} for i in range(k)], "owner_hash": "abc"}
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(side_effect=fake_search),
        ):
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
                result = await retrieve(envelope, "qualquer coisa")
        # search_legal_knowledge is called with k=10 (default), so the mock
        # returns 10 results. Re-ranking is disabled (no API key), so
        # the result keeps all 10.
        assert result["count"] == 10
        assert len(result["results"]) == 10

    @pytest.mark.asyncio
    async def test_no_results_returns_clarification(self):
        from agent_orchestration.knowledge_retriever import retrieve, _RETRIEVAL_CACHE

        _RETRIEVAL_CACHE.clear()
        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        with patch(
            "agent_orchestration.knowledge_retriever.search_legal_knowledge",
            AsyncMock(return_value={"results": [], "owner_hash": "abc"}),
        ):
            result = await retrieve(envelope, "qualquer coisa")
        assert result["decision"] == "needs_clarification"
        assert result["needs_clarification"] is True
        assert "Não encontrei" in result["clarification_prompt"]


class TestSourceTitleAlias:
    @pytest.mark.asyncio
    async def test_static_alias_lgpd(self):
        from agent_orchestration.knowledge_retriever import _match_source_title_alias

        assert _match_source_title_alias("o que diz a lgpd sobre dados?") == (
            "Lei_geral_protecao_dados_pessoais_1ed.pdf"
        )

    @pytest.mark.asyncio
    async def test_static_alias_cdc(self):
        from agent_orchestration.knowledge_retriever import _match_source_title_alias

        assert _match_source_title_alias("qual o artigo 5 do codigo de defesa do consumidor?") == (
            "Codigo-do-consumidor-FINAL.pdf"
        )

    @pytest.mark.asyncio
    async def test_static_alias_no_match(self):
        from agent_orchestration.knowledge_retriever import _match_source_title_alias

        assert _match_source_title_alias("manual de higiene hospitalar") is None

    @pytest.mark.asyncio
    async def test_static_alias_tese(self):
        from agent_orchestration.knowledge_retriever import _match_source_title_alias

        assert _match_source_title_alias("o que diz a tese do vinicius?") == (
            "tese vinicius.pdf"
        )

    @pytest.mark.asyncio
    async def test_static_alias_dissertacao(self):
        from agent_orchestration.knowledge_retriever import _match_source_title_alias

        assert _match_source_title_alias("me fale sobre a dissertacao") == (
            "dissertação vinicius.pdf"
        )


class TestSourceTitleDynamic:
    @pytest.mark.asyncio
    async def test_dynamic_matches_firestore_title(self):
        from agent_orchestration import knowledge_retriever

        fake_sources = [
            "Codigo-do-consumidor-FINAL.pdf",
            "Lei_geral_protecao_dados_pessoais_1ed.pdf",
            "dissertacao vinicius.pdf",
        ]
        with patch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            result = await knowledge_retriever._match_source_title_dynamic(
                "5511999", "sobre o que se trata a dissertacao vinicius?"
            )
        assert result == "dissertacao vinicius.pdf"

    @pytest.mark.asyncio
    async def test_dynamic_requires_two_common_words(self):
        from agent_orchestration import knowledge_retriever

        fake_sources = ["dissertacao vinicius.pdf", "ata_reuniao_2024.pdf"]
        with patch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            result = await knowledge_retriever._match_source_title_dynamic(
                "5511999", "dissertacao"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_dynamic_empty_phone_returns_none(self):
        from agent_orchestration import knowledge_retriever

        result = await knowledge_retriever._match_source_title_dynamic("", "query")
        assert result is None

    @pytest.mark.asyncio
    async def test_dynamic_firestore_failure_returns_none(self):
        from agent_orchestration import knowledge_retriever

        with patch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(side_effect=Exception("firestore down")),
        ):
            result = await knowledge_retriever._match_source_title_dynamic(
                "5511999", "dissertacao vinicius"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_query_hints_uses_dynamic_fallback(self):
        from agent_orchestration import knowledge_retriever

        fake_sources = ["ata_reuniao_2024.pdf"]
        with patch.object(
            knowledge_retriever, "_list_known_sources",
            AsyncMock(return_value=fake_sources),
        ):
            hints = await knowledge_retriever._extract_query_hints(
                "5511999", "sobre o que se trata a ata de reuniao de 2024?"
            )
        assert hints.get("source_title") == "ata_reuniao_2024.pdf"


class TestLLMQueryEnrichment:
    @pytest.mark.asyncio
    async def test_enrich_extracts_subject_from_ambiguous_query(self):
        from agent_orchestration import knowledge_retriever
        import json

        class FakeResponse:
            content = json.dumps({
                "enriched_query": "modelos de precificacao de opcoes abordagem bayesiana",
                "source_hint": "tese",
                "class_hint": "academico",
            })

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=FakeResponse()):
                result = await knowledge_retriever._llm_enrich_query(
                    "aquele negocio de opcoes"
                )
        assert "precificacao" in result["enriched_query"]
        assert result["source_hint"] == "tese"
        assert result["class_hint"] == "academico"

    @pytest.mark.asyncio
    async def test_enrich_preserves_clear_query(self):
        from agent_orchestration import knowledge_retriever
        import json

        class FakeResponse:
            content = json.dumps({
                "enriched_query": "artigo 5 codigo de defesa do consumidor",
                "source_hint": "cdc",
                "class_hint": "legal",
            })

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=FakeResponse()):
                result = await knowledge_retriever._llm_enrich_query(
                    "qual o artigo 5 do cdc?"
                )
        assert "artigo 5" in result["enriched_query"]
        assert result["source_hint"] == "cdc"
        assert result["class_hint"] == "legal"

    @pytest.mark.asyncio
    async def test_enrich_fallback_on_llm_failure(self):
        from agent_orchestration import knowledge_retriever
        import asyncio as _asyncio

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch.object(_asyncio, "to_thread", AsyncMock(side_effect=Exception("LLM down"))):
                result = await knowledge_retriever._llm_enrich_query(
                    "sobre o que se trata a tese?"
                )
        assert result["enriched_query"] == "sobre o que se trata a tese?"
        assert result["source_hint"] == ""
        assert result["class_hint"] == ""

    @pytest.mark.asyncio
    async def test_enrich_fallback_when_no_api_key(self):
        from agent_orchestration import knowledge_retriever

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            result = await knowledge_retriever._llm_enrich_query(
                "sobre o que se trata?"
            )
        assert result["enriched_query"] == "sobre o que se trata?"
        assert result["source_hint"] == ""
        assert result["class_hint"] == ""


class TestRetrieveUsesEnrichedQuery:
    @pytest.mark.asyncio
    async def test_retrieve_uses_enriched_query_in_vector_search(self):
        from agent_orchestration import knowledge_retriever
        import json

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        captured_query = []

        def fake_search(**kwargs):
            captured_query.append(kwargs.get("query", ""))
            return {"results": [], "owner_hash": "abc"}

        class FakeResponse:
            content = json.dumps({
                "enriched_query": "modelos precificacao opcoes bayesianos",
                "source_hint": "",
                "class_hint": "",
            })

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=FakeResponse()):
                with patch(
                    "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                    AsyncMock(side_effect=fake_search),
                ):
                    await knowledge_retriever.retrieve(
                        envelope, "aquele negocio de opcoes que vc memorizou"
                    )

        assert len(captured_query) >= 1
        assert "precificacao" in captured_query[0]

    @pytest.mark.asyncio
    async def test_retrieve_no_longer_calls_rerank(self):
        from agent_orchestration import knowledge_retriever
        import json

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        chunks = [
            {"text": "c1", "score": 0.9, "source": "doc.pdf"},
            {"text": "c2", "score": 0.8, "source": "doc.pdf"},
        ]

        class FakeResponse:
            content = json.dumps({
                "enriched_query": "test query",
                "source_hint": "",
                "class_hint": "",
            })

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=FakeResponse()):
                with patch(
                    "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                    AsyncMock(return_value={"results": chunks, "owner_hash": "abc"}),
                ):
                    with patch(
                        "agent_orchestration.knowledge_retriever._rerank_with_llm",
                        wraps=knowledge_retriever._rerank_with_llm,
                    ) as rerank_spy:
                        knowledge_retriever._RETRIEVAL_CACHE.clear()
                        result = await knowledge_retriever.retrieve(
                            envelope, "test"
                        )

        assert rerank_spy.call_count == 0
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_retrieve_emits_metrics_after_enrichment(self):
        from agent_orchestration import knowledge_retriever
        import json

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        chunks = [
            {"text": "c1", "score": 0.9, "source": "doc.pdf", "class": "legal"},
        ]

        class FakeResponse:
            content = json.dumps({
                "enriched_query": "cdc artigo 5",
                "source_hint": "cdc",
                "class_hint": "legal",
            })

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=FakeResponse()):
                with patch(
                    "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                    AsyncMock(return_value={"results": chunks, "owner_hash": "abc"}),
                ):
                    result = await knowledge_retriever.retrieve(
                        envelope, "qual o artigo 5 do cdc?"
                    )

        assert result["decision"] == "private"
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_enrichment_query_falls_back_to_original_on_llm_down(self):
        from agent_orchestration import knowledge_retriever

        envelope = {
            "phone": "5511999",
            "extra": {"remote_jid": "5511999@s.whatsapp.net"},
        }
        chunks = [{"text": "c1", "score": 0.9, "source": "doc.pdf"}]
        captured_query = []

        def fake_search(**kwargs):
            captured_query.append(kwargs.get("query", ""))
            return {"results": chunks, "owner_hash": "abc"}

        knowledge_retriever._RETRIEVAL_CACHE.clear()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with patch(
                "agent_orchestration.knowledge_retriever.search_legal_knowledge",
                AsyncMock(side_effect=fake_search),
            ):
                result = await knowledge_retriever.retrieve(
                    envelope, "sobre o que se trata a tese?"
                )

        assert result["count"] == 1
        assert "sobre o que se trata a tese" in captured_query[0]