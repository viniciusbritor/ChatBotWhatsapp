"""Google Sheets tools via Composio SDK + Secret Manager."""
import logging
import os
from typing import Any, Dict, List

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


async def read_cells(spreadsheet_id: str, range_: str = "A1:Z100", **kwargs) -> Dict[str, Any]:
    """Lê células de uma planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLESHEETS_READ_GOOGLE_SHEET", {
        "spreadsheet_id": spreadsheet_id, "range": range_,
    }, user_id=user_id)


async def write_cells(spreadsheet_id: str, range_: str, values: List[List[str]], **kwargs) -> Dict[str, Any]:
    """Escreve valores em células de uma planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLESHEETS_WRITE_TO_GOOGLE_SHEET", {
        "spreadsheet_id": spreadsheet_id, "range": range_,
        "values": [[str(v) for v in row] for row in values],
    }, user_id=user_id)


async def create_spreadsheet(title: str, **kwargs) -> Dict[str, Any]:
    """Cria uma nova planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await _composio_call("GOOGLESHEETS_CREATE_GOOGLE_SHEET", {
        "title": title[:200],
    }, user_id=user_id)
