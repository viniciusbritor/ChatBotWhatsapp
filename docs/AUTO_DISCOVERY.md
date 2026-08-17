# Auto-Discovery Architecture (Refactor 17/08/2026)

## Contexto

Antes deste refactor, existiam **2 padrões conflitantes** para gerenciar tools:

1. **Padrão A — DeepAgent Manager**: managers hardcoded (calendar, email, drive, group-rag, web, jennifier) com tools wrapped via `@tool` decorator
2. **Padrão B — Tool Registry Legacy**: `tool_registry.py` monolítico com ~80 tools registradas, usado por `chat_with_tools` (legacy deprecated)

**Problema:** Tools do Composio (LinkedIn, YouTube, GitHub, etc) existiam no Padrão B mas NUNCA eram chamadas porque o orchestrator usava o Padrão A. Resultado: user perguntava "busque meu perfil no linkedin" → Jennifer respondia genericamente.

**Solução:** Auto-discovery unificado (Opção C2 — Allowlist) que cobre **Google APIs + Composio toolkits** com gate de segurança via `ALLOWED_TOOLKITS` hardcoded.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                  tools/api_registry.py                        │
│                  ApiRegistry (singleton)                      │
│                                                              │
│   discover_all() (no startup):                              │
│     1. _discover_google_apis() → from GOOGLE_SERVICES     │
│     2. _discover_composio_toolkits() → SDK auth_configs    │
│                                                              │
│   is_allowed(slug) → ALLOWED_TOOLKITS + EMERGENCY_DISABLE  │
│   get_meta(slug) → retorna ApiMeta se permitido               │
│   list_all() → apenas toolkits permitidos                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      deepagent_layer/dynamic_manager_factory.py             │
│      DynamicManagerFactory (singleton)                       │
│                                                              │
│   get_or_create(slug) →                                      │
│     1. Check allowlist (api_registry.is_allowed)            │
│     2. Cache hit (LRU 100)                                  │
│     3. Importa tools/<slug>_composio.py dinamicamente       │
│     4. Wrap tools via StructuredTool.from_function()        │
│     5. Constroi DeepAgent template-based (B1)                │
│                                                              │
│   on_failure → retorna None → orchestrator usa fallback    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              orchestrator.py (T mão 1)                     │
│                                                              │
│   _detect_dynamic_toolkit(text) → keyword → slug            │
│   if slug: dynamic_factory.get_or_create(slug)             │
│     → se sucesso: executa manager                            │
│     → se None: Jennifer explica "toolkit nao configurado"    │
└─────────────────────────────────────────────────────────────┘
```

## Camadas de Segurança

### 1. ALLOWED_TOOLKITS (hardcoded, git review)

```python
# tools/api_registry.py
ALLOWED_TOOLKITS: Set[str] = {
    # Google APIs (OAuth per-user)
    "calendar", "gmail", "drive", "people", "tasks", "maps",
    # Composio toolkits (user_id via SDK)
    "linkedin", "youtube", "github", "notion",
    "onedrive", "googledocs", "googlesheets", "microsoft_teams",
}
```

Para liberar novo toolkit: editar esta lista, git commit, deploy.

### 2. EMERGENCY_DISABLE_TOOLKITS (env var, kill switch)

```bash
EMERGENCY_DISABLE_TOOLKITS=linkedin,github
```

Bloqueia toolkit mesmo se esta na allowlist. Usado em incidente.

### 3. Rate Limiter (toolkit_rate_limiter.py)

Limite padrao: **100 chamadas/hora/user/toolkit**. Retorna erro amigavel se exceder.

### 4. Audit Log

Toda chamada de tool emite log estruturado:
```python
logger.info(
    "dynamic_tool_call slug=%s tool=%s phone=%s",
    slug, name, phone,
    extra={
        "event_name": "dynamic_tool_call",
        "slug": slug, "tool": name, "phone": phone,
    },
)
```

## Workflow: Adicionar Novo Toolkit

### 1. Implementar tools/X_composio.py

```python
# tools/twitter_composio.py
async def my_profile(phone: str) -> Dict[str, Any]:
    """Retorna perfil do Twitter/X do usuario."""
    return await _composio_call("TWITTER_GET_USER_PROFILE", {}, user_id=phone)

async def post_tweet(text: str, phone: str) -> Dict[str, Any]:
    """Posta um tweet."""
    return await _composio_call("TWITTER_CREATE_TWEET", {"text": text[:280]}, user_id=phone)
