"""Tests for google_calendar tool (per-user OAuth, Fase D)."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_firestore(monkeypatch):
    """Patch Firestore to a MagicMock that returns the configured WhatsApp account."""
    fake_db = MagicMock()
    docs_iter = [
        {"owner_phone": "5511966830020", "owner_uid": "5511966830020", "instance": "jennifer"}
    ]

    class _FakeCollection:
        def where(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def stream(self):
            items = list(docs_iter)
            for idx, item in enumerate(items):
                doc_id = item["instance"]
                captured = item
                yield MagicMock(to_dict=lambda c=captured: c, id=doc_id)

    fake_db.collection.return_value = _FakeCollection()
    monkeypatch.setattr("agent_loader._get_firestore_client", lambda: fake_db)
    monkeypatch.setattr("core.owner._get_firestore_client", lambda: fake_db)
    return fake_db


@pytest.fixture
def mock_calendar_service(mock_firestore):
    """Mock Google Calendar API service."""
    with patch("tools.google_calendar._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


PHONE = "5511966830020"


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
        result = await list_events(
            PHONE, "2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z", instance="jennifer"
        )
        assert result["count"] == 2
        assert result["events"][0]["summary"] == "Reuniao Joao"
        assert result["events"][0]["id"] == "evt1"

    @pytest.mark.asyncio
    async def test_list_events_empty(self, mock_calendar_service):
        from tools.google_calendar import list_events
        mock_calendar_service.events().list().execute.return_value = {"items": []}
        result = await list_events(
            PHONE, "2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z", instance="jennifer"
        )
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
        result = await create_event(
            PHONE, "2026-07-13T14:00:00Z", "2026-07-13T15:00:00Z", "Test",
            instance="jennifer",
        )
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
            PHONE, "2026-07-13T14:00:00Z", "2026-07-13T15:00:00Z", "Reuniao",
            description="Desc", attendees=["a@b.com"], location="Sala 1", instance="jennifer",
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
        result = await update_event(
            PHONE, "evt1", summary="New", start="2026-07-13T16:00:00Z", instance="jennifer"
        )
        assert "event" in result


class TestMoveEvent:
    """move_event: PATCH in-place de start/end preserva o id (nao duplica)."""

    @pytest.mark.asyncio
    async def test_move_event_preserves_id(self, mock_calendar_service):
        """Move retorna o mesmo id - email de update vai para os participantes."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "evt1",
            "summary": "OmniChannel - Startup",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
            "attendees": [{"email": "rafael@example.com"}],
        }
        result = await move_event(
            PHONE, "evt1",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            instance="jennifer",
        )
        assert result["moved"] is True
        assert result["event_id"] == "evt1"
        assert result["event"]["id"] == "evt1"
        assert result["event"]["summary"] == "OmniChannel - Startup"

    @pytest.mark.asyncio
    async def test_move_event_uses_patch_not_insert(self, mock_calendar_service):
        """Verifica que o service chama patch() (nao insert) - chave para nao duplicar."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "evt1", "summary": "Reuniao",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
        }
        # Capturar calls ANTES (evita cross-test contamination de insert de outros testes)
        patch_calls_before = mock_calendar_service.events().patch.call_count
        insert_calls_before = mock_calendar_service.events().insert.call_count
        await move_event(
            PHONE, "evt1",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            instance="jennifer",
        )
        # patch() deve ter sido chamado uma vez
        assert mock_calendar_service.events().patch.call_count == patch_calls_before + 1
        # insert() NAO deve ter sido chamado durante o move_event
        assert mock_calendar_service.events().insert.call_count == insert_calls_before

    @pytest.mark.asyncio
    async def test_move_event_sends_update_notification_by_default(self, mock_calendar_service):
        """sendUpdates='all' envia e-mail de atualizacao aos participantes."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "evt1", "summary": "X",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
        }
        await move_event(
            PHONE, "evt1",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            instance="jennifer",
        )
        call_kwargs = mock_calendar_service.events().patch.call_args.kwargs
        assert call_kwargs.get("sendUpdates") == "all"

    @pytest.mark.asyncio
    async def test_move_event_no_notification_when_disabled(self, mock_calendar_service):
        """notify_attendees=False suprime o e-mail."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "evt1", "summary": "X",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
        }
        await move_event(
            PHONE, "evt1",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            notify_attendees=False,
            instance="jennifer",
        )
        call_kwargs = mock_calendar_service.events().patch.call_args.kwargs
        assert call_kwargs.get("sendUpdates") == "none"

    @pytest.mark.asyncio
    async def test_move_event_includes_event_id(self, mock_calendar_service):
        """O event_id do evento original deve ser passado ao patch."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "abc123", "summary": "X",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
        }
        await move_event(
            PHONE, "abc123",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            instance="jennifer",
        )
        call_kwargs = mock_calendar_service.events().patch.call_args.kwargs
        assert call_kwargs.get("eventId") == "abc123"

    @pytest.mark.asyncio
    async def test_move_event_includes_timezone(self, mock_calendar_service):
        """Timezone e incluida no body do patch."""
        from tools.google_calendar import move_event

        mock_calendar_service.events().patch().execute.return_value = {
            "id": "evt1", "summary": "X",
            "start": {"dateTime": "2026-08-11T20:30:00-03:00"},
            "end": {"dateTime": "2026-08-11T21:30:00-03:00"},
        }
        await move_event(
            PHONE, "evt1",
            new_start="2026-08-11T20:30:00-03:00",
            new_end="2026-08-11T21:30:00-03:00",
            timezone="America/Sao_Paulo",
            instance="jennifer",
        )
        call_kwargs = mock_calendar_service.events().patch.call_args.kwargs
        body = call_kwargs.get("body", {})
        assert body["start"]["timeZone"] == "America/Sao_Paulo"
        assert body["end"]["timeZone"] == "America/Sao_Paulo"


class TestDeleteEvent:
    @pytest.mark.asyncio
    async def test_delete_event(self, mock_calendar_service):
        from tools.google_calendar import delete_event
        mock_calendar_service.events().delete().execute.return_value = None
        result = await delete_event(PHONE, "evt1", instance="jennifer")
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
        result = await freebusy(
            PHONE, "2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z", instance="jennifer"
        )
        assert len(result["busy"]) == 1


class TestPerUserOAuth:
    def test_get_service_uses_per_user_oauth(self):
        from tools import google_calendar
        from core import oauth_per_user

        google_calendar._calendar_services.clear()
        with patch.object(google_calendar, "build", return_value="service-mock") as mock_build:
            with patch.object(oauth_per_user, "get_user_credentials", return_value=MagicMock()) as mock_user_creds:
                service = google_calendar._get_service(PHONE)
                assert mock_user_creds.called
                assert mock_user_creds.call_args.args[0] == PHONE
                assert service == "service-mock"
                assert mock_build.called
                assert mock_build.call_args.args[0] == "calendar"

    def test_get_credentials_requires_phone(self):
        from tools import google_calendar

        with pytest.raises(RuntimeError, match="phone_required_for_calendar_oauth"):
            google_calendar._get_credentials("")

    def test_get_credentials_requires_user_setup(self):
        from tools import google_calendar
        from core import oauth_per_user

        with patch.object(oauth_per_user, "get_user_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="user_google_oauth_required"):
                google_calendar._get_credentials(PHONE)
