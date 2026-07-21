"""Tests for google_calendar tool."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_calendar_service():
    """Mock Google Calendar API service."""
    with patch("tools.google_calendar._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


class TestListEvents:
    @pytest.mark.asyncio
    async def test_list_events_success(self, mock_calendar_service):
        from tools.google_calendar import list_events

        mock_calendar_service.events().list().execute.return_value = {
            "items": [
                {"id": "evt1", "summary": "Reuniao Joao", "start": {"dateTime": "2026-07-13T14:00:00Z"}, "end": {"dateTime": "2026-07-13T15:00:00Z"}},
                {"id": "evt2", "summary": "Daily", "start": {"dateTime": "2026-07-13T16:00:00Z"}, "end": {"dateTime": "2026-07-13T17:00:00Z"}},
            ]
        }
        result = await list_events("2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z")
        assert result["count"] == 2
        assert result["events"][0]["summary"] == "Reuniao Joao"
        assert result["events"][0]["id"] == "evt1"

    @pytest.mark.asyncio
    async def test_list_events_empty(self, mock_calendar_service):
        from tools.google_calendar import list_events
        mock_calendar_service.events().list().execute.return_value = {"items": []}
        result = await list_events("2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z")
        assert result["count"] == 0
        assert result["events"] == []


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_create_event_minimal(self, mock_calendar_service):
        from tools.google_calendar import create_event
        mock_calendar_service.events().insert().execute.return_value = {
            "id": "new1", "summary": "Test", "start": {"dateTime": "2026-07-13T14:00:00Z"},
            "end": {"dateTime": "2026-07-13T15:00:00Z"},
        }
        result = await create_event("2026-07-13T14:00:00Z", "2026-07-13T15:00:00Z", "Test")
        assert "event" in result
        assert result["event"]["summary"] == "Test"

    @pytest.mark.asyncio
    async def test_create_event_full(self, mock_calendar_service):
        from tools.google_calendar import create_event
        mock_calendar_service.events().insert().execute.return_value = {
            "id": "new2", "summary": "Reuniao", "start": {"dateTime": "2026-07-13T14:00:00Z"},
            "end": {"dateTime": "2026-07-13T15:00:00Z"},
            "description": "Desc", "location": "Sala 1",
        }
        result = await create_event(
            "2026-07-13T14:00:00Z", "2026-07-13T15:00:00Z", "Reuniao",
            description="Desc", attendees=["a@b.com"], location="Sala 1",
        )
        assert "event" in result


class TestUpdateEvent:
    @pytest.mark.asyncio
    async def test_update_event(self, mock_calendar_service):
        from tools.google_calendar import update_event
        mock_calendar_service.events().get().execute.return_value = {
            "id": "evt1", "summary": "Old", "start": {"dateTime": "2026-07-13T14:00:00Z"},
            "end": {"dateTime": "2026-07-13T15:00:00Z"},
        }
        mock_calendar_service.events().update().execute.return_value = {
            "id": "evt1", "summary": "New", "start": {"dateTime": "2026-07-13T16:00:00Z"},
            "end": {"dateTime": "2026-07-13T17:00:00Z"},
        }
        result = await update_event("evt1", summary="New", start="2026-07-13T16:00:00Z")
        assert "event" in result


class TestDeleteEvent:
    @pytest.mark.asyncio
    async def test_delete_event(self, mock_calendar_service):
        from tools.google_calendar import delete_event
        mock_calendar_service.events().delete().execute.return_value = None
        result = await delete_event("evt1")
        assert result["deleted"] is True


class TestFreebusy:
    @pytest.mark.asyncio
    async def test_freebusy(self, mock_calendar_service):
        from tools.google_calendar import freebusy
        mock_calendar_service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {"busy": [{"start": "2026-07-13T14:00:00Z", "end": "2026-07-13T15:00:00Z"}]}
            }
        }
        result = await freebusy("2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z")
        assert len(result["busy"]) == 1
