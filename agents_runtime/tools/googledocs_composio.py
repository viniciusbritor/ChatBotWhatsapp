"""Google Docs tools via Composio (helper compartilhado).

GUARDRAIL §0.8 (17/08/2026): refatorado para usar `composio_call` de
`tools._composio_common` que extrai o data real corretamente.
"""
import logging
from typing import Any, Dict

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def create_document(title: str, markdown_text: str = "", **kwargs) -> Dict[str, Any]:
    """Cria documento Google Docs a partir de markdown."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN",
        {"title": title[:200], "markdown_text": markdown_text[:50000]},
        user_id=user_id,
    )


async def read_document(doc_id: str, **kwargs) -> Dict[str, Any]:
    """Le o conteudo plain text de um documento."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLEDOCS_GET_DOCUMENT_PLAINTEXT",
        {"document_id": doc_id},
        user_id=user_id,
    )


async def search_documents(query: str = "", max_results: int = 10, **kwargs) -> Dict[str, Any]:
    """Busca documentos por query."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLEDOCS_SEARCH_DOCUMENTS",
        {"query": query[:500], "max_results": max_results},
        user_id=user_id,
    )


async def export_pdf(doc_id: str, **kwargs) -> Dict[str, Any]:
    """Exporta documento como PDF."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLEDOCS_EXPORT_DOCUMENT_AS_PDF",
        {"file_id": doc_id},
        user_id=user_id,
    )