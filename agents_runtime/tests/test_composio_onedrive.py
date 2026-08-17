"""Tests Nível 1: Composio Direto - OneDrive."""
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


class TestOnedriveBasic:
    def test_list_items_imports(self):
        from tools.onedrive_composio import list_items
        assert callable(list_items)

    def test_list_folder_children_imports(self):
        from tools.onedrive_composio import list_folder_children
        assert callable(list_folder_children)

    def test_list_drives_imports(self):
        from tools.onedrive_composio import list_drives
        assert callable(list_drives)


class TestOnedriveToolCalls:
    def test_list_items_returns_files(self):
        from tools.onedrive_composio import list_items

        mock_data = {"value": [{"id": "file-1", "name": "doc.pdf"}, {"id": "folder-2", "name": "Pasta"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_items(top=10, phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "ONE_DRIVE_ONEDRIVE_LIST_ITEMS"
        assert len(result["value"]) == 2

    def test_list_folder_children_returns_children(self):
        from tools.onedrive_composio import list_folder_children

        mock_data = {"value": [{"id": "sub-1", "name": "subfolder"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_folder_children(
                    folder_path="/Documents", top=50, phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "ONE_DRIVE_LIST_FOLDER_CHILDREN"
        assert result["value"][0]["name"] == "subfolder"

    def test_list_drives_returns_drives(self):
        from tools.onedrive_composio import list_drives

        mock_data = {"value": [{"id": "drive-1", "name": "OneDrive Pessoal"}]}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_drives(phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "ONE_DRIVE_LIST_DRIVES"
        assert result["value"][0]["name"] == "OneDrive Pessoal"


class TestOnedriveErrorHandling:
    def test_sdk_not_installed(self):
        from tools.onedrive_composio import list_items

        with patch("composio.Composio", side_effect=ImportError()):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_items(phone="5511966830020"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_error_envelope(self):
        from tools.onedrive_composio import list_items

        with patch("composio.Composio", side_effect=Exception("OneDrive down")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(list_items(phone="5511966830020"))
        assert "error" in result
        assert "OneDrive down" in result["error"]


class TestOnedriveTopParameter:
    def test_list_items_clamps_top_to_valid_range(self):
        from tools.onedrive_composio import list_items

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope({"value": []})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(list_items(top=10000, phone="5511966830020"))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["top"] <= 999  # clamped to max 999

    def test_list_items_enforces_min_top(self):
        from tools.onedrive_composio import list_items

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope({"value": []})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(list_items(top=0, phone="5511966830020"))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["top"] >= 1  # clamped to min 1