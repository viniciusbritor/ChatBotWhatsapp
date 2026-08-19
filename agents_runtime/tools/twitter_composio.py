"""Twitter/X tools via Composio SDK + Secret Manager.

GUARDRAIL §0.8 (18/08/2026): manager dedicado para Twitter/X via Composio.
Padrao consistente com linkedin_composio / github_composio / notion_composio:
tools wrapped expostas + chamadas via composio_call helper compartilhado.

Tools wrapped (slug Composio -> nome da funcao):
- TWITTER_USER_LOOKUP_ME -> me_profile
- TWITTER_USER_LOOKUP_BY_USERNAMES -> lookup_users
- TWITTER_RECENT_SEARCH -> search_recent
- TWITTER_SEARCH_RECENT_COUNTS -> search_recent_counts
- TWITTER_FULL_ARCHIVE_SEARCH -> search_archive
- TWITTER_POST_LOOKUP_BY_POST_IDS -> lookup_posts
- TWITTER_CREATION_OF_A_POST -> create_post
- TWITTER_UPLOAD_MEDIA -> upload_media
- TWITTER_POST_DELETE_BY_POST_ID -> delete_post
- TWITTER_GET_USERS_BY_IDS -> lookup_users_by_ids (lazy import; se indisponivel, retorna erro)

IMPORTANTE: API v2 do X/Twitter NAO expoe endpoint nativo de trending
topics (foi descontinuado em 11/2024). Trends-by-volume eh implementado
no system_prompt do manager (janela 6h vs 6h anterior via
TWITTER_SEARCH_RECENT_COUNTS), NAO como tool separada.
"""
import logging
from typing import Any, Dict, List, Optional

from tools._composio_common import composio_call

logger = logging.getLogger(__name__)


async def me_profile(**kwargs) -> Dict[str, Any]:
    """Retorna dados do perfil do usuario X autenticado.

    Args:
        phone: Telefone do usuario (per-user Composio user_id).
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_USER_LOOKUP_ME",
        {"user.fields": ["id", "name", "username", "description", "profile_image_url", "public_metrics"]},
        user_id=user_id,
    )


async def lookup_users(usernames: List[str], **kwargs) -> Dict[str, Any]:
    """Busca perfis publicos do X por username (sem o @).

    Args:
        usernames: Lista de usernames (1-100). Ex: ["elonmusk", "sundarpichai"].
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_USER_LOOKUP_BY_USERNAMES",
        {"usernames": usernames[:100]},
        user_id=user_id,
    )


async def search_recent(
    query: str,
    max_results: int = 10,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Busca tweets dos ultimos 7 dias por query (X search syntax).

    Operators uteis: from:user, to:user, lang:pt, -is:retweet, -is:reply,
    has:media, hashtag.

    Args:
        query: Query de busca (max 512 chars).
        max_results: Numero maximo de resultados (min 10, max 100).
        start_time: ISO 8601 (opcional, janela 7d).
        end_time: ISO 8601 (opcional, janela 7d).
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    args: Dict[str, Any] = {
        "query": query,
        "max_results": max(10, min(max_results, 100)),
        "tweet.fields": ["created_at", "public_metrics", "lang", "author_id", "text"],
        "expansions": ["author_id"],
        "user.fields": ["username", "name", "public_metrics"],
    }
    if start_time:
        args["start_time"] = start_time
    if end_time:
        args["end_time"] = end_time
    return await composio_call("TWITTER_RECENT_SEARCH", args, user_id=user_id)


async def search_recent_counts(
    query: str,
    granularity: str = "hour",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Conta tweets matching query por bucket de tempo (para trends-by-volume).

    Args:
        query: Query de busca.
        granularity: 'minute' | 'hour' | 'day' (default 'hour').
        start_time: ISO 8601 (opcional).
        end_time: ISO 8601 (opcional).
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    args: Dict[str, Any] = {
        "query": query,
        "granularity": granularity,
        "search_count.fields": ["end", "start", "tweet_count"],
    }
    if start_time:
        args["start_time"] = start_time
    if end_time:
        args["end_time"] = end_time
    return await composio_call("TWITTER_SEARCH_RECENT_COUNTS", args, user_id=user_id)


async def search_archive(
    query: str,
    start_time: str,
    end_time: str,
    max_results: int = 50,
    **kwargs,
) -> Dict[str, Any]:
    """Busca full archive (requer Academic Research access; pode falhar com 403).

    Args:
        query: Query de busca.
        start_time: ISO 8601 inicio (YYYY-MM-DDTHH:mm:ssZ).
        end_time: ISO 8601 fim.
        max_results: Maximo de resultados (default 50).
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_FULL_ARCHIVE_SEARCH",
        {
            "query": query,
            "start_time": start_time,
            "end_time": end_time,
            "max_results": max(10, min(max_results, 500)),
            "tweet.fields": ["created_at", "public_metrics", "lang", "author_id"],
            "expansions": ["author_id"],
            "user.fields": ["username", "name"],
        },
        user_id=user_id,
    )


async def lookup_posts(post_ids: List[str], **kwargs) -> Dict[str, Any]:
    """Busca tweets por ID (max 100 IDs por chamada).

    Args:
        post_ids: Lista de IDs de tweets.
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_POST_LOOKUP_BY_POST_IDS",
        {
            "ids": post_ids[:100],
            "tweet.fields": ["created_at", "public_metrics", "lang", "text", "author_id"],
            "expansions": ["author_id"],
            "user.fields": ["username", "name"],
        },
        user_id=user_id,
    )


async def create_post(text: str, **kwargs) -> Dict[str, Any]:
    """Cria um tweet (max 280 chars ou X Premium 25k).

    Args:
        text: Texto do tweet (max 280 chars standard; 25000 X Premium).
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_CREATION_OF_A_POST",
        {"text": text[:280]},
        user_id=user_id,
    )


async def upload_media(media_url: str, **kwargs) -> Dict[str, Any]:
    """Upload de midia (imagem) via URL publica.

    Para videos/GIFs grandes, usar initialize_media_upload + append_media_upload
    + get_media_upload_status (chunked). Para simplicidade, esta tool so
    aceita URL publica (imagens).

    Args:
        media_url: URL publica HTTP/HTTPS da imagem.
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_UPLOAD_MEDIA",
        {"media_url": media_url},
        user_id=user_id,
    )


async def delete_post(post_id: str, **kwargs) -> Dict[str, Any]:
    """Deleta um tweet do usuario autenticado (irreversivel).

    Args:
        post_id: ID do tweet a deletar.
        phone: Telefone do usuario.
    """
    user_id = str(kwargs.get("phone", "") or kwargs.get("user_id", ""))
    return await composio_call(
        "TWITTER_POST_DELETE_BY_POST_ID",
        {"id": post_id},
        user_id=user_id,
    )
