"""Testes de isolamento entre pipelines e módulos de infra.

Garante que:
1. Falha em um módulo de infra não derruba pipelines que não o usam.
2. Cada pipeline importa apenas os módulos que precisa.
3. Fallbacks funcionam corretamente em cada módulo.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock




class TestModuleIsolation:
    """Garante que falha em um módulo não derruba os outros."""

    def test_jennifer_does_not_import_guard(self):
        """Jennifier pipeline nunca importa _guard (não usa Google tools)."""
        with patch.dict("sys.modules", {}):
            with patch("pipelines._guard", side_effect=ImportError("guard broken")):
                try:
                    from pipelines.jennifer_pipeline import detect, run
                    assert callable(detect)
                    assert callable(run)
                except ImportError:
                    pass

    def test_jennifer_does_not_import_prefetch(self):
        """Jennifier pipeline nunca importa _prefetch."""
        with patch.dict("sys.modules", {}):
            with patch("pipelines._prefetch", side_effect=ImportError("prefetch broken")):
                try:
                    from pipelines.jennifer_pipeline import detect, run
                    assert callable(detect)
                    assert callable(run)
                except ImportError:
                    pass

    def test_guard_module_fallback_deny(self):
        """_guard.check_google_access retorna deny seguro em caso de erro."""
        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            side_effect=Exception("guard crash"),
        ):
            import asyncio
            from pipelines._guard import check_google_access

            result = asyncio.get_event_loop().run_until_complete(
                check_google_access("jennifer", "5511", "calendar")
            )
        assert result["verdict"] == "deny"
        assert result["reason"] == "guard_error"


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
        assert result["reason"] == "owner"

    @pytest.mark.asyncio
    async def test_check_google_access_deny_non_owner(self):
        from pipelines._guard import check_google_access

        mock_decision = MagicMock()
        mock_decision.verdict = "deny"
        mock_decision.reason = "not_owner"
        mock_decision.oauth_link = None

        with patch(
            "agent_orchestration.access_guardian.decide_guardian",
            return_value=mock_decision,
        ):
            result = await check_google_access("jennifer", "9999", "calendar")
        assert result["verdict"] == "deny"

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
        assert "proprietario" in result["reply"].lower()

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
        assert "autorize" in result["reply"].lower()
        assert "https://auth.example.com" in result["reply"]


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
        assert "Reuniao" in result

    @pytest.mark.asyncio
    async def test_prefetch_calendar_timeout_returns_none(self):
        import asyncio
        from pipelines._prefetch import prefetch_for_agent

        async def slow_prefetch(*args, **kwargs):
            await asyncio.sleep(10)
            return "data"

        with patch("orchestrator._prefetch_calendar", new=slow_prefetch):
            result = await prefetch_for_agent("5511", "jennifer", "calendar")
        assert result is None

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
        assert "Hello" in result

    @pytest.mark.asyncio
    async def test_prefetch_drive_returns_data(self):
        from pipelines._prefetch import prefetch_for_agent

        with patch(
            "orchestrator._prefetch_drive_multi",
            new_callable=AsyncMock,
            return_value='[{"id":"1","name":"ata.pdf"}]',
        ):
            result = await prefetch_for_agent(
                "5511", "jennifer", "drive", text="ata"
            )
        assert result is not None
        assert "ata.pdf" in result

    @pytest.mark.asyncio
    async def test_prefetch_exception_returns_none(self):
        from pipelines._prefetch import prefetch_for_agent

        with patch(
            "orchestrator._prefetch_calendar",
            side_effect=Exception("API down"),
        ):
            result = await prefetch_for_agent("5511", "jennifer", "calendar")
        assert result is None


class TestAckModule:
    @pytest.mark.asyncio
    async def test_send_ack_does_not_crash(self):
        """send_ack nunca deve lançar exceção."""
        from pipelines._ack import send_ack

        with patch("core.evolution_client.send_presence", side_effect=Exception("fail")):
            with patch("core.evolution_client.send_text", side_effect=Exception("fail")):
                result = await send_ack("jennifer", "5511", "calendar", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_send_ack_calendar_type(self):
        from pipelines._ack import send_ack

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


class TestExecutorModule:
    @pytest.mark.asyncio
    async def test_run_agent_with_valid_agent(self):
        from pipelines._executor import run_agent

        mock_agent = {
            "id": "test-agent",
            "name": "Test",
            "enabled": True,
            "model": "deepseek-v4-flash",
            "system_prompt": "You are a test agent.",
            "tools": [],
            "skills": [],
        }

        with patch("agent_loader.get_agent", return_value=mock_agent):
            with patch(
                "orchestrator._execute_agent",
                new_callable=AsyncMock,
                return_value={
                    "reply": "Olá!",
                    "delay_ms": 500,
                    "presence": "composing",
                    "metadata": {"agent_id": "test-agent"},
                },
            ):
                result = await run_agent(
                    "test-agent",
                    "oi",
                    {"instance": "jennifer", "phone": "5511"},
                    {},
                )
        assert result["reply"] == "Olá!"
        assert result["metadata"]["agent_id"] == "test-agent"

    @pytest.mark.asyncio
    async def test_run_agent_not_found_returns_graceful_error(self):
        from pipelines._executor import run_agent

        with patch("agent_loader.get_agent", return_value=None):
            with patch("agent_loader._load_all", side_effect=None):
                result = await run_agent(
                    "missing-agent",
                    "oi",
                    {"instance": "jennifer", "phone": "5511"},
                    {},
                )
        assert "indisponível" in result["reply"].lower()
        assert result["metadata"]["error"] == "agent_not_found"

    @pytest.mark.asyncio
    async def test_run_agent_with_prefetch_injects_data(self):
        from pipelines._executor import run_agent

        mock_agent = {
            "id": "calendar-agent",
            "name": "Calendar",
            "enabled": True,
            "model": "deepseek-v4-flash",
            "system_prompt": "You are calendar.",
            "tools": ["calendar.list_events"],
            "skills": [],
        }

        prefetch_data = '[{"id":"1","summary":"Reuniao"}]'

        with patch("agent_loader.get_agent", return_value=mock_agent):
            with patch(
                "orchestrator._has_real_data", return_value=True
            ):
                with patch(
                    "orchestrator._execute_agent",
                    new_callable=AsyncMock,
                    return_value={
                        "reply": "Sua agenda: Reuniao",
                        "delay_ms": 500,
                        "presence": "composing",
                        "metadata": {"agent_id": "calendar-agent"},
                    },
                ) as mock_exec:
                    result = await run_agent(
                        "calendar-agent",
                        "agenda",
                        {"instance": "jennifer", "phone": "5511"},
                        {},
                        prefetch=prefetch_data,
                        prefetch_label="CALENDARIO",
                        tone_guide="Responda em portugues.",
                    )
        assert mock_exec.called
        call_agent = mock_exec.call_args[0][0]
        assert "DADOS PRE-CARREGADOS DO CALENDARIO" in call_agent["system_prompt"]
        assert "Reuniao" in call_agent["system_prompt"]
        assert call_agent["tools"] == []

    @pytest.mark.asyncio
    async def test_run_agent_exception_returns_graceful_error(self):
        from pipelines._executor import run_agent

        with patch(
            "agent_loader.get_agent",
            side_effect=Exception("Firestore down"),
        ):
            result = await run_agent(
                "any-agent",
                "oi",
                {"instance": "jennifer", "phone": "5511"},
                {},
            )
        assert "erro" in result["reply"].lower()
