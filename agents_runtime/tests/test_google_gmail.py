"""Tests for google_gmail tool (per-user OAuth, Fase D)."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_firestore(monkeypatch):
    fake_db = MagicMock()
    docs = [{"owner_phone": PHONE, "owner_uid": PHONE, "instance": "jennifer"}]

    class _FC:
        def where(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def stream(self):
            items = list(docs)
            for item in items:
                captured = item
                yield MagicMock(to_dict=lambda c=captured: c, id=captured["instance"])

    fake_db.collection.return_value = _FC()
    monkeypatch.setattr("agent_loader._get_firestore_client", lambda: fake_db)
    monkeypatch.setattr("core.owner._get_firestore_client", lambda: fake_db)
    return fake_db


@pytest.fixture
def mock_gmail_service(mock_firestore):
    with patch("tools.google_gmail._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


PHONE = "5511966830020"


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
        result = await search_messages(PHONE, "subject:reuniao", instance="jennifer")
        assert result["count"] >= 1
        assert result["messages"][0]["from"] == "joao@example.com"

    @pytest.mark.asyncio
    async def test_search_messages_empty(self, mock_gmail_service):
        from tools.google_gmail import search_messages
        mock_gmail_service.users().messages().list().execute.return_value = {"messages": []}
        result = await search_messages(PHONE, "subject:naoexiste", instance="jennifer")
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
        result = await get_thread(PHONE, "t1", instance="jennifer")
        assert result["count"] == 2


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_text(self, mock_gmail_service):
        from tools.google_gmail import send_message
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent1", "threadId": "t1",
        }
        result = await send_message(PHONE, "to@example.com", "Subject", "Body text", instance="jennifer")
        assert "message" in result
        assert result["message"]["to"] == "to@example.com"

    @pytest.mark.asyncio
    async def test_send_message_html(self, mock_gmail_service):
        from tools.google_gmail import send_message
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent2", "threadId": "t2",
        }
        result = await send_message(PHONE, "to@example.com", "Subject", "<h1>HTML</h1>", html=True, instance="jennifer")
        assert "message" in result


class TestPerUserOAuth:
    def test_get_service_uses_per_user_oauth(self):
        from tools import google_gmail
        from core import oauth_per_user

        google_gmail._gmail_services.clear()
        with patch.object(google_gmail, "build", return_value="service-mock") as mock_build:
            with patch.object(oauth_per_user, "get_user_credentials", return_value=MagicMock()) as mock_user_creds:
                service = google_gmail._get_service(PHONE)
                assert mock_user_creds.called
                assert mock_user_creds.call_args.args[0] == PHONE
                assert service == "service-mock"
                assert mock_build.called
                assert mock_build.call_args.args[0] == "gmail"

    def test_get_credentials_requires_phone(self):
        from tools import google_gmail

        with pytest.raises(RuntimeError, match="phone_required_for_gmail_oauth"):
            google_gmail._get_credentials("")

    def test_get_credentials_requires_user_setup(self):
        from tools import google_gmail
        from core import oauth_per_user

        with patch.object(oauth_per_user, "get_user_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="user_google_oauth_required"):
                google_gmail._get_credentials(PHONE)
