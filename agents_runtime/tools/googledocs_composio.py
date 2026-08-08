"""Google Docs tools via Composio SDK."""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_GDOCS_ACCOUNT = os.getenv("COMPOSIO_GDOCS_ACCOUNT", "googledocs_eyas-blasty")
_CACHED_KEY = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


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
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY from Secret Manager: %s", exc)
        return ""


async def _composio_call(tool_slug: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from composio import Composio
        client = Composio(api_key=_get_api_key())
        result = client.tools.execute(
            slug=tool_slug,
            arguments=arguments,
            connected_account_id=_GDOCS_ACCOUNT,
        )
        return result.get("data", result)
    except ImportError:
        logger.warning("Composio SDK not installed")
        return {"error": "composio_sdk_missing"}
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def create_document(title: str, markdown_text: str = "") -> Dict[str, Any]:
    return await _composio_call("GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN", {
        "title": title[:200],
        "markdown_text": markdown_text[:50000],
    })


async def read_document(doc_id: str) -> Dict[str, Any]:
    return await _composio_call("GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT", {"id": doc_id})


async def search_documents(query: str = "", max_results: int = 10) -> Dict[str, Any]:
    return await _composio_call("GOOGLEDOCS_SEARCH_DOCUMENTS", {
        "query": query[:500],
        "max_results": max_results,
    })


async def export_pdf(doc_id: str) -> Dict[str, Any]:
    return await _composio_call("GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF", {"id": doc_id})
