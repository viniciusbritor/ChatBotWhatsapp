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
    # Twitter/X — adicionado em 18/08/2026. Verificar versao atualizada
    # no painel Composio antes de promover.
    "twitter": "20260818_00",
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
    """Chama Composio via REST API direta (workaround 18/08/2026) com SDK fallback.

    Esta funcao eh o helper compartilhado por TODOS os tools/*_composio.py.
    Cada tool especifica apenas constroi os arguments e passa pra ca.

    WORKAROUND: o SDK composio (versao 0.10.10 / composio-client 1.27.0) chama
    o endpoint /api/v3/tools/execute que retorna envelopes inconsistentes
    para toolkits Custom (Twitter no plano Hobby). A REST API direta retorna
    o erro real (sem mascaramento) e nos permite detectar o paywall do X API.

    Mantem o SDK como fallback se httpx falhar.
    """
    api_key = get_composio_api_key()

    # Caminho primario: REST API direta
    try:
        import httpx

        def _execute_rest() -> Dict[str, Any]:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"https://backend.composio.dev/api/v3/tools/execute/{tool_slug}",
                    headers={
                        "X-API-Key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"user_id": user_id, "arguments": arguments},
                )
            try:
                return resp.json()
            except Exception:
                return {
                    "successful": False,
                    "status_code": resp.status_code,
                    "data": {"error": resp.text[:500]},
                    "error": f"http_{resp.status_code}",
                }

        result = await asyncio.to_thread(_execute_rest)
        # Extrair HTTP error code
        http_status = result.get("status_code")
        if isinstance(http_status, int) and http_status >= 400:
            data = result.get("data") or {}
            err_msg = (
                data.get("error")
                or data.get("http_error")
                or data.get("message")
                or result.get("error")
                or "http_error"
            )
            logger.warning(
                "Composio REST call failed: http=%s tool=%s err=%s",
                http_status, tool_slug, str(err_msg)[:200],
            )
            return _error_envelope(f"composio_http_{http_status}: {str(err_msg)[:200]}")

        # Detectar falhas em qualquer nivel do envelope (REST API Composio retorna
        # tanto outer.successful=False quanto data.successful=False para falhas do tool).
        if result.get("successful") is False:
            # Outer level failure (ex: action execute nao existe, rate limit do Composio)
            err_data = result.get("data") or {}
            err = (
                err_data.get("error")
                or err_data.get("message")
                or err_data.get("http_error")
                or result.get("error")
                or "composio_outer_failure"
            )
            logger.warning(
                "Composio outer failure for tool %s: %s",
                tool_slug, str(err)[:200],
            )
            return _error_envelope(str(err)[:500])

        data = result.get("data")
        if isinstance(data, dict) and data.get("successful") is False:
            # Tool executado mas X API retornou 401/403 — propagar o erro real
            err = data.get("error") or data.get("message") or "tool_returned_failure"
            logger.warning(
                "Tool %s returned failure: %s",
                tool_slug, str(err)[:200],
            )
            return _error_envelope(str(err)[:500])
        return result
    except ImportError:
        logger.warning("httpx_missing_falling_back_to_sdk")
    except Exception as exc:
        logger.warning(
            "Composio REST call failed: %s tool=%s — falling back to SDK",
            exc, tool_slug,
        )

    # Fallback: SDK (mesmo comportamento de antes)
    try:
        from composio import Composio
        client = Composio(api_key=api_key, toolkit_versions=TOOLKIT_VERSIONS)
    except ImportError:
        return _error_envelope("composio_sdk_missing")
    except Exception as exc:
        logger.warning("Composio client init failed: %s", exc)
        return _error_envelope(f"composio_client_init_failed: {exc}")

    try:
        result = await asyncio.to_thread(
            client.tools.execute,
            slug=tool_slug,
            arguments=arguments,
            user_id=user_id,
        )
        return _extract_composio_data(result)
    except Exception as exc:
        logger.warning("Composio SDK call failed: %s tool=%s", exc, tool_slug)
        return _error_envelope(str(exc)[:200])