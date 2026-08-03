"""Testes do jennifer_pipeline — fallback conversacional."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch




class TestJenniferDetect:

    def test_detect_always_true(self):
        from pipelines.jennifer_pipeline import detect
        assert detect("qualquer coisa") is True

    def test_detect_empty_string(self):
        from pipelines.jennifer_pipeline import detect
        assert detect("") is True

    def test_detect_calendar_keyword(self):
        """Mesmo com keyword de calendar, detect = True (so e chamado como fallback)."""
        from pipelines.jennifer_pipeline import detect
        assert detect("agenda") is True


class TestJenniferRun:

    def _payload(self, text="oi tudo bem?"):
        return {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": text,
            "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    @pytest.mark.asyncio
    async def test_run_returns_conversational_response(self):
        from pipelines.jennifer_pipeline import run

        with patch(
            "pipelines._executor.run_agent",
            new_callable=AsyncMock,
            return_value={
                "reply": "Oi Vinicius! Tudo bem? Como posso ajudar?",
                "delay_ms": 500,
                "presence": "composing",
                "metadata": {"agent_id": "jennifier"},
            },
        ):
            result = await run(self._payload())
        assert "oi" in result["reply"].lower() or "bem" in result["reply"].lower()
        assert result["metadata"]["agent_id"] == "jennifier"

    @pytest.mark.asyncio
    async def test_run_no_google_tools_in_response(self):
        """Jennifer nunca deve chamar tools do Google."""
        from pipelines.jennifer_pipeline import run

        with patch(
            "pipelines._executor.run_agent",
            new_callable=AsyncMock,
            return_value={
                "reply": "Sou a Jennifer, assistente conversacional.",
                "delay_ms": 500,
                "presence": "composing",
                "metadata": {"agent_id": "jennifier"},
            },
        ):
            result = await run(self._payload())
        reply = result["reply"].lower()
        assert "agenda" not in reply
        assert "drive" not in reply
        assert "email" not in reply
        assert "calendar" not in reply

    @pytest.mark.asyncio
    async def test_run_with_greeting(self):
        from pipelines.jennifer_pipeline import run

        with patch(
            "pipelines._executor.run_agent",
            new_callable=AsyncMock,
            return_value={
                "reply": "Ola! Como vai voce?",
                "delay_ms": 300,
                "presence": "composing",
                "metadata": {"agent_id": "jennifier"},
            },
        ):
            result = await run(self._payload("ola"))
        assert result["reply"]

    @pytest.mark.asyncio
    async def test_run_error_returns_graceful_error(self):
        from pipelines.jennifer_pipeline import run

        with patch(
            "pipelines._executor.run_agent",
            new_callable=AsyncMock,
            return_value={
                "reply": "Desculpe, ocorreu um erro.",
                "delay_ms": 0,
                "presence": "composing",
                "metadata": {"agent_id": "jennifier", "error": "timeout"},
            },
        ):
            result = await run(self._payload())
        assert "erro" in result["reply"].lower() or "desculpe" in result["reply"].lower()
