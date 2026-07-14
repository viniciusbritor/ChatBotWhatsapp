"""Tests for google_drive tool."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_drive_service():
    with patch("tools.google_drive._get_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


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
        result = await search_files("Ata")
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
        result = await upload_file("folder1", "test.md", "# Content")
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
        result = await list_folder("parent_folder")
        assert result["count"] == 2


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_create_folder(self, mock_drive_service):
        from tools.google_drive import create_folder
        mock_drive_service.files().create().execute.return_value = {
            "id": "new_folder", "name": "NewFolder", "mimeType": "application/vnd.google-apps.folder",
        }
        result = await create_folder("NewFolder", parent_id="parent")
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
        result = await find_omnichannel_atas_folder()
        assert result["folder_id"] == "atas_id"

    @pytest.mark.asyncio
    async def test_omnichannel_not_found(self, mock_drive_service):
        from tools.google_drive import find_omnichannel_atas_folder
        mock_drive_service.files().list().execute.return_value = {"files": []}
        result = await find_omnichannel_atas_folder()
        assert "error" in result