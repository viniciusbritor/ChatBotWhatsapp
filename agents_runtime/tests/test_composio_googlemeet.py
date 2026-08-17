"""Tests Nível 1: Composio Direto - Google Meet."""
import asyncio
from unittest.mock import MagicMock, patch


def composio_envelope(payload: dict) -> dict:
    return {
        "data": {
            "results": [
                {"response": {"successful": True, "data": payload}}
            ]
        }
    }


class TestGooglemeetBasic:
    def test_create_meeting_imports(self):
        from tools.googlemeet_composio import create_meeting
        assert callable(create_meeting)

    def test_list_meetings_imports(self):
        from tools.googlemeet_composio import list_meetings
        assert callable(list_meetings)

    def test_get_meeting_link_imports(self):
        from tools.googlemeet_composio import get_meeting_link
        assert callable(get_meeting_link)


class TestGooglemeetToolCalls:
    def test_create_meeting_returns_hangout_link(self):
        from tools.googlemeet_composio import create_meeting

        mock_data = {"id": "evt-123", "hangoutLink": "https://meet.google.com/abc-defg-hij"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_meeting(
                    summary="Reuniao de equipe",
                    start_time="2026-08-20T15:00:00-03:00",
                    end_time="2026-08-20T16:00:00-03:00",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLECALENDAR_CREATE_EVENT"
        assert "meet.google.com" in result["hangoutLink"]
        # Verifica que ENVIOU conferenceData nos arguments (para Google criar Meet)
        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["conferenceData"]["createRequest"]["requestId"].startswith("meet-")
        assert "5511966830020" in args["conferenceData"]["createRequest"]["requestId"]

    def test_list_meetings_returns_events(self):
        from tools.googlemeet_composio import list_meetings

        mock_data = {"items": [{"id": "evt-1", "summary": "Standup", "hangoutLink": "https://meet.google.com/abc"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_meetings(
                    time_min="2026-08-01T00:00:00-03:00",
                    time_max="2026-08-31T23:59:59-03:00",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLECALENDAR_LIST_EVENTS"
        assert result["items"][0]["summary"] == "Standup"

    def test_get_meeting_link_returns_event(self):
        from tools.googlemeet_composio import get_meeting_link

        mock_data = {"id": "evt-1", "hangoutLink": "https://meet.google.com/xyz"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(get_meeting_link(event_id="evt-1", phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLECALENDAR_GET_EVENT"
        assert result["hangoutLink"].startswith("https://meet.google.com/")


class TestGooglemeetErrorHandling:
    def test_sdk_not_installed(self):
        from tools.googlemeet_composio import create_meeting

        with patch("composio.Composio", side_effect=ImportError()):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_meeting("Test", "2026-08-20T15:00:00-03:00", "2026-08-20T16:00:00-03:00", phone="5511966830020"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_error_envelope(self):
        from tools.googlemeet_composio import create_meeting

        with patch("composio.Composio", side_effect=Exception("Quota exceeded")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_meeting("Test", "2026-08-20T15:00:00-03:00", "2026-08-20T16:00:00-03:00", phone="5511966830020"))
        assert "error" in result
        assert "Quota exceeded" in result["error"]


class TestGooglemeetAttendeeParsing:
    def test_create_meeting_with_attendees(self):
        from tools.googlemeet_composio import create_meeting

        mock_data = {"id": "evt-1", "hangoutLink": "https://meet.google.com/abc"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(create_meeting(
                    summary="Reuniao",
                    start_time="2026-08-20T15:00:00-03:00",
                    end_time="2026-08-20T16:00:00-03:00",
                    attendees="alice@example.com,bob@example.com",
                    phone="5511966830020",
                ))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert len(args["attendees"]) == 2
        assert args["attendees"][0]["email"] == "alice@example.com"
        assert args["attendees"][1]["email"] == "bob@example.com"

    def test_create_meeting_without_attendees(self):
        from tools.googlemeet_composio import create_meeting

        mock_data = {"id": "evt-1", "hangoutLink": "https://meet.google.com/abc"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(create_meeting(
                    summary="Reuniao",
                    start_time="2026-08-20T15:00:00-03:00",
                    end_time="2026-08-20T16:00:00-03:00",
                    phone="5511966830020",
                ))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert "attendees" not in args