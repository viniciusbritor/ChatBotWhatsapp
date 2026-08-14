"""E2E smoke tests ÔÇö fluxo completo detect() ÔåÆ run() ÔåÆ response.

Validam a integra├º├úo real entre orquestrador e pipelines.
Mockam apenas depend├¬ncias externas: Firestore, DeepSeek API, Evolution API, agent execution.
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
# Stubs compartilhados para mock de depend├¬ncias externas
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
        "reply": "Amanh├ú voc├¬ tem Reuni├úo ├ás 15h na sala 3.",
        "delay_ms": 500,
        "presence": "composing",
        "metadata": {"agent_id": "manager-calendar"},
    })


def _mock_agent_email_response():
    return AsyncMock(return_value={
        "reply": "Voc├¬ tem 3 emails n├úo lidos. O mais recente ├® 'Aprova├º├úo budget Q3'.",
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


class TestE2EEmail:
    """Email pipeline: detect ÔåÆ guard ÔåÆ ack ÔåÆ prefetch ÔåÆ agent ÔåÆ response."""

    @pytest.mark.asyncio
    async def test_e2e_email_full_flow(self):
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_email()):
                    with patch("pipelines._executor.run_agent", _mock_agent_email_response()):
                        result = await orchestrate(_base_payload("meus ultimos emails"))

        assert result["reply"], "Resposta n├úo pode ser vazia"
        assert "email" in result["reply"].lower() or "Aprova├º├úo" in result["reply"]
        assert result["metadata"]["agent_id"] == "manager-email"

    @pytest.mark.asyncio
    async def test_e2e_email_never_mentions_calendar_or_drive(self):
        """Garantia: resposta de email NUNCA referencia calendar, drive, doc."""
        from orchestrator import orchestrate

        with patch("pipelines._guard.check_google_access", _mock_guard_allow()):
            with patch("pipelines._ack.send_ack", AsyncMock()):
                with patch("pipelines._prefetch.prefetch_for_agent", _mock_prefetch_email()):
                    with patch("pipelines._executor.run_agent", _mock_agent_email_response()):
                        with patch("orchestrator._user_has_any_connection", new_callable=AsyncMock, return_value=True):
                            result = await orchestrate(_base_payload("meus emails"))

        reply = result["reply"].lower()
        assert "agenda" not in reply, "Email mencionou Agenda!"
        assert "calendario" not in reply, "Email mencionou Calendario!"
        assert "drive" not in reply, "Email mencionou Drive!"
        assert "documento" not in reply, "Email mencionou Documento!"


class TestE2EJennifer:
    """Jennifer pipeline: fallback conversacional."""

    @pytest.mark.asyncio
    async def test_e2e_jennifer_fallback_greeting(self):
        from orchestrator import orchestrate

        with patch("pipelines.jennifer_pipeline.run", _mock_agent_jennifer_response()):
            result = await orchestrate(_base_payload("oi, tudo bem?"))

        assert result["reply"], "Resposta n├úo pode ser vazia"
        assert "oi" in result["reply"].lower() or "bem" in result["reply"].lower()
        assert result["metadata"]["agent_id"] == "jennifier"


class TestE2ETier1Blocking:
    """Tier 1: security handlers bloqueiam antes de Tier 2."""

    @pytest.mark.asyncio
    async def test_e2e_morality_blocks_pipeline(self):
        """Profanidade no Tier 1 ÔåÆ bloqueia, nunca chama pipeline."""
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