```

### 2. Adicionar slug em ALLOWED_TOOLKITS

```python
# tools/api_registry.py
ALLOWED_TOOLKITS: Set[str] = {
    ...
    "twitter",  # <-- adicionar
}
```

### 3. Adicionar keyword em orchestrator.py

```python
# orchestrator.py
_KEYWORD_TO_TOOLKIT: Dict[str, str] = {
    ...
    "twitter": "twitter",  # <-- adicionar
    "tweet": "twitter",
}
```

### 4. (Opcional) Adicionar pin em tools/_composio_common.py

```python
TOOLKIT_VERSIONS = {
    ...
    "twitter": "20260901_00",  # <-- adicionar
}
```

### 5. Git commit + Deploy

```bash
git add tools/twitter_composio.py tools/api_registry.py orchestrator.py
git commit -m "feat(composio): add twitter toolkit"
git push origin test
```

## Comportamento de User

### Quando user pede algo usando toolkit APROVADO

```
User: "busque meu perfil no linkedin"
  ↓
orchestrator._detect_dynamic_toolkit() → "linkedin"
  ↓
api_registry.is_allowed("linkedin") → True (em ALLOWED_TOOLKITS)
  ↓
dynamic_factory.get_or_create("linkedin")
  → Cache miss
  → Importa tools.linkedin_composio
  → Encontra 4 funcoes: my_profile, create_post, read_post, create_article
  → Wraps em StructuredTool
  → Constroi DeepAgent (system_prompt template + 4 tools)
  → Cache set
  ↓
Executa DeepAgent → LLM escolhe my_profile → Composio SDK → LinkedIn API
  ↓
Resposta formatada enviada para user
```

### Quando user pede algo usando toolkit NAO APROVADO

```
User: "poste 'oi' no twitter"
  ↓
orchestrator._detect_dynamic_toolkit() → "twitter"
  ↓
api_registry.is_allowed("twitter") → False (NAO esta em ALLOWED_TOOLKITS)
  ↓
dynamic_factory.get_or_create("twitter") → retorna None
  ↓
orchestrator retorna mensagem amigavel:
  "⚠️ O toolkit 'twitter' nao esta disponivel.
   Pode ser que ele nao esteja na allowlist
   (tools/api_registry.py::ALLOWED_TOOLKITS)."
```

## Comportamento de Admin

### Ver toolkits disponiveis

```python
from tools.api_registry import api_registry
import asyncio
asyncio.run(api_registry.discover_all())
api_registry.list_allowed_slugs()
# ['calendar', 'drive', 'github', 'gmail', 'googledocs', 'googlesheets',
#  'linkedin', 'maps', 'microsoft_teams', 'notion', 'onedrive',
#  'people', 'tasks', 'youtube']
```

### Bloquear toolkit em emergencia (sem deploy)

```bash
# Adicionar ao .env ou secret manager
EMERGENCY_DISABLE_TOOLKITS=linkedin,youtube
```

### Limpar cache apos deploy

```python
from deepagent_layer.dynamic_manager_factory import dynamic_factory
dynamic_factory.clear_cache()
```

Forcar rebuild de todos os managers.

## Migration Path (do tool_registry.py para api_registry)

O `tool_registry.py` foi marcado como **DEPRECATED** mas mantido para compatibilidade. Tests legacy continuam passando.

Proximas fases de migration:
1. `scripts/sync_tools_to_firestore.py` → usar `api_registry.list_all()` + Firestore
2. Portal Admin UI → listar tools via `api_registry.list_allowed_slugs()`
3. tool_registry.py fica apenas para `sync_tools_to_firestore` + tests legacy

## Comparacao: Antes vs. Depois

| Aspecto | Antes (Padrão B) | Depois (Padrão A com Auto-Discovery) |
|---|---|---|
| Tools Composio | Nunca chamadas | Auto-discovery via registry |
| Adicionar toolkit | Editar 5+ arquivos | Editar 2-3 arquivos |
| Segurança | Manual (código) | Allowlist + emergency disable |
| Audit | Logs básicos | Structured logs + rate limit |
| Cache | Nenhum | LRU 100 managers |
| Latência | N/A (não funcionava) | ~1s (1ª vez) / cached |

## Testes

- `tests/test_api_registry.py` — 10 testes (allowlist, discovery, emergency)
- `tests/test_dynamic_manager_factory.py` — 10 testes (cache, LRU, wrap, kill switch)

Suite completa: **1314 tests passing** (06/08/2026)
