# Portal Fixes — `coherence-portal`

> **Escopo:** este doc lista correções que precisam ser aplicadas no frontend
> do `coherence-portal` (repo separado, não incluido neste repo). Cada item
> identifica o sintoma, a causa raiz e a correção sugerida.
>
> **Por que essas correções:** a UI do módulo "Agents Omnichannel" no Portal
> abre `https://agents-runtime-test-...run.app/?token=<jwt>` e renderiza
> o HTML servido por `core/module_ui.render_dashboard()`. Ao observar a
> renderizacao em 25/07/2026, foram identificados 3 problemas visuais que
> poluem a UI mas nao impedem o funcionamento.

---

## 1. Header mostra `commit <build-id>` em vez do commit SHA curto

**Sintoma:** no canto superior direito do modulo, aparece:
```
commit 0621113e-cadc-46c6-9dfa-b596dec9302e · deployed local
```
O valor `0621113e-cadc-46c6-9dfa-b596dec9302e` e o **build ID** do Cloud Build
(uuid do recurso), nao o SHA do commit git. Para o usuario isso e ruido
inutil.

**Causa raiz:** o backend do agents-runtime passa `COMMIT_SHA` para
`render_dashboard(commit, deployed_at, ...)`. O `COMMIT_SHA` no
`cloudbuild-test.yaml` e resolvido para `$BUILD_ID` (variavel do Cloud Build,
linha 44: `--set-env-vars=...,COMMIT_SHA=$BUILD_ID,...`). O correto seria
resolver para `$REVISION_ID` ou `$SHORT_SHA` (variaveis de Cloud Build
disponiveis em https://cloud.google.com/build/docs/configuring-builds/substitute-variable).

**Correcao:** editar `agents_runtime/cloudbuild-test.yaml:44`:

```yaml
# Antes
COMMIT_SHA=$BUILD_ID

# Depois
COMMIT_SHA=$SHORT_SHA
```

`SHORT_SHA` (7 chars) e o padrao git; `$REVISION_ID` retorna o SHA completo.

**Validacao:** apos redeploy, o header do modulo no Portal deve mostrar
`commit 50434c5` (ou similar) em vez de `commit 0621113e-cadc-46c6-...`.

---

## 2. Header mostra `deployed local` em vez de data de deploy

**Sintoma:** mesmo lugar do item 1:
```
commit 0621113e-cadc-46c6-9dfa-b596dec9302e · deployed local
```
A string `local` e literal do template `core/module_ui.py` quando a env
var `DEPLOYED_AT` nao foi setada.

**Causa raiz:** o backend do agents-runtime define `DEPLOYED_AT = os.getenv("DEPLOYED_AT", "local")`
em `main.py`. O `cloudbuild-test.yaml` nao injeta essa env var, entao o
runtime cai no default "local".

**Correcao:** editar `agents_runtime/cloudbuild-test.yaml:44` para incluir
`DEPLOYED_AT=$_DEPLOYED_AT` e adicionar uma linha de substitution que
resolva essa variavel:

```yaml
# No set-env-vars:
DEPLOYED_AT=$_DEPLOYED_AT

# Adicionar em substitutions (no inicio do yaml):
substitutions:
  _DEPLOYED_AT: "${BUILD_ID}"
```

OU injetar uma expressao data fixa:

```yaml
DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

**Validacao:** apos redeploy, o header deve mostrar `deployed 2026-07-25T06:03:45Z`
(ou similar) em vez de `deployed local`.

---

## 3. `auth_token` do bearer e exposto no JavaScript do modulo

**Sintoma:** o template `core/module_ui.py:99` referencia `AUTH`, que e
uma variavel JavaScript populada pelo backend runtime com o token Bearer
recebido via `?token=` ou `Authorization` header. O token fica em uma
variavel JS global, visivel no DevTools do navegador.

**Risco:** vaazamento de credencial. Mesmo que o token seja o Firebase JWT
do usuario (com expiracao curta), um XSS ou copia-cola no console
expporia o token.

**Causa raiz:** `auth_token` e passado para `render_dashboard(commit, deployed_at, auth_token)`,
e dentro do template a string e injetada em JS:
```html
<script>const AUTH = '{{ AUTH }}';</script>
```

**Correcao (no runtime):** NAO expor o token no JS. O backend ja valida o
token antes de servir a pagina (middleware `core/auth.py`). O JS do
modulo deve confiar na sessao estabelecida e fazer chamadas fetch com
`credentials: 'include'` (cookies) em vez de passar o token via header.

**Correcao (no Portal):** o Portal ja tem o Firebase JWT do usuario logado
no frontend. Em vez de passar o token via `?token=` para o agents-runtime,
o Portal pode usar um proxy autenticado que ja conhece o usuario.

**Validacao:** abrir o modulo no Portal, abrir DevTools, confirmar que
a variavel `AUTH` nao existe (ou esta vazia). As requests fetch seguintes
devem funcionar via cookie de sessao.

---

## 4. `commit` no header usa o build ID em vez do SHORT_SHA

> (redundante com item 1, mas aqui fica a referencia do lado git)

**Arquivo:** `agents_runtime/core/module_ui.py:_TEMPLATE` (linha 88 ou
proxima — o template injeta `commit` no header via `{{ commit }}`).

Ja e resolvido com a correcao do item 1 (mudar `$BUILD_ID` para `$SHORT_SHA`
no `cloudbuild-test.yaml`).

---

## 5. Resumo das acoes

| # | Arquivo | Mudanca | Impacto |
|---|---|---|---|
| 1 | `agents_runtime/cloudbuild-test.yaml:44` | `COMMIT_SHA=$BUILD_ID` → `COMMIT_SHA=$SHORT_SHA` | Header mostra SHA curto real |
| 2 | `agents_runtime/cloudbuild-test.yaml:44` | Adicionar `DEPLOYED_AT=$_DEPLOYED_AT` + substitution | Header mostra data real |
| 3 | `agents_runtime/core/module_ui.py` | Remover injecao de `auth_token` no JS; usar cookie de sessao | Sem vazamento de credencial |
| 4 | (cumulativo com #1) | — | — |

**Aplicar:** apos edicao, commit + push → Cloud Build dispara build via
trigger 2nd-gen `deploy-agents-runtime-test` (criado em 25/07/2026 via
this fix). Deploy automatico em ~3min. Portal reflete a UI corrigida
no proximo refresh (a Portal carrega `?token=<jwt>` no clique, sem
cache).

---

## 6. Pre-requisitos no Portal (fora deste repo)

Apos as correcoes no runtime, o Portal nao precisa de nenhuma alteracao
para continuar funcionando. As correcoes sao todas server-side:
- `/oauth/google` ja foi removido de `PROTECTED_PATHS` (publico)
- `/` ja serve HTML quando `?token=` presente (retrocompat)
- `/admin/dashboard` ja servia HTML via `render_dashboard`

**Nenhuma mudanca de `module_url` no Portal e necessaria.**

---

## 7. Debug: como ver o module UI ao vivo

1. Abrir `https://coherence-portal-...run.app/`
2. Logar com a conta Google workspace
3. Clicar em "Agents Omnichannel" no menu lateral
4. O Portal abre `https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/?token=<jwt>` em iframe ou nova janela
5. Esperado: ver UI renderizada com header "commit 50434c5" (apos correcao) e contas/agentes listados
