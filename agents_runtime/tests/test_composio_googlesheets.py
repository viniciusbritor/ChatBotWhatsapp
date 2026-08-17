"""Tests Nível 1: Composio Direto - Google Sheets."""
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


class TestGooglesheetsBasic:
    def test_read_cells_imports(self):
        from tools.googlesheets_composio import read_cells
        assert callable(read_cells)

    def test_write_cells_imports(self):
        from tools.googlesheets_composio import write_cells
        assert callable(write_cells)

    def test_create_spreadsheet_imports(self):
        from tools.googlesheets_composio import create_spreadsheet
        assert callable(create_spreadsheet)


class TestGooglesheetsToolCalls:
    def test_read_cells_returns_range_data(self):
        from tools.googlesheets_composio import read_cells

        mock_data = {"values": [["A1", "B1"], ["A2", "B2"]], "range": "A1:B2"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(read_cells(
                    spreadsheet_id="sheet-123",
                    range_="A1:B2",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLESHEETS_READ_GOOGLE_SHEET"
        assert result["values"] == [["A1", "B1"], ["A2", "B2"]]

    def test_write_cells_returns_updated_count(self):
        from tools.googlesheets_composio import write_cells

        mock_data = {"updatedRows": 2, "updatedColumns": 2, "updatedCells": 4}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(write_cells(
                    spreadsheet_id="sheet-123",
                    range_="A1:B2",
                    values=[["X", "Y"], ["Z", "W"]],
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLESHEETS_WRITE_TO_GOOGLE_SHEET"
        assert result["updatedRows"] == 2

    def test_create_spreadsheet_returns_id(self):
        from tools.googlesheets_composio import create_spreadsheet

        mock_data = {"spreadsheetId": "new-sheet-abc", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-sheet-abc"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_data)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_spreadsheet(
                    title="Minha Planilha",
                    phone="5511966830020",
                ))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLESHEETS_CREATE_GOOGLE_SHEET"
        assert result["spreadsheetId"] == "new-sheet-abc"


class TestGooglesheetsErrorHandling:
    def test_sdk_not_installed(self):
        from tools.googlesheets_composio import read_cells

        with patch("composio.Composio", side_effect=ImportError("composio_sdk_missing")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(read_cells("sheet-1", phone="5511966830020"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_error_envelope(self):
        from tools.googlesheets_composio import write_cells

        with patch("composio.Composio", side_effect=Exception("Quota exceeded")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(write_cells(
                    spreadsheet_id="x", range_="A1", values=[["x"]], phone="5511966830020",
                ))
        assert "error" in result
        assert "Quota exceeded" in result["error"]


class TestGooglesheetsValueConversion:
    def test_write_cells_converts_values_to_strings(self):
        """values sao convertidos para str antes de enviar."""
        from tools.googlesheets_composio import write_cells

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope({"updatedRows": 2})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(write_cells(
                    spreadsheet_id="sheet-1",
                    range_="A1:B2",
                    values=[[1, 2.5], [True, None]],
                    phone="5511966830020",
                ))

        args = mock_client.tools.execute.call_args.kwargs["arguments"]
        assert args["values"] == [["1", "2.5"], ["True", "None"]]