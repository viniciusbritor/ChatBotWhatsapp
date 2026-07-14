"""Tests for ata_worker module."""
import pytest
from unittest.mock import patch, AsyncMock


class TestExtractOrganizerEmail:
    @pytest.mark.asyncio
    async def test_first_attendee(self):
        from ata_worker.main import extract_organizer_email
        event = {"attendees": ["joao@example.com", "maria@example.com"]}
        result = await extract_organizer_email(event)
        assert result == "joao@example.com"

    @pytest.mark.asyncio
    async def test_no_attendees(self):
        from ata_worker.main import extract_organizer_email
        result = await extract_organizer_email({"attendees": []})
        assert result is None


class TestAlreadyProcessed:
    def test_no_firestore(self):
        from ata_worker import main as aw_main
        with patch.object(aw_main, "_get_firestore", return_value=None):
            assert aw_main._already_processed("evt1") is False


class TestMarkProcessed:
    def test_no_firestore(self):
        from ata_worker import main as aw_main
        with patch.object(aw_main, "_get_firestore", return_value=None):
            aw_main._mark_processed("evt1", "completed")
            assert True


class TestMain:
    @pytest.mark.asyncio
    async def test_main_no_events(self):
        from ata_worker import main as aw_main
        with patch.object(aw_main, "find_recent_meetings", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = []
            result = await aw_main.main()
        assert result["processed"] == 0