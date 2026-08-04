"""E2E smoke tests — fluxo completo detect() → run() → response.

Validam a integração real entre orquestrador e pipelines.
Mockam apenas dependências externas: Firestore, DeepSeek API, Evolution API, agent execution.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock




def _base_payload(text="qual minha agenda amanha?"):
    return {
        "instance": "jennifer",
        "phone": "+5511966830020",
        "text": text,
        "sender_name": "Vinicius",
        "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
    }


# ---------------------------------------------------------------------------
# Stubs compartilhados para mock de dependências externas
# ---------------------------------------------------------------------------

def _mock_guard_allow():
    return AsyncMock(return_value={"verdict": "allow", "reason": "owner"})


def _mock_prefetch_calendar():
    return AsyncMock(return_value='[{"id":"1","summary":"Reuniao as 15h","start":"2026-08-03T15:00:00-03:00"}]')


def _mock_prefetch_email():
    return AsyncMock(return_value='[{"id":"1","subject":"Aprovacao budget Q3","from":"cliente@acme.com"}]')


def _mock_prefetch_drive():
    return AsyncMock(return_value='[{"id":"1","name":"ata-2026-07-23.md","modifiedTime":"2026-07-23T09:00:00Z"}]')


def _mock_agent_calendar_response():
    return AsyncMock(return_value={
        "reply": "Amanhã você tem Reunião às 15h na sala 3.",
        "delay_ms": 500,
        "presence": "composing",
        "metadata": {"agent_id": "manager-calendar"},
    })


def _mock_agent_email_response():
    return AsyncMock(return_value={
        "reply": "Você tem 3 emails não lidos. O mais recente é 'Aprovação budget Q3'.",
        "delay_ms": 500,
        "presence": "composing",
        "metadata": {"agent_id": "manager-email"},
    })


def _mock_agent_drive_response():
    return AsyncMock(return_value={
        "reply": "Na pasta Omnichannel/Atas: ata-2026-07-23.md (23/07/2026).",
        "delay_ms": 500,
        "presence": "composing",
        "metadata": {"agent_id": "manager-drive"},
    })


def _mock_agent_jennifer_response():
    return AsyncMock(return_value={
        "reply": "Oi Vinicius! Tudo bem? Como posso ajudar hoje?",
        "delay_ms": 500,
        "presence": "composing",
        "metadata": {"agent_id": "jennifier"},
    })


# ============================================================================
# TESTES
# ============================================================================


class TestE2ECalendar:
    """Calendar pipeline: detect → guard → ack → prefetch → agent → response."""

    @pytest.mark.asyncio
    async def test_e2e_calendar_full_flow(self):
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_calendar()):
                    with patch("pipelines._executor.run_agent", _mock_agent_calendar_response()):
                        result = await orchestrate(_base_payload("qual minha agenda amanha?"))

        assert result["reply"], "Resposta não pode ser vazia"
        assert "reuniao" in result["reply"].lower() or "Reunião" in result["reply"]
        assert "15h" in result["reply"]
        assert result["metadata"]["agent_id"] == "manager-calendar"

    @pytest.mark.asyncio
    async def test_e2e_calendar_never_mentions_drive_or_email(self):
        """Garantia: resposta de calendar NUNCA referencia drive, email, documento."""
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_calendar()):
                    with patch("pipelines._executor.run_agent", _mock_agent_calendar_response()):
                        result = await orchestrate(_base_payload("compromissos de hoje"))

        reply = result["reply"].lower()
        assert "drive" not in reply, "Calendar mencionou Drive!"
        assert "email" not in reply, "Calendar mencionou Email!"
        assert "documento" not in reply, "Calendar mencionou Documento!"
        assert "rag" not in reply, "Calendar mencionou RAG!"
        assert "vector" not in reply, "Calendar mencionou Vector!"
        assert "base de conhecimento" not in reply, "Calendar mencionou base de conhecimento!"

    @pytest.mark.asyncio
    async def test_e2e_calendar_oauth_deny_blocked(self):
        """OAuth deny → bloqueio, não executa agente."""
        from orchestrator import orchestrate

        with patch(
            "pipelines._guard.check_google_access",
            AsyncMock(return_value={
                "verdict": "deny",
                "reason": "not_owner",
                "capability": "calendar.list_events",
            }),
        ):
            result = await orchestrate(_base_payload("minha agenda"))

        assert result["metadata"]["blocked"] is True
        assert result["metadata"]["blocked_reason"] == "not_owner"

    @pytest.mark.asyncio
    async def test_e2e_calendar_prefetch_failure_still_responds(self):
        """Prefetch quebrado → pipeline continua com agente sem cache."""
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    side_effect=Exception("API down"),
                ):
                    with patch("pipelines._executor.run_agent", _mock_agent_calendar_response()):
                        result = await orchestrate(_base_payload("eventos de amanha"))

        assert result["reply"], "Pipeline não pode quebrar por falha no prefetch"


class TestE2EEmail:
    """Email pipeline: detect → guard → ack → prefetch → agent → response."""

    @pytest.mark.asyncio
    async def test_e2e_email_full_flow(self):
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_email()):
                    with patch("pipelines._executor.run_agent", _mock_agent_email_response()):
                        result = await orchestrate(_base_payload("meus ultimos emails"))

        assert result["reply"], "Resposta não pode ser vazia"
        assert "email" in result["reply"].lower() or "Aprovação" in result["reply"]
        assert result["metadata"]["agent_id"] == "manager-email"

    @pytest.mark.asyncio
    async def test_e2e_email_never_mentions_calendar_or_drive(self):
        """Garantia: resposta de email NUNCA referencia calendar, drive, doc."""
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_email()):
                    with patch("pipelines._executor.run_agent", _mock_agent_email_response()):
                        result = await orchestrate(_base_payload("meus emails"))

        reply = result["reply"].lower()
        assert "agenda" not in reply, "Email mencionou Agenda!"
        assert "calendario" not in reply, "Email mencionou Calendario!"
        assert "drive" not in reply, "Email mencionou Drive!"
        assert "documento" not in reply, "Email mencionou Documento!"


class TestE2EDocAndDrive:
    """Doc pipeline: detect → disambiguate → RAG ou Drive."""

    @pytest.mark.asyncio
    async def test_e2e_drive_path_full_flow(self):
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_drive()):
                    with patch("pipelines._executor.run_agent", _mock_agent_drive_response()):
                        with patch("pipelines.doc_pipeline._disambiguate_rag_vs_drive", AsyncMock(return_value="drive")):
                            result = await orchestrate(_base_payload("liste os arquivos do drive"))

        assert result["reply"], "Resposta não pode ser vazia"
        assert result["metadata"]["agent_id"] == "manager-drive"

    @pytest.mark.asyncio
    async def test_e2e_rag_path_with_results(self):
        """RAG path: busca vetorial retorna chunks."""
        from orchestrator import orchestrate

        with patch(
            "agent_orchestration.knowledge_retriever.retrieve",
            AsyncMock(return_value={
                "results": [
                    {"source": "lei-13709.pdf", "text": "Art 1. Esta Lei dispõe sobre o tratamento de dados pessoais...", "score": 0.92, "class": "legal", "group": "leis"},
                ],
                "decision": "rag",
                "scope": "private",
                "count": 1,
                "min_score": 0.7,
            }),
        ):
            with patch("pipelines.doc_pipeline._disambiguate_rag_vs_drive", AsyncMock(return_value="rag")):
                result = await orchestrate(_base_payload("documentos sobre LGPD na base de conhecimento"))

        assert result["reply"], "Resposta não pode ser vazia"
        assert "lei-13709" in result["reply"].lower() or "LGPD" in result["reply"].upper()
        assert "drive.google.com" not in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_e2e_doc_clarify_when_pro_down(self):
        """Pro indisponível → pede clarificação ao usuário."""
        from orchestrator import orchestrate

        with patch("pipelines.doc_pipeline._disambiguate_rag_vs_drive", AsyncMock(return_value="clarify")):
            result = await orchestrate(_base_payload("leia o documento"))

        assert result["metadata"]["needs_clarification"] is True
        assert "banco semantico" in result["reply"].lower()
        assert "drive" in result["reply"].lower()


class TestE2EJennifer:
    """Jennifer pipeline: fallback conversacional."""

    @pytest.mark.asyncio
    async def test_e2e_jennifer_fallback_greeting(self):
        from orchestrator import orchestrate

        with patch("pipelines.jennifer_pipeline.run", _mock_agent_jennifer_response()):
            result = await orchestrate(_base_payload("oi, tudo bem?"))

        assert result["reply"], "Resposta não pode ser vazia"
        assert "oi" in result["reply"].lower() or "bem" in result["reply"].lower()
        assert result["metadata"]["agent_id"] == "jennifier"


class TestE2EMultiIntent:
    """Tier 2: collect-all → parallel if multiple."""

    @pytest.mark.asyncio
    async def test_e2e_calendar_and_email_parallel(self):
        from orchestrator import orchestrate

        async def mock_cal_run(payload):
            return {"reply": "Reunião às 15h.", "delay_ms": 500, "presence": "composing", "metadata": {}}

        async def mock_eml_run(payload):
            return {"reply": "3 emails não lidos.", "delay_ms": 300, "presence": "composing", "metadata": {}}

        with patch("orchestrator._detect_intimacy", return_value=False):
            with patch("orchestrator._detect_runtime_status", return_value=False):
                with patch("orchestrator._detect_correction", return_value=False):
                    with patch("orchestrator._detect_morality", return_value=False):
                        with patch("orchestrator._detect_web", return_value=False):
                            with patch("pipelines.calendar_pipeline.detect", return_value=True):
                                with patch("pipelines.calendar_pipeline.run", new=mock_cal_run):
                                    with patch("pipelines.email_pipeline.detect", return_value=True):
                                        with patch("pipelines.email_pipeline.run", new=mock_eml_run):
                                            with patch("pipelines.doc_pipeline.detect", return_value=False):
                                                with patch("orchestrator._setup_nickname_consent", AsyncMock()):
                                                    result = await orchestrate(
                                                        _base_payload("agenda e tambem meus emails")
                                                    )

        assert "---" in result["reply"], "Respostas paralelas devem ser separadas por ---"
        assert result["metadata"]["multi_intent"] is True
        assert "Reunião" in result["reply"]
        assert "emails" in result["reply"].lower()


class TestE2ETier1Blocking:
    """Tier 1: security handlers bloqueiam antes de Tier 2."""

    @pytest.mark.asyncio
    async def test_e2e_morality_blocks_pipeline(self):
        """Profanidade no Tier 1 → bloqueia, nunca chama pipeline."""
        from orchestrator import orchestrate

        with patch("orchestrator._handle_morality", AsyncMock(return_value={
            "reply": "Mensagem bloqueada.",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "morality-guard", "blocked": True},
        })):
            call_count = 0

            async def track_cal_run(payload):
                nonlocal call_count
                call_count += 1
                return {"reply": "Nao deveria ter chegado aqui", "delay_ms": 0, "presence": "composing", "metadata": {}}

            with patch("pipelines.calendar_pipeline.run", new=track_cal_run):
                result = await orchestrate(_base_payload("sua puta agenda"))

        assert result["metadata"]["blocked"] is True
        assert call_count == 0, "Calendar pipeline foi chamado mesmo com insulto!"
