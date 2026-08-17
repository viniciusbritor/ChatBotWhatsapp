"""Shared Composio config + helpers comuns para todas as tools Composio.

GUARDRAIL §0.8 (17/08/2026): helper centralizado para:
1. Pinning de toolkit versions
2. Extracao CORRETA do data real da resposta Composio
3. Retry basico + logging estruturado

Formato de retorno do Composio SDK (client.tools.execute):

    {
      "data": {
        "results": [
          {
            "response": {
              "successful": true,
              "data": { ... payload real ... }
            }
          }
        ]
      }
    }

ERRO comum (17/08/2026): o caller fazia `result.get("data", result)` e recebia
a lista envelope, NAO o payload real. Corrigido aqui em `_extract_composio_data`.
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOOLKIT_VERSIONS: Dict[str, str] = {
    "youtube": "20260721_00",
    "linkedin": "20260724_00",
    "googledocs": "20260721_00",
    "github": "20260728_00",
    "notion": "20260730_00",
    "googlesheets": "20260806_00",
    "one_drive": "20260804_00",
    "googlemeet": "20250901_00",
    "microsoft_teams": "20250901_00",
}

_CACHED_KEY: Optional[str] = None
_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")


def get_composio_api_key() -> str:
    """Carrega COMPOSIO_API_KEY do Secret Manager com cache."""
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


def _extract_composio_data(result: Any) -> Any:
    """Extrai o data real do envelope Composio.

    Formato de entrada:
        {"data": {"results": [{"response": {"data": {...}, "successful": True}}]}}
        ou variantes (error envelope)

    Retorna o `data` mais interno, ou o envelope se nao conseguir extrair.
    """
    if not isinstance(result, dict):
        return result
    data = result.get("data", result)
    if not isinstance(data, dict):
        return data
    # Se tem results[0].response.data, retorna isso
    results = data.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            response = first.get("response", first)
            if isinstance(response, dict):
                return response.get("data", response)
    return data


def _error_envelope(error_msg: str) -> Dict[str, Any]:
    """Envelope de erro padrao."""
    return {"error": error_msg, "data": {"results": []}, "successful": False}


async def composio_call(
    tool_slug: str,
    arguments: Dict[str, Any],
    user_id: str = "",
) -> Dict[str, Any]:
    """Chama Composio SDK e retorna o data real extraido.

    Esta funcao eh o helper compartilhado por TODOS os tools/*_composio.py.
    Cada tool especifica apenas constroi os arguments e passa pra ca.
    """
    try:
        from composio import Composio
        client = Composio(api_key=get_composio_api_key(), toolkit_versions=TOOLKIT_VERSIONS)
    except ImportError:
        return _error_envelope("composio_sdk_missing")
    except Exception as exc:
        logger.warning("Composio client init failed: %s", exc)
        return _error_envelope(f"composio_client_init_failed: {exc}")

    try:
        # SDK 0.x e sync — chamamos via asyncio.to_thread para nao bloquear
        result = await asyncio.to_thread(
            client.tools.execute,
            slug=tool_slug,
            arguments=arguments,
            user_id=user_id,
        )
        return _extract_composio_data(result)
    except Exception as exc:
        logger.warning("Composio call failed: %s tool=%s", exc, tool_slug)
        return _error_envelope(str(exc)[:200])