# ADMIN_GUIDE.md — Guia do Módulo Web Admin (30/07/2026)

> Documento operacional para o módulo `/admin/*` do `agents-runtime-test`.
> Fonte autoritativa de pendências: [`STATE.md`](../STATE.md)

## 🔐 Autenticação

Todos os endpoints `/admin/*` exigem **Bearer SA token** ou **Firebase ID token** no header `Authorization`:

```bash
curl -H "Authorization: Bearer $AGENTS_RUNTIME_SA_TOKEN" \
     https://agents-runtime-test-...run.app/admin/agents
```

Sem token válido: HTTP 401/403.

## 📊 Endpoints Read-Only (GET)

| Endpoint | Descrição |
|---|---|
| `/admin/dashboard` | HTML do painel (login + abas) |
| `/health`, `/health` | Health check |
| `/admin/agents` | Lista todos os agentes |
| `/admin/agents/status` | Resumo do status dos agentes |
| `/admin/agents/{id}/status` | Status detalhado de um agente |
| `/admin/agents/{id}` | Agent específico |
| `/admin/skills` | Lista skills |
| `/admin/tools` | Lista tools |
| `/admin/users` | Lista usuários registrados |
| `/admin/users/{phone}` | User específico |
| `/admin/users/{phone}/folder-permissions` | **Lista permissões de pastas do user** (v.30/07/2026) |
| `/admin/groups` | Lista grupos |
| `/admin/accounts` | Lista contas WhatsApp |
| `/admin/accounts/{id}` | Conta específica |
| `/admin/owners` | Lista owners |
| `/admin/knowledge` | Lista docs indexados |
| `/admin/knowledge/search` | Busca semântica |
| `/admin/cache/stats` | Estatísticas de cache |
| `/admin/status` | Status do runtime |

## ✏️ Endpoints Write (POST/PUT/DELETE)

| Endpoint | Verbo | Função |
|---|---|---|
| `/admin/agents` | POST | Criar/atualizar agente |
| `/admin/agents/{id}` | DELETE | Deletar agente |
| `/admin/skills` | POST | Criar/atualizar skill |
| `/admin/tools` | POST | Criar/atualizar tool |
| `/admin/accounts` | POST | Criar conta WhatsApp |
| `/admin/accounts/{id}` | PUT | Atualizar conta |
| `/admin/register-user` | POST | Registrar/atualizar user OAuth |
| `/admin/groups/confirm` | POST | Confirmar membro de grupo |
| `/admin/knowledge` | POST | Adicionar doc à base |
| `/admin/users/{phone}/folder-permissions` | POST | **Conceder permissão** (v.30/07/2026) |
| `/admin/users/{phone}/folder-permissions/{id}` | DELETE | **Revogar permissão** (v.30/07/2026) |
| `/admin/playground` | POST | Playground tools |

## 📁 Folder Permissions (TASK A — 30/07/2026)

Permite conceder/revogar acesso do user a pastas específicas de Calendar/Gmail/GDrive.

### Conceito

Sem folder permissions, o bot usa o token OAuth do user e tem acesso a **TODOS** os dados (drive inteiro, todos emails, todas reuniões). Com folder permissions, o admin pode escopar o acesso.

### Storage

```
usuarios/{phone}/folder_permissions/{permission_id}
{
  permission_id: 'a1b2c3d4...',   # sha1(tool::pattern)[:16], determinístico
  tool: 'drive' | 'gmail' | 'calendar',
  scope: 'whitelist' | 'blacklist',
  pattern: 'folder_id' | 'email_pattern' | '*',
  created_at: '2026-07-30T...',
  created_by: 'admin-sa-token' ou phone,
}
```

### Conceder whitelist (drive, pasta específica)

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool":"drive","pattern":"1AbC...folder_id...","scope":"whitelist"}' \
  https://...run.app/admin/users/+5511966830020/folder-permissions
```

### Conceder blacklist (gmail, padrão de email)

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool":"gmail","pattern":"*@spam.com","scope":"blacklist"}' \
  https://...run.app/admin/users/+5511966830020/folder-permissions
```

### Listar

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://...run.app/admin/users/+5511966830020/folder-permissions
```

### Revogar

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  https://...run.app/admin/users/+5511966830020/folder-permissions/{permission_id}
```

### Runtime enforcement (status)

| Fase | Status |
|---|---|
| Storage + endpoints + tests | ✅ deployado (30/07/2026) |
| Tools filtram results por permissions | 🔴 **pendente** (próxima janela) |

Por enquanto, **conceder/revogar é apenas storage** — as tools (Drive/Gmail/Calendar) não estão checando as permissions antes de retornar resultados. Próxima fase: instrumentar tools para filtrar.

## 🔄 Refresh após write

Todos os endpoints write chamam `force_reload()` para invalidar o cache in-memory. Mudanças são visíveis nos próximos requests sem restart.

## ⚠️ Ferramentas sempre código

> Tools são **read-only no Firestore** — a implementação executável
> continua versionada em código (skill logic fica em `agents_runtime/tools/`).

Tools no Firestore servem apenas de metadata reference (nome, descrição, schema). A lógica real (função Python) vive no código.

## 🛟 Auditoria de mudanças

Toda chamada write gera log estruturado:
- `Agent '{id}' upserted to Firestore`
- `Folder permission granted phone=... tool=... pattern=...`
- `Folder permission revoked phone=... id=...`

Cross-scope attempts (user tentando acessar pasta de outro) geram `CROSS_SCOPE_ATTEMPT` no log.
