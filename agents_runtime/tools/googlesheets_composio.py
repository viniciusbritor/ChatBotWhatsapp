"""Google Sheets tools via Composio (helper compartilhado).

GUARDRAIL §0.8 (17/08/2026): refatorado para usar `composio_call` de
`tools._composio_common` que extrai o data real corretamente.
"""
import logging
from typing import Any, Dict, List

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def read_cells(
    spreadsheet_id: str,
    range_: str = "A1:Z100",
    **kwargs,
) -> Dict[str, Any]:
    """Le celulas de uma planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLESHEETS_READ_GOOGLE_SHEET",
        {"spreadsheet_id": spreadsheet_id, "range": range_},
        user_id=user_id,
    )


async def write_cells(
    spreadsheet_id: str,
    range_: str,
    values: List[List[str]],
    **kwargs,
) -> Dict[str, Any]:
    """Escreve valores em celulas de uma planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLESHEETS_WRITE_TO_GOOGLE_SHEET",
        {
            "spreadsheet_id": spreadsheet_id,
            "range": range_,
            "values": [[str(v) for v in row] for row in values],
        },
        user_id=user_id,
    )


async def create_spreadsheet(title: str, **kwargs) -> Dict[str, Any]:
    """Cria uma nova planilha Google Sheets."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "GOOGLESHEETS_CREATE_GOOGLE_SHEET",
        {"title": title[:200]},
        user_id=user_id,
    )