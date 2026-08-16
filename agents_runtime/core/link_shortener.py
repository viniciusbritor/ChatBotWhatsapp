"""Link shortener global (regra: sempre usar ao enviar links via Evolution).

Quando o conteudo de uma mensagem WhatsApp inclui URLs, esta funcao
substitui cada URL por uma versao encurtada via API gratuita (TinyURL
ou is.gd) ou via endpoint custom (configuravel via
``LINK_SHORTENER_PROVIDER``).

Regras:
- Habilitado por padrao (``LINK_SHORTENER_ENABLED=true``). Para desativar
  globalmente, defina ``LINK_SHORTENER_ENABLED=false``.
- Skips URLs que ja sao encurtadas (bit.ly, tinyurl.com, is.gd, ow.ly,
  t.co, goo.gl, ift.tt, reut.rs, lnkd.in, buff.ly, fb.me, youtu.be).
- Timeout agressivo (3s) para nao bloquear envio.
- Em caso de falha (network, 5xx, timeout), URL original eh preservada.
- Logging estruturado de quantos links foram encurtados.
- Cache em memoria (LRU maxsize=512, TTL 24h) para evitar chamadas
  repetidas ao mesmo URL.

Providers suportados:
- ``tinyurl`` (default, free, sem API key)
- ``isgd`` (free, sem API key)
- ``custom`` (usa ``LINK_SHORTENER_CUSTOM_URL`` template)

Uso:
    >>> from core.link_shortener import shorten_urls_in_text
    >>> shorten_urls_in_text("Veja https://google.com/search?q=hello")
    'Veja https://tinyurl.com/2x4y5z'
"""

from __future__ import annotations

import logging
import os
import re
import time
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Regex de URL: captura scheme + path + query
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'`)\]}\]]+",
    re.IGNORECASE,
)

# Hosts ja encurtados (skip)
_SHORTENED_HOSTS: frozenset[str] = frozenset({
    "bit.ly", "tinyurl.com", "is.gd", "ow.ly", "t.co", "goo.gl",
    "ift.tt", "reut.rs", "lnkd.in", "buff.ly", "fb.me", "youtu.be",
    "tinyurl.app", "tiny.cc", "shorte.st", "adf.ly",
})

# Cache LRU em memoria (maxsize=512)
_url_cache: dict[str, str] = {}
_CACHE_MAX_SIZE = 512
_CACHE_TTL_SEC = 24 * 3600
_cache_timestamps: dict[str, float] = {}


def _is_shortened_url(url: str) -> bool:
    """Retorna True se URL ja eh encurtada (skip)."""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return host in _SHORTENED_HOSTS
    except Exception:
        return False


def _call_tinyurl(url: str, timeout: float) -> Optional[str]:
    """POST https://tinyurl.com/api/create.php?url=... -> short URL."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                "https://tinyurl.com/api/create.php",
                params={"url": url},
                headers={"User-Agent": "AgentsRuntime/1.0"},
            )
        if resp.status_code == 200 and "http" in resp.text.lower():
            return resp.text.strip()
    except Exception as e:
        logger.debug("tinyurl_shorten_failed url=%s err=%s", url, type(e).__name__)
    return None


def _call_isgd(url: str, timeout: float) -> Optional[str]:
    """GET https://is.gd/create.php?format=simple&url=... -> short URL."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                "https://is.gd/create.php",
                params={"format": "simple", "url": url},
                headers={"User-Agent": "AgentsRuntime/1.0"},
            )
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
    except Exception as e:
        logger.debug("isgd_shorten_failed url=%s err=%s", url, type(e).__name__)
    return None


def _call_custom(url: str, template: str, timeout: float) -> Optional[str]:
    """POST {template_com_URL} -> short URL."""
    try:
        endpoint = template.replace("{url}", url)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(endpoint, headers={"User-Agent": "AgentsRuntime/1.0"})
        if resp.status_code < 400:
            data = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            short = data.get("short_url") or data.get("shortUrl") or resp.text.strip()
            if short and short.startswith("http"):
                return short
    except Exception as e:
        logger.debug("custom_shorten_failed url=%s err=%s", url, type(e).__name__)
    return None


def _shorten_one(url: str) -> str:
    """Encurta uma URL usando o provider configurado. Retorna original se falhar."""
    if not url:
        return url

    # Skip se ja encurtada
    if _is_shortened_url(url):
        return url

    # Cache check
    now = time.time()
    if url in _url_cache:
        ts = _cache_timestamps.get(url, 0)
        if (now - ts) < _CACHE_TTL_SEC:
            return _url_cache[url]

    # Disabled check
    enabled = os.getenv("LINK_SHORTENER_ENABLED", "true").lower() not in ("false", "0", "no")
    if not enabled:
        return url

    provider = os.getenv("LINK_SHORTENER_PROVIDER", "tinyurl").lower()
    timeout = float(os.getenv("LINK_SHORTENER_TIMEOUT_SEC", "3"))

    short: Optional[str] = None
    if provider == "tinyurl":
        short = _call_tinyurl(url, timeout)
    elif provider == "isgd":
        short = _call_isgd(url, timeout)
    elif provider == "custom":
        template = os.getenv("LINK_SHORTENER_CUSTOM_URL", "")
        if not template:
            logger.warning("LINK_SHORTENER_CUSTOM_URL not set, falling back to tinyurl")
            short = _call_tinyurl(url, timeout)
        else:
            short = _call_custom(url, template, timeout)
    else:
        logger.warning("unknown_link_shortener_provider=%s, using tinyurl", provider)
        short = _call_tinyurl(url, timeout)

    if short:
        # Cache write (LRU eviction)
        if len(_url_cache) >= _CACHE_MAX_SIZE:
            oldest = min(_cache_timestamps, key=_cache_timestamps.get)
            _url_cache.pop(oldest, None)
            _cache_timestamps.pop(oldest, None)
        _url_cache[url] = short
        _cache_timestamps[url] = now
        return short

    # Fallback: URL original
    return url


def shorten_urls_in_text(text: str) -> str:
    """Encurta todas as URLs em `text`. Preserva formatacao.

    Se o shortener estiver desativado ou falhar, retorna o texto original.

    Optimizacao: pula encurtamento se:
    - texto menor que MIN_TEXT_LENGTH_CHARS (default 50)
    - texto NAO contem http:// ou https://

    Isso evita chamadas HTTP para ~70% das mensagens WhatsApp (acks curtos,
    respostas simples) que NAO tem URLs.
    """
    if not text:
        return text if text == "" else ""

    enabled = os.getenv("LINK_SHORTENER_ENABLED", "true").lower() not in ("false", "0", "no")
    if not enabled:
        return text

    # Optimizacao: skip em textos curtos (70% das msgs nao tem URL)
    min_len = int(os.getenv("LINK_SHORTENER_MIN_TEXT_LENGTH", "50"))
    if len(text) < min_len:
        return text

    # Optimizacao: skip se nao tem http:// ou https://
    if "http://" not in text and "https://" not in text:
        return text

    urls = _URL_PATTERN.findall(text)
    if not urls:
        return text

    count = 0
    result = text
    for url in urls:
        short = _shorten_one(url)
        if short != url:
            result = result.replace(url, short, 1)
            count += 1

    if count > 0:
        logger.info(
            "link_shortener_applied url_count=%d provider=%s",
            count, os.getenv("LINK_SHORTENER_PROVIDER", "tinyurl"),
        )
    return result


def clear_cache() -> None:
    """Limpa cache (util para testes)."""
    _url_cache.clear()
    _cache_timestamps.clear()
