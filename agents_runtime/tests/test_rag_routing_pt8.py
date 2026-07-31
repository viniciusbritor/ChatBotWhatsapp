"""Smoke test para o patch de routing RAG vs Drive (PT8 F3).

Cobre:
1. _keyword_classify tie-breaker: queries com "base de conhecimento" => is_drive=False
2. is_rag_query: "quais documentos voce tem" => True
3. is_rag_query: "liste os arquivos do drive" => False (continua sendo Drive)
4. Orquestrador: is_rag=True vem antes de is_drive no _resolve_agent_for_intent
5. Jennifer system prompt tem a regra PT8 (RAG vs Drive)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("GCP_PROJECT", "test-project")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "")
os.environ.setdefault("AGENTS_RUNTIME_SA_TOKEN_SECRET", "test-sa")

import pytest


class TestKeywordClassifyTieBreaker:
    """Garante que _keyword_classify prioriza RAG sobre Drive quando
    query contem 'base de conhecimento' / 'memorizou' / etc."""

    def test_base_de_conhecimento_disables_drive(self):
        from agent_orchestration.graph import _keyword_classify

        result = _keyword_classify("quais documentos voce tem na sua base de conhecimento")
        assert result["is_drive"] is False
        assert result["is_calendar"] is False
        assert result["is_email"] is False
        assert result.get("is_rag") is True

    def test_memorizou_disables_drive(self):
        from agent_orchestration.graph import _keyword_classify

        result = _keyword_classify("voce memorizou alguma coisa?")
        assert result["is_drive"] is False
        assert result.get("is_rag") is True

    def test_drive_keyword_without_rag_still_drive(self):
        from agent_orchestration.graph import _keyword_classify

        result = _keyword_classify("liste os arquivos do drive")
        assert result["is_drive"] is True
        assert result.get("is_rag") is not True

    def test_calendar_keyword_still_calendar(self):
        from agent_orchestration.graph import _keyword_classify

        result = _keyword_classify("tenho reuniao amanha as 10h?")
        assert result["is_calendar"] is True
        assert result.get("is_rag") is not True


class TestIsRagQueryKeywords:
    """Garante que RAG_KEYWORDS captura queries genericas sobre
    'documentos' (PT8 fix)."""

    def test_quais_documentos_voce_tem(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("quais documentos voce tem na sua base de conhecimento") is True

    def test_lista_documentos(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("lista os documentos memorizados") is True

    def test_ola_nao_rag(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("ola tudo bem") is False

    def test_drive_nao_rag(self):
        from agent_orchestration.knowledge_retriever import _looks_like_rag_query

        assert _looks_like_rag_query("liste os arquivos do drive") is False


class TestRoutePriority:
    """Garante que _resolve_agent_for_intent prioriza is_rag > is_drive."""

    def _intent(self, **overrides):
        base = {
            "is_gross": False,
            "is_assault_related": False,
            "is_correction": False,
            "is_intimacy": False,
            "is_runtime_status": False,
        }
        base.update(overrides)
        return base

    def test_rag_takes_priority_over_drive(self):
        from orchestrator import _resolve_agent_for_intent

        intent = self._intent(is_rag=True, is_drive=True, is_email=False, is_calendar=False)
        assert _resolve_agent_for_intent(intent, instance="jennifer") == "agent-knowledge-retriever"

    def test_only_drive(self):
        from orchestrator import _resolve_agent_for_intent

        intent = self._intent(is_rag=False, is_drive=True, is_email=False, is_calendar=False)
        assert _resolve_agent_for_intent(intent, instance="jennifer") == "manager-drive"

    def test_only_rag(self):
        from orchestrator import _resolve_agent_for_intent

        intent = self._intent(is_rag=True, is_drive=False, is_email=False, is_calendar=False)
        assert _resolve_agent_for_intent(intent, instance="jennifer") == "agent-knowledge-retriever"


class TestJenniferSystemPrompt:
    """Garante que o system prompt do jennifier tem a regra PT8."""

    def test_prompt_has_rag_vs_drive_distinction(self):
        path = Path(__file__).resolve().parents[1] / "data" / "agents" / "jennifier.yaml"
        yaml = path.read_text(encoding="utf-8")
        assert "RAG vs Google Drive" in yaml
        assert "base de conhecimento" in yaml
        assert "NUNCA" in yaml or "Nunca" in yaml
        assert "folder_permissions" in yaml or "permissao de pasta" in yaml
