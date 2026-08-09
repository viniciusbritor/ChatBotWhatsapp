"""Google Docs tools via Composio SDK + Secret Manager."""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

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
        logger.info("COMPOSIO_API_KEY loaded: %d chars", len(_CACHED_KEY))
        return _CACHED_KEY
    except Exception as exc:
        logger.error("Failed to load COMPOSIO_API_KEY: %s", exc)
        return (os.getenv("COMPOSIO_API_KEY", "") or "").strip()


async def _composio_call(tool_slug: str, arguments: Dict[str, Any], user_id: str = "") -> Dict[str, Any]:
    try:
        from composio import Composio
        from tools._composio_common import TOOLKIT_VERSIONS
        client = Composio(api_key=_get_api_key(), toolkit_versions=TOOLKIT_VERSIONS)
        result = client.tools.execute(slug=tool_slug, arguments=arguments, user_id=user_id)
        return result.get("data", result)
    except ImportError:
        return {"error": "composio_sdk_missing"}
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return {"error": str(exc)[:200]}


async def create_document(title: str, markdown_text: str = "", **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN", {
        "title": title[:200], "markdown_text": markdown_text[:50000],
    }, user_id=user_id)


async def read_document(doc_id: str, **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT", {"document_id": doc_id}, user_id=user_id)


async def search_documents(query: str = "", max_results: int = 10, **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLEDOCS_SEARCH_DOCUMENTS", {
        "query": query[:500], "max_results": max_results,
    }, user_id=user_id)


async def export_pdf(doc_id: str, **kwargs) -> Dict[str, Any]:
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF", {"file_id": doc_id}, user_id=user_id)
