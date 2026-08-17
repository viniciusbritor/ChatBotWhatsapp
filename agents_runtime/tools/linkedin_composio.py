"""LinkedIn tools via Composio SDK + Secret Manager.

GUARDRAIL §0.8 (17/08/2026): refatorado para usar helper compartilhado
`tools._composio_common.composio_call` que extrai o data real corretamente
do envelope Composio.

Tools wrapped:
- my_profile        -> LINKEDIN_GET_MY_INFO
- create_post       -> LINKEDIN_CREATE_LINKED_IN_POST
- read_post         -> LINKEDIN_GET_POST_CONTENT
- create_article    -> LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE
"""
import logging
from typing import Any, Dict, List, Optional

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)

_AUTHOR_URN_CACHE: Dict[str, str] = {}


async def _resolve_author_urn(user_id: str) -> str:
    """Resolve o URN do autor (urn:li:person:xxx) uma vez e cacheia."""
    cached = _AUTHOR_URN_CACHE.get(user_id)
    if cached:
        return cached
    profile = await my_profile(phone=user_id)
    person_id = profile.get("id") if isinstance(profile, dict) else None
    if person_id:
        urn = f"urn:li:person:{person_id}"
        _AUTHOR_URN_CACHE[user_id] = urn
        return urn
    return ""


async def create_post(
    text: str,
    visibility: str = "PUBLIC",
    images: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Cria post no LinkedIn."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    author = await _resolve_author_urn(user_id)
    if not author:
        return {"error": "linkedin_author_urn_resolution_failed"}
    return await composio_call(
        "LINKEDIN_CREATE_LINKED_IN_POST",
        {"author": author, "commentary": text[:3000], "visibility": visibility, "images": images or []},
        user_id=user_id,
    )


async def read_post(post_id: str, **kwargs) -> Dict[str, Any]:
    """Le o conteudo de um post por ID."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "LINKEDIN_GET_POST_CONTENT",
        {"post_id": post_id},
        user_id=user_id,
    )


async def my_profile(**kwargs) -> Dict[str, Any]:
    """Retorna dados do perfil LinkedIn do usuario autenticado."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call("LINKEDIN_GET_MY_INFO", {}, user_id=user_id)


async def create_article(
    text: str,
    title: str = "",
    url: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Cria artigo ou compartilha URL no LinkedIn."""
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    author = await _resolve_author_urn(user_id)
    if not author:
        return {"error": "linkedin_author_urn_resolution_failed"}
    if url:
        share = {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "originalUrl": url[:500],
                    "title": {"text": title[:200] or text[:100]},
                    "status": "READY",
                }],
            }
        }
    else:
        share = {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
                "media": [],
            }
        }
    return await composio_call(
        "LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE",
        {"author": author, "visibility": "PUBLIC", "specificContent": share},
        user_id=user_id,
    )