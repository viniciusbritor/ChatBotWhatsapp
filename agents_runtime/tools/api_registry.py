"""ApiRegistry - Auto-discovery unificado para Google APIs e Composio toolkits.

GUARDRAIL (17/08/2026): auto-discovery funciona em 3 camadas:
1. Descobre metadados de Google APIs (via GOOGLE_SERVICES) e Composio toolkits (via SDK).
2. Filtra por ALLOWED_TOOLKITS hardcoded (git review).
3. Expõe API unificada para factory construir managers dinamicamente.

Para adicionar novo toolkit: editar ALLOWED_TOOLKITS + git commit + deploy.
"""
import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ApiMeta:
    """Metadados de uma API ou toolkit."""
    slug: str
    name: str
    category: str  # "google" | "composio"
    description: str
    auth_type: str  # "oauth_per_user" | "api_key" | "composio_user_id"
    module_path: str = ""  # caminho do módulo de tools (ex: "tools.linkedin_composio")
    scopes: List[str] = field(default_factory=list)
    version: str = "latest"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ALLOWED_TOOLKITS - lista hardcoded revisada por git.
# Para liberar novo toolkit: adicionar aqui, git commit, deploy.
# EMERGENCY: variavel de ambiente EMERGENCY_DISABLE_TOOLKITS para bloquear mesmo se na allowlist.
ALLOWED_TOOLKITS: Set[str] = {
    # Google APIs (OAuth per-user)
    "calendar",
    "gmail",
    "drive",
    "people",
    "tasks",
    # Google Maps (API key)
    "maps",
    # Composio toolkits (user_id via SDK)
    "linkedin",
    "youtube",
    "github",
    "notion",
    "onedrive",
    "googledocs",
    "googlesheets",
    "googlemeet",
    "microsoft_teams",
    "msteams",
}


def _get_emergency_disable_set() -> Set[str]:
    """Le variavel de ambiente para kill switch de emergencia."""
    raw = os.getenv("EMERGENCY_DISABLE_TOOLKITS", "").strip()
    if not raw:
        return set()
    return {slug.strip() for slug in raw.split(",") if slug.strip()}


