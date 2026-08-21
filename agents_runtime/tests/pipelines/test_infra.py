"""Testes de isolamento entre pipelines e modulos de infra.

Garante que:
1. Falha em um modulo de infra nao derruba pipelines que nao o usam.
2. Cada pipeline importa apenas os modulos que precisa.
3. Fallbacks funcionam corretamente em cada modulo.
"""
from __future__ import annotations

import os
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "")


class TestModuleIsolation:

    @pytest.mark.asyncio
    async def test_guard_module_fallback_deny(self):
        """_guard.check_google_access retorna deny seguro em caso de erro."""
        from pipelines._guard import check_google_access

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            side_effect=Exception("guard crash"),
        ):
            result = await check_google_access("jennifer", "5511", "calendar")
        assert result["verdict"] == "deny"
        assert result["reason"] == "guard_error"

    @pytest.mark.asyncio
    async def test_prefetch_timeout_does_not_crash(self):
        """_prefetch nunca deve lancar excecao."""
        from pipelines._prefetch import prefetch_for_agent

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(10)
            return "data"

        with patch("orchestrator._prefetch_calendar", new=slow_fetch):
            result = await prefetch_for_agent("5511", "jennifer", "calendar")
        assert result is None

    @pytest.mark.asyncio
    async def test_ack_error_does_not_crash(self):
        """_ack nunca deve lancar excecao."""
        from pipelines._ack import send_ack

        with patch("core.evolution_client.send_presence", side_effect=Exception("fail")):
            with patch("core.evolution_client.send_text", side_effect=Exception("fail")):
                with patch("core.delay_calculator.calculate_delay_ms", return_value=1500):
                    result = await send_ack("jennifer", "5511", "calendar", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_executor_missing_agent_returns_error(self):
        """_executor retorna erro amigavel quando agente nao existe."""
        from pipelines._executor import run_agent

        with patch("agent_loader.get_agent", return_value=None):
            with patch("agent_loader._load_all", side_effect=None):
                result = await run_agent(
                    "missing-agent", "oi",
                    {"instance": "jennifer", "phone": "5511"}, {},
                )
        assert "indispon" in result["reply"].lower()

    @pytest.mark.asyncio
    async def test_executor_crash_returns_graceful_error(self):
        """_executor retorna erro amigavel em caso de excecao."""
        from pipelines._executor import run_agent

        with patch("agent_loader.get_agent", side_effect=Exception("Firestore down")):
            result = await run_agent(
                "any-agent", "oi",
                {"instance": "jennifer", "phone": "5511"}, {},
            )
        assert "erro" in result["reply"].lower()


class TestGuardModule:
    @pytest.mark.asyncio
    async def test_check_google_access_allow(self):
        from pipelines._guard import check_google_access

        mock_decision = MagicMock()
        mock_decision.verdict = "allow"
        mock_decision.reason = "owner"
        mock_decision.oauth_link = None

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            return_value=mock_decision,
        ):
            result = await check_google_access("jennifer", "5511", "calendar")
        assert result["verdict"] == "allow"

    @pytest.mark.asyncio
    async def test_check_google_access_request_oauth(self):
        from pipelines._guard import check_google_access

        mock_decision = MagicMock()
        mock_decision.verdict = "request_oauth"
        mock_decision.reason = "no_token"
        mock_decision.oauth_link = "https://auth.example.com"

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            return_value=mock_decision,
        ):
            result = await check_google_access("jennifer", "5511", "email")
        assert result["verdict"] == "request_oauth"
        assert result["oauth_link"] == "https://auth.example.com"

    def test_blocked_response_deny(self):
        from pipelines._guard import blocked_response

        guard = {"verdict": "deny", "reason": "not_owner", "capability": "calendar"}
        result = blocked_response(guard)
        assert result["metadata"]["blocked"] is True
        assert "administrador" in result["reply"].lower()

    def test_blocked_response_oauth(self):
        from pipelines._guard import blocked_response

        guard = {
            "verdict": "request_oauth",
            "reason": "no_token",
            "capability": "gmail.search_messages",
            "oauth_link": "https://auth.example.com",
        }
        result = blocked_response(guard)
        assert result["metadata"]["blocked"] is True
        assert "conecte" in result["reply"].lower()
        assert "auth.example.com" in result["reply"]
        assert "e-mails" in result["reply"]


