"""Tests for Composio tool wrappers — SDK API validation."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch


class TestYoutubeComposio:
    def test_search_videos_calls_correct_sdk_api(self):
        from tools.youtube_composio import search_videos

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"items": [{"id": "123"}]}}

        with patch("composio.Composio", return_value=mock_client):
            with patch.dict("os.environ", {"COMPOSIO_API_KEY": "test"}):
                result = asyncio.run(search_videos("marvin gaye"))

        assert mock_client.tools.execute.called
        kwargs = mock_client.tools.execute.call_args.kwargs
        assert kwargs["slug"] == "YOUTUBE_SEARCH_YOU_TUBE"
        assert kwargs["arguments"]["query"] == "marvin gaye"
        assert kwargs["connected_account_id"] == "youtube_begall-sozin"
        assert "items" in result

    def test_sdk_not_installed_graceful(self):
        from tools.youtube_composio import search_videos

        with patch.dict("os.environ", {"COMPOSIO_API_KEY": "test"}):
            with patch("composio.Composio", side_effect=ImportError()):
                result = asyncio.run(search_videos("test"))

        assert result["error"] == "composio_sdk_missing"


class TestLinkedinComposio:
    def test_create_post_calls_correct_sdk_api(self):
        from tools.linkedin_composio import create_post

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"id": "post-1"}}

        with patch("composio.Composio", return_value=mock_client):
            with patch.dict("os.environ", {"COMPOSIO_API_KEY": "test"}):
                result = asyncio.run(create_post("hello"))

        kwargs = mock_client.tools.execute.call_args.kwargs
        assert kwargs["slug"] == "LINKEDIN_CREATE_LINKED_IN_POST"
        assert kwargs["connected_account_id"] == "linkedin_struma-torula"


class TestGoogledocsComposio:
    def test_create_document_calls_correct_sdk_api(self):
        from tools.googledocs_composio import create_document

        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {"data": {"documentId": "doc-1"}}

        with patch("composio.Composio", return_value=mock_client):
            with patch.dict("os.environ", {"COMPOSIO_API_KEY": "test"}):
                result = asyncio.run(create_document("Meu Doc"))

        kwargs = mock_client.tools.execute.call_args.kwargs
        assert kwargs["slug"] == "GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN"
        assert kwargs["connected_account_id"] == "googledocs_eyas-blasty"
