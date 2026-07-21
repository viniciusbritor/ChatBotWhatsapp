"""Tests for google_gmail tool."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_gmail_service():
    with patch("tools.google_gmail._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


class TestSearchMessages:
    @pytest.mark.asyncio
    async def test_search_messages(self, mock_gmail_service):
        from tools.google_gmail import search_messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}, {"id": "m2"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "m1",
            "threadId": "t1",
            "snippet": "Reuniao amanha",
            "payload": {
                "headers": [
                    {"name": "From", "value": "joao@example.com"},
                    {"name": "Subject", "value": "Reuniao"},
                    {"name": "Date", "value": "Mon, 13 Jul 2026"},
                ],
                "body": {"data": "VGVzdGU="},
                "mimeType": "text/plain",
            },
        }
        result = await search_messages("subject:reuniao")
        assert result["count"] >= 1
        assert result["messages"][0]["from"] == "joao@example.com"

    @pytest.mark.asyncio
    async def test_search_messages_empty(self, mock_gmail_service):
        from tools.google_gmail import search_messages
        mock_gmail_service.users().messages().list().execute.return_value = {"messages": []}
        result = await search_messages("subject:naoexiste")
        assert result["count"] == 0


class TestGetThread:
    @pytest.mark.asyncio
    async def test_get_thread(self, mock_gmail_service):
        from tools.google_gmail import get_thread
        mock_gmail_service.users().threads().get().execute.return_value = {
            "messages": [
                {"id": "m1", "threadId": "t1", "snippet": "msg1",
                 "payload": {"headers": [{"name": "Subject", "value": "Test"}], "mimeType": "text/plain", "body": {"data": "aGk="}}},
                {"id": "m2", "threadId": "t1", "snippet": "msg2",
                 "payload": {"headers": [{"name": "Subject", "value": "Re: Test"}], "mimeType": "text/plain", "body": {"data": "aGk="}}},
            ]
        }
        result = await get_thread("t1")
        assert result["count"] == 2


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_text(self, mock_gmail_service):
        from tools.google_gmail import send_message
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent1", "threadId": "t1",
        }
        result = await send_message("to@example.com", "Subject", "Body text")
        assert "message" in result
        assert result["message"]["to"] == "to@example.com"

    @pytest.mark.asyncio
    async def test_send_message_html(self, mock_gmail_service):
        from tools.google_gmail import send_message
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent2", "threadId": "t2",
        }
        result = await send_message("to@example.com", "Subject", "<h1>HTML</h1>", html=True)
        assert "message" in result