class TestPrefetchModule:
    @pytest.mark.asyncio
    async def test_prefetch_calendar_returns_data(self):
        from pipelines._prefetch import prefetch_for_agent

        with patch(
            "orchestrator._prefetch_calendar",
            new_callable=AsyncMock,
            return_value='[{"id":"1","summary":"Reuniao"}]',
        ):
            result = await prefetch_for_agent("5511", "jennifer", "calendar")
        assert result is not None
        assert "Reuniao" in result["text"]

    @pytest.mark.asyncio
    async def test_prefetch_email_returns_data(self):
        from pipelines._prefetch import prefetch_for_agent

        with patch(
            "orchestrator._prefetch_email",
            new_callable=AsyncMock,
            return_value='[{"id":"1","subject":"Hello"}]',
        ):
            result = await prefetch_for_agent("5511", "jennifer", "email")
        assert result is not None
        assert "Hello" in result["text"]

    @pytest.mark.asyncio
    async def test_prefetch_drive_returns_data(self):
        from pipelines._prefetch import prefetch_for_agent

        with patch(
            "orchestrator._prefetch_drive_multi",
            new_callable=AsyncMock,
            return_value='[{"id":"1","name":"ata.pdf"}]',
        ):
            result = await prefetch_for_agent("5511", "jennifer", "drive", text="ata")
        assert result is not None
        assert "ata.pdf" in result["text"]

    @pytest.mark.asyncio
    async def test_prefetch_unknown_type_returns_none(self):
        from pipelines._prefetch import prefetch_for_agent

        result = await prefetch_for_agent("5511", "jennifer", "unknown")
        assert result is None


class TestAckModule:
    @pytest.mark.asyncio
    async def test_send_ack_calendar_dispatches(self):
        from pipelines._ack import send_ack, _ACKED_PHONES
        _ACKED_PHONES.clear()

        with patch(
            "core.evolution_client.send_presence", new_callable=AsyncMock
        ) as mock_presence:
            with patch(
                "core.evolution_client.send_text", new_callable=AsyncMock
            ) as mock_text:
                with patch(
                    "core.delay_calculator.calculate_delay_ms", return_value=1500
                ):
                    await send_ack("jennifer", "5511", "calendar", {})
        assert mock_presence.called
        assert mock_text.called

    @pytest.mark.asyncio
    async def test_send_ack_unknown_type_defaults(self):
        from pipelines._ack import send_ack

        with patch(
            "core.evolution_client.send_presence", new_callable=AsyncMock
        ), patch(
            "core.evolution_client.send_text", new_callable=AsyncMock
        ), patch(
            "core.delay_calculator.calculate_delay_ms", return_value=1500
        ):
            result = await send_ack("jennifer", "5511", "unknown", {})
        assert result is None


class TestExecutorModule:
    @pytest.mark.asyncio
    async def test_run_agent_with_valid_agent(self):
        from pipelines._executor import run_agent

        mock_agent = {
            "id": "test-agent", "name": "Test", "enabled": True,
            "model": "deepseek-v4-flash", "system_prompt": "You are a test agent.",
            "tools": [], "skills": [],
        }

        with patch("agent_loader.get_agent", return_value=mock_agent):
            with patch(
                "orchestrator._execute_agent",
                new_callable=AsyncMock,
                return_value={
                    "reply": "Ola!", "delay_ms": 500,
                    "presence": "composing", "metadata": {"agent_id": "test-agent"},
                },
            ):
                result = await run_agent(
                    "test-agent", "oi",
                    {"instance": "jennifer", "phone": "5511"}, {},
                )
        assert result["reply"] == "Ola!"

    @pytest.mark.asyncio
    async def test_run_agent_not_found_returns_error(self):
        from pipelines._executor import run_agent

        with patch("agent_loader.get_agent", return_value=None):
            with patch("agent_loader._load_all", side_effect=None):
                result = await run_agent(
                    "missing-agent", "oi",
                    {"instance": "jennifer", "phone": "5511"}, {},
                )
        assert "indispon" in result["reply"].lower()
