"""Tests for proactive_worker module."""
import pytest
from unittest.mock import patch, AsyncMock


class TestGenerateEventMessage:
    def test_1h(self):
        from proactive_worker.main import generate_event_message
        msg = generate_event_message({"summary": "Reuniao"}, "1h")
        assert "Reuniao" in msg

    def test_3h(self):
        from proactive_worker.main import generate_event_message
        msg = generate_event_message({"summary": "Daily"}, "3h")
        assert "3h" in msg

    def test_24h(self):
        from proactive_worker.main import generate_event_message
        msg = generate_event_message({"summary": "Sprint"}, "24h")
        assert "Amanha" in msg or "amanha" in msg.lower()


class TestScanUpcomingEvents:
    @pytest.mark.asyncio
    async def test_scan_returns_candidates(self):
        from proactive_worker import main as pw_main
        with patch.object(pw_main, "list_events", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "events": [
                    {"id": "evt1", "summary": "Reuniao"},
                    {"id": "evt2", "summary": "Daily"},
                ],
                "count": 2,
            }
            result = await pw_main.scan_upcoming_events("5511966830020")
        assert len(result) >= 2
        assert result[0]["phone"] == "5511966830020"


class TestSendProactiveMessage:
    @pytest.mark.asyncio
    async def test_dry_run(self):
        from proactive_worker import main as pw_main
        with patch.object(pw_main, "is_dry_run", return_value=True):
            result = await pw_main.send_proactive_message("+5511966830020", "test", "test_trigger")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_config(self):
        """Sem Evolution API configurada -> fail-safe False (substituiu
        test antigo que dependia de WHATSAPP_AGENTE_URL removido em F6)."""
        from proactive_worker import main as pw_main

        with patch.object(pw_main, "is_dry_run", return_value=False), \
             patch("core.evolution_client.send_text", AsyncMock(side_effect=Exception("evo_unavailable"))):
            result = await pw_main.send_proactive_message("+5511966830020", "test", "test_trigger")
        assert result is False


class TestProcessCandidate:
    @pytest.mark.asyncio
    async def test_prohibited_template(self):
        from proactive_worker import main as pw_main
        with patch.object(pw_main, "is_prohibited_template", return_value=True):
            result = await pw_main.process_candidate({
                "trigger": "calendar_1h",
                "event": {"summary": "Oi, tudo bem?", "attendees": ["+5511966830020"]},
                "relevance_score": 0.9,
            })
        assert result is False

    @pytest.mark.asyncio
    async def test_no_event(self):
        from proactive_worker import main as pw_main
        result = await pw_main.process_candidate({"trigger": "topic", "relevance_score": 0.9})
        assert result is False
