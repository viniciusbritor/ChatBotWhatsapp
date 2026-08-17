"""DynamicManagerFactory - Constroi DeepAgents sob demanda para toolkits auto-descobertos.

GUARDRAIL (17/08/2026): auto-discovery funciona em 3 camadas:
1. ApiRegistry descobre metadados
2. Allowlist hardcoded filtra o que pode ser usado
3. DynamicManagerFactory constroi DeepAgent template-based (B1)

Para adicionar novo toolkit:
- Implementar tools/X_composio.py (composio) ou ja existe tools/google_X.py
- Adicionar slug em tools/api_registry.py::ALLOWED_TOOLKITS
- Factory descobre automaticamente via registry
"""
import importlib
import inspect
import logging
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import BaseTool, StructuredTool

from tools.api_registry import api_registry, ApiMeta

logger = logging.getLogger(__name__)

# LRU cache: maximo de managers em memoria
_MAX_CACHE_SIZE = 100


def _discover_async_funcs(module) -> List[Callable]:
    """Descobre funcoes async publicas de um modulo."""
    funcs = []
    for name, obj in inspect.getmembers(module):
        if inspect.iscoroutinefunction(obj) and not name.startswith("_"):
            funcs.append((name, obj))
    return funcs


def _build_system_prompt(meta: ApiMeta) -> str:
    """Template deterministico de system prompt baseado nos metadados."""
    return (
        f"Voce e o especialista em {meta.name} ({meta.category}) da Jennifer. "
        f"{meta.description}. "
        f"Use as tools disponiveis para executar as acoes do usuario. "
        f"Se o usuario pedir algo fora do escopo desta integracao, "
        f"reporte educadamente que essa ferramenta nao pode fazer isso. "
        f"Responda em portugues brasileiro natural e amigavel."
    )


def _make_async_tool(name: str, coroutine_fn: Callable, doc: str, slug: str) -> BaseTool:
    """Cria LangChain BaseTool a partir de uma funcao async.

    Usa StructuredTool.from_function() para suportar funcoes async
    sem docstring (geramos automaticamente).
    """

    async def wrapper(**kwargs) -> Any:
        # GUARDRAIL (17/08/2026): rate limit por toolkit+phone
        from tools.toolkit_rate_limiter import toolkit_rate_limiter
        phone = kwargs.get("phone", "")
        if not toolkit_rate_limiter.check(slug, phone):
            return {
                "error": "toolkit_rate_limit_exceeded",
                "toolkit": slug,
                "tool": name,
                "limit_per_hour": 100,
                "retry_after_seconds": 3600,
            }
        logger.info(
            "dynamic_tool_call slug=%s tool=%s",
            slug, name,
            extra={
                "event_name": "dynamic_tool_call",
                "slug": slug,
                "tool": name,
                "phone": phone,
            },
        )
        return await coroutine_fn(**kwargs)

    # StructuredTool supports async functions e generics.
    # docstring pode ser None para functions async — StructuredTool aceita.
    wrapper.__doc__ = doc
    wrapper.__name__ = name
    return StructuredTool.from_function(
        coroutine=wrapper,
        name=f"{slug}.{name}",
        description=doc,
    )


class DynamicManagerFactory:
    """Constroi e cacheia managers dinamicos baseado no ApiRegistry."""

    def __init__(self):
        self._cache: "OrderedDict[str, Any]" = OrderedDict()
        self._agent_builders: Dict[str, Callable] = {}

    def get_or_create(self, toolkit_slug: str):
        """Retorna manager existente ou constroi novo.

        Retorna None se:
        - slug nao esta na allowlist
        - tool module nao existe (tools/X_composio.py)
        - build falhou
        """
        # 1. Check allowlist (kill switch automatico)
        if not api_registry.is_allowed(toolkit_slug):
            logger.warning("dynamic_manager_blocked slug=%s reason=not_allowed", toolkit_slug)
            return None

        # 2. Cache hit
        if toolkit_slug in self._cache:
            self._cache.move_to_end(toolkit_slug)
            logger.debug("dynamic_manager_cache_hit slug=%s", toolkit_slug)
            return self._cache[toolkit_slug]

        # 3. Get metadata
        meta = api_registry.get_meta(toolkit_slug)
        if not meta:
            logger.warning("dynamic_manager_no_meta slug=%s", toolkit_slug)
            return None

        # 4. Import module (lazy import)
        try:
            module = importlib.import_module(meta.module_path)
        except ImportError as exc:
            logger.warning(
                "dynamic_manager_module_missing slug=%s module=%s exc=%s",
                toolkit_slug, meta.module_path, exc,
            )
            return None

        # 5. Build tools wrapped
        tools = self._build_tools(meta, module)
        if not tools:
            logger.warning("dynamic_manager_no_tools slug=%s", toolkit_slug)
            return None

        # 6. Build system prompt
        system_prompt = _build_system_prompt(meta)

        # 7. Build DeepAgent
        try:
            agent = self._build_agent(system_prompt, tools)
            if agent:
                self._cache[toolkit_slug] = agent
                self._evict_if_needed()
                logger.info(
                    "dynamic_manager_built slug=%s tools=%d category=%s",
                    toolkit_slug, len(tools), meta.category,
                )
                return agent
        except Exception as exc:
            logger.exception("dynamic_manager_build_failed slug=%s: %s", toolkit_slug, exc)
            return None
        return None

    def _build_tools(self, meta: ApiMeta, module) -> List[Any]:
        """Constroi LangChain tools wrapped a partir do modulo de tools."""
        funcs = _discover_async_funcs(module)
        if not funcs:
            return []
        wrapped = []
        for name, func in funcs:
            try:
                doc = (func.__doc__ or f"Executa {name} no toolkit {meta.slug}.").strip()
                wrapped_tool = _make_async_tool(name, func, doc, meta.slug)
                wrapped.append(wrapped_tool)
            except Exception as exc:
                logger.warning(
                    "dynamic_manager_wrap_failed slug=%s tool=%s exc=%s",
                    meta.slug, name, exc,
                )
        return wrapped

    def _build_agent(self, system_prompt: str, tools: List[Any]):
        """Constroi DeepAgent (LangChain)."""
        try:
            from deepagents import create_deep_agent
            from deepagent_layer.agents import _build_model
            model = _build_model()
            return create_deep_agent(
                model=model,
                system_prompt=system_prompt,
                tools=tools,
            )
        except ImportError:
            logger.warning("deepagents_not_available_skipping_dynamic_manager")
            return None
        except Exception as exc:
            logger.exception("deep_agent_build_failed: %s", exc)
            return None

    def _evict_if_needed(self):
        """LRU eviction."""
        while len(self._cache) > _MAX_CACHE_SIZE:
            self._cache.popitem(last=False)

    def invalidate(self, toolkit_slug: str) -> bool:
        """Invalida cache para um toolkit (usado apos EMERGENCY_DISABLE)."""
        if toolkit_slug in self._cache:
            del self._cache[toolkit_slug]
            logger.info("dynamic_manager_cache_invalidated slug=%s", toolkit_slug)
            return True
        return False

    def clear_cache(self):
        """Limpa todo o cache."""
        n = len(self._cache)
        self._cache.clear()
        logger.info("dynamic_manager_cache_cleared count=%d", n)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatisticas do cache."""
        return {
            "size": len(self._cache),
            "max_size": _MAX_CACHE_SIZE,
            "cached_slugs": list(self._cache.keys()),
        }


# Singleton global
dynamic_factory = DynamicManagerFactory()