"""Tests for web_search tool (Serper + cache)."""
import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock


class TestSerperSearch:
    @pytest.mark.asyncio
    async def test_serper_search_success(self):
        from tools.web_search import serper_search, L1_CACHE

        L1_CACHE.clear()

        with patch("tools.web_search.get_secret", return_value="test-key"):
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "organic": [
                    {"title": "Result 1", "link": "https://example.com/1", "snippet": "Snippet 1", "position": 1},
                    {"title": "Result 2", "link": "https://example.com/2", "snippet": "Snippet 2", "position": 2},
                ]
            }
            mock_response.raise_for_status = MagicMock()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                result = await serper_search("test query")

        assert result["query"] == "test query"
        assert result["cached"] is False
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_serper_search_l1_cache_hit(self):
        from tools.web_search import serper_search, L1_CACHE

        L1_CACHE.clear()
        L1_CACHE["hash"] = {"data": [{"title": "cached"}], "ts": time.time()}

        query = "cached query"
        import hashlib
        q_hash = hashlib.sha256(query.lower().strip().encode("utf-8")).hexdigest()[:32]
        L1_CACHE[q_hash] = {"data": [{"title": "cached"}], "ts": time.time()}

        result = await serper_search(query)
        assert result["cached"] is True
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_serper_search_no_api_key(self):
        from tools.web_search import serper_search, L1_CACHE

        L1_CACHE.clear()
        with patch("tools.web_search.get_secret", return_value=None):
            result = await serper_search("test")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_serper_search_http_error(self):
        from tools.web_search import serper_search, L1_CACHE
        import httpx

        L1_CACHE.clear()
        with patch("tools.web_search.get_secret", return_value="test-key"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_post = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
                mock_client.return_value.__aenter__.return_value.post = mock_post
                result = await serper_search("test")
        assert "error" in result


class TestFetchUrl:
    @pytest.mark.asyncio
    async def test_fetch_url_success(self):
        from tools.web_search import fetch_url
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "Page content"
            mock_response.status_code = 200
            mock_response.url = "https://example.com"
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await fetch_url("https://example.com")
        assert result["content"] == "Page content"
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_fetch_url_error(self):
        from tools.web_search import fetch_url
        import httpx
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            result = await fetch_url("https://example.com")
        assert "error" in result