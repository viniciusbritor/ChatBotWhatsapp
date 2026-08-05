"""Testes isolados do source_title_resolver — Opcao D.

Validam que o LLM dedicado acerta matching de documentos sem
depender de Firestore nem knowledge_retriever.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


class TestResolveCore:
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_llm_matches_correct_source(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "ata_reuniao_2024.pdf"

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["ata_reuniao_2024.pdf", "tese_vinicius.pdf", "lgpd.pdf"],
                    "sobre o que se trata a ata da reuniao de abril?",
                )
        assert result == "ata_reuniao_2024.pdf"

    @pytest.mark.asyncio
    async def test_llm_no_match_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = ""

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["ata_reuniao_2024.pdf"],
                    "qual o cardapio do restaurante?",
                )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_answer_not_in_list_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "documento_que_nao_existe.pdf"

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["ata_reuniao_2024.pdf", "lgpd.pdf"],
                    "me fala sobre o edital de 2025",
                )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_case_insensitive_match(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "ATA_REUNIAO_2024.PDF"

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["ata_reuniao_2024.pdf"],
                    "ata de abril",
                )
        assert result == "ata_reuniao_2024.pdf"

    @pytest.mark.asyncio
    async def test_empty_sources_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        result = await resolve([], "qualquer coisa")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_query_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        result = await resolve(["doc.pdf"], "")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        with patch.dict("os.environ", {}, clear=True):
            result = await resolve(["doc.pdf"], "query")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_exception_returns_none(self):
        from agent_orchestration.source_title_resolver import resolve

        class FailingLLM:
            def invoke(self, prompt):
                raise RuntimeError("LLM crash")

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: (_ for _ in ()).throw(RuntimeError("crash"))})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=FailingLLM()):
                result = await resolve(["doc.pdf"], "query")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_returns_whitespace_only(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "   \n\t  "

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(["doc.pdf"], "query")
        assert result is None


class TestResolveContext:
    @pytest.mark.asyncio
    async def test_understands_synonyms(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "tese_vinicius.pdf"

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["codigo_consumidor.pdf", "tese_vinicius.pdf", "lgpd.pdf"],
                    "aquele pdf de doutorado que o vinicius escreveu",
                )
        assert result == "tese_vinicius.pdf"

    @pytest.mark.asyncio
    async def test_understands_academic_context(self):
        from agent_orchestration.source_title_resolver import resolve

        class FakeResponse:
            content = "dissertacao_vinicius.pdf"

        fake_llm = type("FakeLLM", (), {"invoke": lambda self, prompt: FakeResponse()})()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake"}):
            with patch("langchain_openai.ChatOpenAI", return_value=fake_llm):
                result = await resolve(
                    ["tese_vinicius.pdf", "dissertacao_vinicius.pdf"],
                    "o trabalho de mestrado do vinicius",
                )
        assert result == "dissertacao_vinicius.pdf"


class TestResolveIntegration:
    """Testa que retrieve() usa o resolver como fallback sem quebrar o existente."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_resolver_not_called_when_hints_has_source_title(self):
        from agent_orchestration import knowledge_retriever

        with patch.object(
            knowledge_retriever, "_extract_query_hints",
            AsyncMock(return_value={
                "source_title": "tese_vinicius.pdf",
                "enriched_query": "tese",
            }),
        ):
            with patch.object(
                knowledge_retriever, "_retrieve_private",
                AsyncMock(return_value={"results": [], "count": 0, "scope": "private"}),
            ):
                result = await knowledge_retriever.retrieve(
                    {"phone": "5511999", "extra": {}},
                    "o que diz a tese?",
                )
        assert result["filters"].get("source_title") == "tese_vinicius.pdf"

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_resolver_called_when_hints_empty(self):
        from agent_orchestration import knowledge_retriever

        with patch.object(
            knowledge_retriever, "_extract_query_hints",
            AsyncMock(return_value={"enriched_query": "ata reuniao"}),
        ):
            with patch.object(
                knowledge_retriever, "_list_known_sources",
                AsyncMock(return_value=["ata_reuniao_2024.pdf"]),
            ):
                with patch(
                    "agent_orchestration.source_title_resolver.resolve",
                    AsyncMock(return_value="ata_reuniao_2024.pdf"),
                ):
                    with patch.object(
                        knowledge_retriever, "_retrieve_private",
                        AsyncMock(return_value={"results": [], "count": 0, "scope": "private"}),
                    ):
                        result = await knowledge_retriever.retrieve(
                            {"phone": "5511999", "extra": {}},
                            "sobre a ata de abril",
                        )
        assert result["filters"].get("source_title") == "ata_reuniao_2024.pdf"
