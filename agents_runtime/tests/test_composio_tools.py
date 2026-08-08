"""Tests for Composio tool wrappers — HTTP API validation."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch


class TestYoutubeComposio:
    def test_search_videos_http_call(self):
        from tools.youtube_composio import search_videos

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"items": [{"id": "123"}]}}

        with patch("tools.youtube_composio.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.post.return_value = mock_resp
            with patch("tools.youtube_composio._get_api_key", return_value="ck_test123"):
                result = asyncio.run(search_videos("marvin gaye"))

        assert "items" in result
        assert len(result["items"]) == 1

    def test_api_key_missing_graceful(self):
        from tools.youtube_composio import search_videos
        import asyncio

        with patch("tools.youtube_composio._get_api_key", return_value=""):
            result = asyncio.run(search_videos("test"))

        assert result["error"] == "composio_api_key_missing"


class TestLinkedinComposio:
    def test_my_profile_http_call(self):
        from tools.linkedin_composio import my_profile

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"firstName": "Test"}}

        with patch("tools.linkedin_composio.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.post.return_value = mock_resp
            with patch("tools.linkedin_composio._get_api_key", return_value="ck_test"):
                result = asyncio.run(my_profile())

        assert "firstName" in result


class TestGoogledocsComposio:
    def test_create_document_http_call(self):
        from tools.googledocs_composio import create_document

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"documentId": "doc-1"}}

        with patch("tools.googledocs_composio.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.post.return_value = mock_resp
            with patch("tools.googledocs_composio._get_api_key", return_value="ck_test"):
                result = asyncio.run(create_document("Meu Doc"))

        assert result["documentId"] == "doc-1"
