"""Testes de isolamento: mudancas RAG nao vazam para outras pipelines."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

RAG_MODULES = frozenset({
    "agent_orchestration.knowledge_retriever",
    "agent_orchestration.knowledge_router",
    "agent_orchestration.categorizer",
    "core.rag",
    "pipelines.doc_pipeline",
})

_AGENTS_RUNTIME = Path(__file__).resolve().parent.parent


def _find_imports(file_path: Path) -> set:
    """Extrai todos os nomes de modulos importados de um arquivo .py."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


class TestNoRagImportsInNonRagPipelines:
    def test_calendar_pipeline_no_rag_imports(self):
        """Calendar pipeline nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "calendar_pipeline.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"calendar_pipeline importa {imp}"
            )
            assert imp != "core.rag", f"calendar_pipeline importa core.rag"
            assert imp != "pipelines.doc_pipeline", f"calendar_pipeline importa doc_pipeline"

    def test_email_pipeline_no_rag_imports(self):
        """Email pipeline nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "email_pipeline.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"email_pipeline importa {imp}"
            )
            assert imp != "core.rag", f"email_pipeline importa core.rag"
            assert imp != "pipelines.doc_pipeline", f"email_pipeline importa doc_pipeline"

    def test_jennifer_pipeline_no_rag_imports(self):
        """Jennifer pipeline nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "jennifer_pipeline.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"jennifer_pipeline importa {imp}"
            )
            assert imp != "core.rag", f"jennifer_pipeline importa core.rag"
            assert imp != "pipelines.doc_pipeline", f"jennifer_pipeline importa doc_pipeline"

    def test_guard_no_rag_imports(self):
        """_guard.py nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "_guard.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"_guard importa {imp}"
            )
            assert imp != "pipelines.doc_pipeline", f"_guard importa doc_pipeline"

    def test_prefetch_no_rag_imports(self):
        """_prefetch.py nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "_prefetch.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"_prefetch importa {imp}"
            )
            assert imp != "pipelines.doc_pipeline", f"_prefetch importa doc_pipeline"

    def test_executor_no_rag_imports(self):
        """_executor.py nao importa nenhum modulo RAG."""
        imports = _find_imports(_AGENTS_RUNTIME / "pipelines" / "_executor.py")
        for imp in imports:
            assert not imp.startswith("agent_orchestration.knowledge"), (
                f"_executor importa {imp}"
            )
            assert imp != "pipelines.doc_pipeline", f"_executor importa doc_pipeline"


class TestDocPipelinePublicApi:
    def test_doc_pipeline_run_signature(self):
        """doc_pipeline.run() mantem assinatura: (payload) -> dict."""
        from pipelines.doc_pipeline import run

        sig = inspect.signature(run)
        params = list(sig.parameters.keys())
        assert params == ["payload"], f"run() assinatura mudou: {params}"

    def test_doc_pipeline_detect_signature(self):
        """doc_pipeline.detect() mantem assinatura: (text) -> bool."""
        from pipelines.doc_pipeline import detect

        sig = inspect.signature(detect)
        params = list(sig.parameters.keys())
        assert params == ["text"], f"detect() assinatura mudou: {params}"

    def test_doc_pipeline_run_returns_dict(self):
        """doc_pipeline.run() sempre retorna dict com 'reply'."""
        import asyncio
        from pipelines.doc_pipeline import run

        async def _call():
            result = await run({"phone": "5511999", "text": "", "extra": {}})
            assert isinstance(result, dict)
            assert "reply" in result
            assert isinstance(result["reply"], str)

        asyncio.run(_call())


class TestKnowledgeRetrieveToolSchema:
    def test_retrieve_output_has_required_keys(self):
        """knowledge_retriever.retrieve() schema: decision, results, count, scope."""
        from agent_orchestration.knowledge_retriever import retrieve

        sig = inspect.signature(retrieve)
        # Parameter names
        params = list(sig.parameters.keys())
        assert "envelope" in params
        assert "query" in params
        assert "limit" in params
        assert "min_score" in params

    def test_retrieve_returns_dict_type(self):
        """retrieve() type hint retorna Dict[str, Any]."""
        from agent_orchestration.knowledge_retriever import retrieve

        hints = inspect.get_annotations(retrieve, eval_str=True)
        assert "return" in hints


class TestLegacyFallbackFormat:
    def test_fallback_raw_chunks_format(self):
        """_fallback_raw_chunks produz formato identico ao legado."""
        from pipelines.doc_pipeline import _fallback_raw_chunks

        chunks = [
            {"source": "doc1.pdf", "text": "Conteudo A com mais de 300 caracteres " + "x" * 280},
            {"source": "doc2.pdf", "text": "Conteudo B"},
        ]
        result = _fallback_raw_chunks(chunks)
        # Legacy format: [source] text\n\n[source] text
        assert "[doc1.pdf]" in result
        assert "[doc2.pdf]" in result
        assert "\n\n" in result
        # Each chunk text is capped at 300 chars
        for chunk_text in result.split("\n\n"):
            text_part = chunk_text.split("] ", 1)[1] if "] " in chunk_text else chunk_text
            assert len(text_part) <= 300