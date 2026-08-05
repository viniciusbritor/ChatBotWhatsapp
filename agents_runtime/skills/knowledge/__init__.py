"""Knowledge skills registry.

Each skill encapsulates a single file type or storage target and exposes a
minimal contract:

    MIME_TYPES = ["application/pdf", ...]
    async def extract(envelope) -> dict | None
    async def persist(envelope, extracted, scope) -> dict

The router (`agent_orchestration.knowledge_router.py`) consults this registry
to dispatch an incoming attachment to the appropriate handler.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


SKILLS: Dict[str, Any] = {}


def register_skill(name: str, skill: Any) -> None:
    SKILLS[name] = skill
    logger.debug("knowledge_skill_registered name=%s", name)


def get_skill(name: str) -> Optional[Any]:
    return SKILLS.get(name)


def find_skill_by_mime(mime: str) -> Optional[Any]:
    if not mime:
        return None
    mime_lower = mime.lower()
    for skill in SKILLS.values():
        if mime_lower in getattr(skill, "MIME_TYPES", []):
            return skill
    return None


def list_skills() -> List[str]:
    return sorted(SKILLS.keys())


def _lazy_imports() -> None:
    """Populate the registry on first use (avoids circular imports)."""
    if SKILLS:
        return
    from skills.knowledge import pdf_handler  # noqa: F401
    from skills.knowledge import docx_handler  # noqa: F401
    from skills.knowledge import xlsx_handler  # noqa: F401
    from skills.knowledge import pptx_handler  # noqa: F401
    from skills.knowledge import text_handler  # noqa: F401
    from skills.knowledge import google_drive_saver  # noqa: F401


_lazy_imports()


__all__ = [
    "SKILLS",
    "register_skill",
    "get_skill",
    "find_skill_by_mime",
    "list_skills",
]
