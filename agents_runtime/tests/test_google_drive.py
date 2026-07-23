"""Tests for google_drive tool (per-user OAuth, Fase D)."""
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
def mock_drive_service(mock_firestore):
    with patch("tools.google_drive._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


PHONE = "5511966830020"


class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_search_files(self, mock_drive_service):
        from tools.google_drive import search_files
        mock_drive_service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "Ata 2026-07-13.md", "mimeType": "text/markdown"},
                {"id": "f2", "name": "Ata 2026-07-12.md", "mimeType": "text/markdown"},
            ]
        }
        result = await search_files(PHONE, "Ata", instance="jennifer")
        assert result["count"] == 2
        assert "Ata" in result["files"][0]["name"]


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file(self, mock_drive_service):
        from tools.google_drive import upload_file
        mock_drive_service.files().create().execute.return_value = {
            "id": "new1", "name": "test.md", "mimeType": "text/markdown",
            "webViewLink": "https://drive.google.com/file/d/new1",
        }
        result = await upload_file(PHONE, "folder1", "test.md", "# Content", instance="jennifer")
        assert "file" in result
        assert result["file"]["name"] == "test.md"


class TestListFolder:
    @pytest.mark.asyncio
    async def test_list_folder(self, mock_drive_service):
        from tools.google_drive import list_folder
        mock_drive_service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "doc.md", "mimeType": "text/markdown"},
                {"id": "f2", "name": "Subfolder", "mimeType": "application/vnd.google-apps.folder"},
            ]
        }
        result = await list_folder(PHONE, "parent_folder", instance="jennifer")
        assert result["count"] == 2


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_create_folder(self, mock_drive_service):
        from tools.google_drive import create_folder
        mock_drive_service.files().create().execute.return_value = {
            "id": "new_folder", "name": "NewFolder", "mimeType": "application/vnd.google-apps.folder",
        }
        result = await create_folder(PHONE, "NewFolder", parent_id="parent", instance="jennifer")
        assert "folder" in result
        assert result["folder"]["name"] == "NewFolder"


class TestFindOmnichannelAtas:
    @pytest.mark.asyncio
    async def test_find_existing(self, mock_drive_service):
        from tools.google_drive import find_omnichannel_atas_folder
        mock_drive_service.files().list().execute.side_effect = [
            {"files": [{"id": "omni_id"}]},
            {"files": [{"id": "atas_id"}]},
        ]
        result = await find_omnichannel_atas_folder(PHONE, instance="jennifer")
        assert result["folder_id"] == "atas_id"

    @pytest.mark.asyncio
    async def test_omnichannel_not_found(self, mock_drive_service):
        from tools.google_drive import find_omnichannel_atas_folder
        mock_drive_service.files().list().execute.return_value = {"files": []}
        result = await find_omnichannel_atas_folder(PHONE, instance="jennifer")
        assert "error" in result


class TestPerUserOAuth:
    def test_get_service_uses_per_user_oauth(self):
        from tools import google_drive
        from core import oauth_per_user

        google_drive._drive_services.clear()
        with patch.object(google_drive, "build", return_value="service-mock") as mock_build:
            with patch.object(oauth_per_user, "get_user_credentials", return_value=MagicMock()) as mock_user_creds:
                service = google_drive._get_service(PHONE)
                assert mock_user_creds.called
                assert mock_user_creds.call_args.args[0] == PHONE
                assert service == "service-mock"
                assert mock_build.called
                assert mock_build.call_args.args[0] == "drive"

    def test_get_credentials_requires_phone(self):
        from tools import google_drive

        with pytest.raises(RuntimeError, match="phone_required_for_drive_oauth"):
            google_drive._get_credentials("")

    def test_get_credentials_requires_user_setup(self):
        from tools import google_drive
        from core import oauth_per_user

        with patch.object(oauth_per_user, "get_user_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="user_google_oauth_required"):
                google_drive._get_credentials(PHONE)
