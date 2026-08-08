"""Tests for Composio tool wrappers — SDK + Secret Manager."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch


class TestYoutubeComposio:
    def test_search_videos_calls_sdk(self):
        from tools.youtube_composio import search_videos

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"items": [{"id": "123"}]}}

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools.youtube_composio._get_api_key", return_value="ck_test123"):
                result = asyncio.run(search_videos("marvin gaye"))

        assert mock_client.tools.execute.called
        assert mock_client.tools.execute.call_args.kwargs["slug"] == "YOUTUBE_SEARCH_YOU_TUBE"
        assert "items" in result

    def test_sdk_not_installed_graceful(self):
        from tools.youtube_composio import search_videos

        with patch("tools.youtube_composio._get_api_key", return_value="ck_test"):
            with patch("composio.Composio", side_effect=ImportError()):
                result = asyncio.run(search_videos("test"))
        assert result["error"] == "composio_sdk_missing"


class TestLinkedinComposio:
    def test_my_profile_calls_sdk(self):
        from tools.linkedin_composio import my_profile

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"firstName": "Test"}}

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools.linkedin_composio._get_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile())

        assert mock_client.tools.execute.call_args.kwargs["slug"] == "LINKEDIN_GET_MY_INFO"
        assert result["firstName"] == "Test"


class TestGoogledocsComposio:
    def test_create_document_calls_sdk(self):
        from tools.googledocs_composio import create_document

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"documentId": "doc-1"}}

        with patch("composio.Composio", return_value=mock_client):
            with patch("tools.googledocs_composio._get_api_key", return_value="ck_test"):
                result = asyncio.run(create_document("Meu Doc"))

        assert mock_client.tools.execute.call_args.kwargs["slug"] == "GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN"
        assert result["documentId"] == "doc-1"
