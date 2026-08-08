"""Google Docs tools via Composio API (HTTP direto)."""
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

_GDOCS_ACCOUNT = os.getenv("COMPOSIO_GDOCS_ACCOUNT", "googledocs_eyas-blasty")
_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
_BASE_URL = "https://backend.composio.dev/api/v3"


def _get_api_key() -> str:
    global _CACHED_KEY
    if _CACHED_KEY:
        return _CACHED_KEY
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{_PROJECT}/secrets/COMPOSIO_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        _CACHED_KEY = response.payload.data.decode("utf-8-sig").strip()
        logger.info("COMPOSIO_API_KEY loaded from SecretManager: %d chars", len(_CACHED_KEY))
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY from Secret Manager: %s", exc)
        return ""


async def _api_call(tool_slug: str, arguments: Dict[str, Any], connected_account_id: str) -> Dict[str, Any]:
    key = _get_api_key()
    if not key:
        return {"error": "composio_api_key_missing"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/tools/{tool_slug}/execute",
                headers={
                    "x-consumer-api-key": key,
                    "Content-Type": "application/json",
                },
                json={
                    "arguments": arguments,
                    "connected_account_id": connected_account_id,
                },
            )
            if resp.status_code >= 400:
                logger.warning("Composio HTTP %d: %s tool=%s", resp.status_code, resp.text[:200], tool_slug)
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
            return data.get("data", data)
    except Exception as exc:
        logger.warning("Composio HTTP call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def create_document(title: str, markdown_text: str = "") -> Dict[str, Any]:
    return await _api_call("GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN", {
        "title": title[:200], "markdown_text": markdown_text[:50000],
    }, _GDOCS_ACCOUNT)


async def read_document(doc_id: str) -> Dict[str, Any]:
    return await _api_call("GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT", {"id": doc_id}, _GDOCS_ACCOUNT)


async def search_documents(query: str = "", max_results: int = 10) -> Dict[str, Any]:
    return await _api_call("GOOGLEDOCS_SEARCH_DOCUMENTS", {
        "query": query[:500], "max_results": max_results,
    }, _GDOCS_ACCOUNT)


async def export_pdf(doc_id: str) -> Dict[str, Any]:
    return await _api_call("GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF", {"id": doc_id}, _GDOCS_ACCOUNT)
