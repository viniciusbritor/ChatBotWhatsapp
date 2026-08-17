"""OneDrive tools via Composio (helper compartilhado).

GUARDRAIL §0.8 (17/08/2026): refatorado para usar `composio_call` de
`tools._composio_common` que extrai o data real corretamente.
"""
import logging
from typing import Any, Dict

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def list_items(top: int = 50, **kwargs) -> Dict[str, Any]:
    """Lista itens do OneDrive."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "ONE_DRIVE_ONEDRIVE_LIST_ITEMS",
        {"top": max(1, min(999, top)), "user_id": "me"},
        user_id=user_id,
    )


async def list_folder_children(
    folder_path: str = "/", top: int = 200, **kwargs
) -> Dict[str, Any]:
    """Lista arquivos dentro de uma pasta."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "ONE_DRIVE_LIST_FOLDER_CHILDREN",
        {"folder_path": folder_path or "/", "top": max(1, min(999, top)), "use_me_drive": True},
        user_id=user_id,
    )


async def list_drives(**kwargs) -> Dict[str, Any]:
    """Lista drives disponiveis."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call("ONE_DRIVE_LIST_DRIVES", {}, user_id=user_id)