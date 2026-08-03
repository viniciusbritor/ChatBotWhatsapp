"""Testes do email_pipeline — keyword-only, zero LLM."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch




class TestEmailDetect:

    def test_priority_meus_emails(self):
        from pipelines.email_pipeline import detect
        assert detect("meus emails") is True

    def test_priority_caixa_de_entrada(self):
        from pipelines.email_pipeline import detect
        assert detect("caixa de entrada") is True

    def test_priority_ultimos_emails(self):
        from pipelines.email_pipeline import detect
        assert detect("ultimos e-mails") is True

    def test_keyword_gmail(self):
        from pipelines.email_pipeline import detect
        assert detect("gmail") is True

    def test_keyword_inbox(self):
        from pipelines.email_pipeline import detect
        assert detect("inbox") is True

    def test_keyword_ler_email(self):
        from pipelines.email_pipeline import detect
        assert detect("ler email do cliente") is True

    def test_exclusion_agenda(self):
        from pipelines.email_pipeline import detect
        assert detect("email da agenda") is False

    def test_exclusion_drive(self):
        from pipelines.email_pipeline import detect
        assert detect("email do drive") is False

    def test_negative_calendar(self):
        from pipelines.email_pipeline import detect
        assert detect("minha agenda") is False

    def test_negative_drive(self):
        from pipelines.email_pipeline import detect
        assert detect("liste os arquivos do drive") is False

    def test_negative_conversa(self):
        from pipelines.email_pipeline import detect
        assert detect("oi tudo bem") is False


class TestEmailRun:

    def _payload(self):
        return {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": "meus ultimos emails",
            "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    @pytest.mark.asyncio
    async def test_run_guard_deny(self):
        from pipelines.email_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "deny"},
        ):
            result = await run(self._payload())
        assert result["metadata"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_run_success_with_prefetch(self):
        from pipelines.email_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    new_callable=AsyncMock,
                    return_value='[{"id":"1","subject":"Hello"}]',
                ):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Voce tem 3 emails nao lidos.",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-email"},
                        },
                    ):
                        result = await run(self._payload())
        assert "email" in result["reply"].lower()
        assert "drive" not in result["reply"].lower()
        assert "agenda" not in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_isolamento_nunca_retorna_calendar(self):
        from pipelines.email_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch("pipelines._prefetch.prefetch_for_agent", new_callable=AsyncMock, return_value=None):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Seus emails...",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-email"},
                        },
                    ):
                        result = await run(self._payload())
        reply = result["reply"].lower()
        assert "agenda" not in reply
        assert "drive" not in reply
        assert "documento" not in reply
