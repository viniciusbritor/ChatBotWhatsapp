"""Tests Nível 1: Composio Direto - Google Docs.

Valida tools do googledocs_composio.py diretamente contra SDK mockado.
"""
import asyncio
from unittest.mock import MagicMock, patch


def composio_envelope(payload: dict) -> dict:
    """Retorna formato envelope real do Composio SDK."""
    return {
        "data": {
            "results": [
                {"response": {"successful": True, "data": payload}}
            ]
        }
    }


class TestGoogledocsBasic:
    def test_create_document_imports(self):
        from tools.googledocs_composio import create_document
        assert callable(create_document)

    def test_read_document_imports(self):
        from tools.googledocs_composio import read_document
        assert callable(read_document)

    def test_search_documents_imports(self):
        from tools.googledocs_composio import search_documents
        assert callable(search_documents)

    def test_export_pdf_imports(self):
        from tools.googledocs_composio import export_pdf
        assert callable(export_pdf)


class TestGoogledocsToolCalls:
    def test_create_document_returns_doc_id(self):
        from tools.googledocs_composio import create_document

        mock_doc = {"documentId": "doc-abc-123", "title": "Meu Doc"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_doc)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_document("Meu Doc", markdown_text="# Titulo", phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN"
        assert result["documentId"] == "doc-abc-123"

    def test_read_document_extracts_content(self):
        from tools.googledocs_composio import read_document

        mock_content = {"text": "Conteudo do documento aqui", "documentId": "doc-1"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_content)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(read_document("doc-1", phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT"
        assert result["text"] == "Conteudo do documento aqui"

    def test_search_documents_returns_results(self):
        from tools.googledocs_composio import search_documents

        mock_results = {"documents": [{"documentId": "doc-1", "title": "Ata 01/07"}], "count": 1}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_results)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(search_documents("ata", max_results=5, phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLEDOCS_SEARCH_DOCUMENTS"
        assert result["count"] == 1

    def test_export_pdf_returns_pdf_url(self):
        from tools.googledocs_composio import export_pdf

        mock_export = {"pdfUrl": "https://docs.google.com/doc-1/export?format=pdf", "documentId": "doc-1"}
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope(mock_export)

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(export_pdf("doc-1", phone="5511966830020"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF"
        assert "pdf" in result["pdfUrl"].lower()


class TestGoogledocsErrorHandling:
    def test_sdk_not_installed(self):
        from tools.googledocs_composio import create_document

        with patch("composio.Composio", side_effect=ImportError("composio_sdk_missing")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(create_document("Test"))
        assert result["error"] == "composio_sdk_missing"

    def test_api_error_envelope(self):
        from tools.googledocs_composio import read_document

        with patch("composio.Composio", side_effect=Exception("OAuth revoked")):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                result = asyncio.run(read_document("doc-1", phone="5511966830020"))
        assert "error" in result
        assert "OAuth revoked" in result["error"]


class TestGoogledocsPhoneExtraction:
    def test_create_document_uses_phone_from_kwargs(self):
        from tools.googledocs_composio import create_document

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = composio_envelope({"documentId": "x"})

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools._composio_common.get_composio_api_key", return_value="ck_test"):
                asyncio.run(create_document("Test", phone="5511999999999"))

        assert mock_client.tools.execute.call_args.kwargs["user_id"] == "5511999999999"