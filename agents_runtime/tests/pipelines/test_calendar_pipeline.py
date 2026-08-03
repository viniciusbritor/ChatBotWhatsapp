"""Testes do calendar_pipeline — keyword-only, zero LLM."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock




class TestCalendarDetect:
    """detect() — priority patterns + keyword matching."""

    def test_priority_agenda_hoje(self):
        from pipelines.calendar_pipeline import detect
        assert detect("agenda hoje") is True

    def test_priority_criar_evento(self):
        from pipelines.calendar_pipeline import detect
        assert detect("criar evento amanha as 15h") is True

    def test_priority_compromissos_hoje(self):
        from pipelines.calendar_pipeline import detect
        assert detect("meus compromissos hoje") is True

    def test_priority_minha_agenda(self):
        from pipelines.calendar_pipeline import detect
        assert detect("minha agenda da semana") is True

    def test_keyword_reuniao(self):
        from pipelines.calendar_pipeline import detect
        assert detect("tenho reuniao amanha") is True

    def test_keyword_evento(self):
        from pipelines.calendar_pipeline import detect
        assert detect("eventos da proxima semana") is True

    def test_keyword_agenda(self):
        from pipelines.calendar_pipeline import detect
        assert detect("qual minha agenda?") is True

    def test_exclusion_documento(self):
        """Exclusao: keyword 'agenda' com 'documento' → False."""
        from pipelines.calendar_pipeline import detect
        assert detect("agenda de documentos") is False

    def test_exclusion_drive(self):
        from pipelines.calendar_pipeline import detect
        assert detect("agenda no drive") is False

    def test_exclusion_email(self):
        from pipelines.calendar_pipeline import detect
        assert detect("agenda de emails") is False

    def test_negative_drive(self):
        from pipelines.calendar_pipeline import detect
        assert detect("liste os arquivos do drive") is False

    def test_negative_email(self):
        from pipelines.calendar_pipeline import detect
        assert detect("meus emails") is False

    def test_negative_conversa(self):
        from pipelines.calendar_pipeline import detect
        assert detect("oi tudo bem") is False

    def test_negative_vazio(self):
        from pipelines.calendar_pipeline import detect
        assert detect("") is False


class TestCalendarRun:
    """run() — guard → ack → prefetch → agent."""

    def _payload(self, text="qual minha agenda amanha?"):
        return {
            "instance": "jennifer",
            "phone": "+5511966830020",
            "text": text,
            "sender_name": "Vinicius",
            "extra": {"remote_jid": "5511966830020@s.whatsapp.net"},
        }

    @pytest.mark.asyncio
    async def test_run_guard_deny_returns_blocked(self):
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "deny", "reason": "not_owner"},
        ):
            result = await run(self._payload())
        assert result["metadata"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_run_guard_request_oauth(self):
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={
                "verdict": "request_oauth",
                "reason": "no_token",
                "oauth_link": "https://auth.example.com",
            },
        ):
            result = await run(self._payload())
        assert result["metadata"]["blocked"] is True
        assert "autorize" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_run_success_with_prefetch(self):
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow", "reason": "owner"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    new_callable=AsyncMock,
                    return_value='[{"id":"1","summary":"Reuniao"}]',
                ):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Voce tem reuniao amanha as 15h.",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-calendar"},
                        },
                    ):
                        result = await run(self._payload())
        assert "reuniao" in result["reply"].lower()
        assert "drive" not in result["reply"].lower()
        assert "email" not in result["reply"].lower()
        assert "documento" not in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_run_prefetch_failure_still_executes(self):
        """Prefetch quebrado não derruba o pipeline."""
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    side_effect=Exception("prefetch down"),
                ):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Sua agenda esta vazia.",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-calendar"},
                        },
                    ):
                        result = await run(self._payload())
        assert "agenda" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_run_ack_failure_still_executes(self):
        """Ack quebrado não derruba o pipeline."""
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch(
                "pipelines._ack.send_ack",
                side_effect=Exception("ack down"),
            ):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Ok.",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-calendar"},
                        },
                    ):
                        result = await run(self._payload())
        assert result["reply"] == "Ok."

    @pytest.mark.asyncio
    async def test_isolamento_nunca_retorna_drive(self):
        """Garantia: resposta de calendar nunca contem termos de drive/email/doc."""
        from pipelines.calendar_pipeline import run

        with patch(
            "pipelines._guard.check_google_access",
            new_callable=AsyncMock,
            return_value={"verdict": "allow"},
        ):
            with patch("pipelines._ack.send_ack", new_callable=AsyncMock):
                with patch(
                    "pipelines._prefetch.prefetch_for_agent",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    with patch(
                        "pipelines._executor.run_agent",
                        new_callable=AsyncMock,
                        return_value={
                            "reply": "Voce tem uma reuniao as 15h no dia 03/08.",
                            "delay_ms": 500,
                            "presence": "composing",
                            "metadata": {"agent_id": "manager-calendar"},
                        },
                    ):
                        result = await run(self._payload())
        reply = result["reply"].lower()
        assert "drive" not in reply
        assert "documento" not in reply
        assert "email" not in reply
        assert "rag" not in reply
        assert "vector" not in reply