class ApiRegistry:
    """Registry dinâmico com auto-discovery de Google APIs e Composio."""

    def __init__(self):
        self._google_apis: Dict[str, ApiMeta] = {}
        self._composio_toolkits: Dict[str, ApiMeta] = {}
        self._discovered = False
        self._lock = asyncio.Lock()

    async def discover_all(self) -> None:
        """Descobre todas as APIs/toolkits disponíveis."""
        async with self._lock:
            if self._discovered:
                return
            self._discover_google_apis()
            await self._discover_composio_toolkits()
            self._discovered = True
            logger.info(
                "api_registry_discovered google=%d composio=%d allowed=%d",
                len(self._google_apis), len(self._composio_toolkits), len(ALLOWED_TOOLKITS),
            )

    def _discover_google_apis(self) -> None:
        """Descobre Google APIs a partir de GOOGLE_SERVICES (core.google_scopes)."""
        try:
            from core.google_scopes import GOOGLE_SERVICES, ALL_OAUTH_SCOPES
            scope_str = " ".join(ALL_OAUTH_SCOPES)
            for svc in GOOGLE_SERVICES:
                slug = svc["id"]
                module_map = {
                    "calendar": "tools.google_calendar",
                    "gmail": "tools.google_gmail",
                    "drive": "tools.google_drive",
                    "people": "tools.google_people",
                    "tasks": "tools.google_tasks",
                }
                self._google_apis[slug] = ApiMeta(
                    slug=slug,
                    name=svc["label"],
                    category="google",
                    description=f"{svc['label']} (Google API)",
                    auth_type="oauth_per_user",
                    module_path=module_map.get(slug, f"tools.google_{slug}"),
                    scopes=[s for s in ALL_OAUTH_SCOPES if svc["scope"] in s],
                    version="v1",
                )
            # Maps usa API key, nao OAuth
            self._google_apis["maps"] = ApiMeta(
                slug="maps",
                name="Google Maps",
                category="google",
                description="Google Maps API (rotas, geocoding, places)",
                auth_type="api_key",
                module_path="tools.locomotion",
                scopes=[],
                version="v1",
            )
        except Exception as exc:
            logger.warning("google_apis_discovery_failed: %s", exc)

    async def _discover_composio_toolkits(self) -> None:
        """Descobre toolkits Composio via SDK."""
        try:
            from tools._composio_common import TOOLKIT_VERSIONS
            api_key = await asyncio.to_thread(self._get_composio_api_key)
            if not api_key:
                logger.warning("composio_api_key_missing_skipping_discovery")
                return
            from composio import Composio
            client = Composio(api_key=api_key)
            configs = await asyncio.to_thread(client.auth_configs.list)
            for cfg in configs.items:
                slug = cfg.toolkit.slug
                module_path = f"tools.{slug.replace('-', '_').replace(' ', '_')}_composio"
                self._composio_toolkits[slug] = ApiMeta(
                    slug=slug,
                    name=getattr(cfg, "name", slug),
                    category="composio",
                    description=f"{getattr(cfg, 'name', slug)} via Composio",
                    auth_type="composio_user_id",
                    module_path=module_path,
                    scopes=[],
                    version=TOOLKIT_VERSIONS.get(slug, "latest"),
                )
        except ImportError:
            logger.warning("composio_sdk_missing_skipping_discovery")
        except Exception as exc:
            logger.warning("composio_discovery_failed: %s", exc)

    @staticmethod
    def _get_composio_api_key() -> str:
        """Carrega COMPOSIO_API_KEY do Secret Manager."""
        global _cached_composio_key
        if _cached_composio_key:
            return _cached_composio_key
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            project = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
            name = f"projects/{project}/secrets/COMPOSIO_API_KEY/versions/latest"
            response = client.access_secret_version(request={"name": name})
            _cached_composio_key = response.payload.data.decode("utf-8-sig").strip()
            return _cached_composio_key
        except Exception:
            return (os.getenv("COMPOSIO_API_KEY", "") or "").strip()

    def is_allowed(self, slug: str) -> bool:
        """True se o toolkit esta na allowlist E NAO esta em emergency disable."""
        if slug not in ALLOWED_TOOLKITS:
            return False
        if slug in _get_emergency_disable_set():
            return False
        return True

    def get_meta(self, slug: str) -> Optional[ApiMeta]:
        """Retorna metadados de uma API/toolkit (se permitido).

        Se a discovery nunca rodou (ou falhou), tenta fazer discovery lazy
        para evitar que o sistema fique quebrado por bug de startup.
        """
        if not self._discovered:
            logger.warning(
                "api_registry_not_discovered_lazy_retry slug=%s",
                slug,
            )
            try:
                # NUNCA chamar asyncio.run() com um event loop ativo
                # (RuntimeError "asyncio.run() cannot be called from a
                # running event loop"). Se ha loop rodando, agenda a
                # discovery em background; senao, roda sincronamente.
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.create_task(self.discover_all())
                else:
                    asyncio.run(self.discover_all())
            except Exception as exc:
                logger.warning("api_registry_lazy_retry_failed: %s", exc)
        meta = self._google_apis.get(slug) or self._composio_toolkits.get(slug)
        if meta and self.is_allowed(slug):
            return meta
        return None

    def list_all(self) -> List[ApiMeta]:
        """Lista todas as APIs/toolkits (apenas as permitidas)."""
        all_metas = list(self._google_apis.values()) + list(self._composio_toolkits.values())
        return [m for m in all_metas if self.is_allowed(m.slug)]

    def list_allowed_slugs(self) -> List[str]:
        """Lista slugs permitidos (para admin UI)."""
        return sorted(ALLOWED_TOOLKITS)


# Singleton global
api_registry = ApiRegistry()

# Cache de API key (memoria)
_cached_composio_key = None