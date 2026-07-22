# Setup OAuth per-user no Google Cloud Console (Fase F)

> Procedure manual para o usuario configurar o OAuth Client no Google Cloud
> Console e executar o fluxo de autorizacao para o telefone master
> `+5511966830020` (Vinicius Britto).

## Contexto

Apos as Fases C/D, o `agents_runtime` exige OAuth per-user. O secret
`COHERENCE_18_PLUS_OAUTH_CLIENT_ID` ja existe no Secret Manager do projeto
`coherence-ominichannel-fs`. Falta:

1. Configurar Authorized redirect URIs no Console.
2. Confirmar scopes do Client.
3. Executar o fluxo `/oauth/google` para gerar tokens por usuario em
   `usuarios/{phone}/google_oauth_token`.

## Pre-condicoes

1. `gcloud` autenticado no projeto `coherence-ominichannel-fs`:
   ```powershell
   gcloud config set project coherence-ominichannel-fs
   ```
2. Permissao `secretmanager.versions.access` no IAM.
3. Branch `test` deployada (gate verde, commit `6f095d8` ou HEAD).
4. Acesso ao Google Cloud Console com role `Owner` ou `OAuth Admin`.

## Procedure 1 — Console OAuth

### 1.1. Localizar o Client

1. Abrir `https://console.cloud.google.com/apis/credentials?project=coherence-ominichannel-fs`.
2. Em "OAuth 2.0 Client IDs", localizar o Client com nome `coherence-18-plus`.
3. Anotar o `Client ID` (deve coincidir com o secret
   `COHERENCE_18_PLUS_OAUTH_CLIENT_ID` no Secret Manager).

### 1.2. Authorized redirect URIs

Adicionar:

- `https://agents-runtime-test-c5nbfc5meq-uc.a.run.app/oauth/callback`
- `https://agents-runtime-prod-XXXXX-uc.a.run.app/oauth/callback` (quando o
  servico prod for deployado — substituir `XXXXX` pelo suffix real)

NAO incluir `localhost` em producao.

### 1.3. Authorized JavaScript origins

Adicionar:

- `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app`
- `https://coherence-portal-prod-XXXXX-uc.a.run.app`

### 1.4. Scopes

Confirmar que o Client tem os scopes necessarios para Calendar, Drive, Gmail
e People API:

- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.send`

Caso algum esteja faltando, adicione via "Add or remove scopes".

### 1.5. Salvar

Clicar em "Save". Google pode levar ate 5 minutos para propagar.

## Procedure 2 — Execucao do OAuth pelo usuario

### 2.1. Gerar URL de autorizacao

Em PowerShell, com a branch `test` deployada:

```powershell
$base = 'https://agents-runtime-test-c5nbfc5meq-uc.a.run.app'
$phone = '5511966830020'
$state = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($phone))
$url = "$base/oauth/google?state=$state&instance=jennifer"
Write-Host "Abra no browser: $url"
```

A `state` deve estar assinada com `OAUTH_STATE_SECRET` (HMAC-SHA256). O
endpoint `/oauth/google` aceita a versao **plain** (apenas base64) por
compatibilidade com a UI do Portal. Em producao, prefira o fluxo Portal.

### 2.2. Autorizar no browser

1. Abrir a URL no navegador.
2. Login com a conta Google pessoal (Vinicius Britto).
3. Autorizar todos os 5 scopes listados acima.
4. O callback `/oauth/callback` redireciona para o Portal com `?ok=1`.
5. Verificar que o token foi persistido:

```powershell
gcloud firestore documents get users/5511966830020/google_oauth --project=coherence-ominichannel-fs
```

Campo esperado: `google_oauth_token.token`, `refresh_token`, `expiry`,
`updated_at`.

### 2.3. Smoke test dos managers

Em uma conversa WhatsApp com Jennifer:

1. "Quais sao meus eventos hoje?" — espera resposta com eventos reais do
   Calendar via `_prefetch_calendar`.
2. "Mostre meus emails recentes" — espera resposta com snippets reais do
   Gmail via `_prefetch_email`.
3. "Busque atas no Drive" — espera resposta com arquivos reais do Drive
   via `_prefetch_drive`.

Caso algum falhe:

- Token expirado: o codigo refresca automaticamente via
  `core.oauth_per_user.get_valid_user_token`. Logs do Cloud Run devem
  mostrar `"oauth refresh failed: ..."`.
- Scope ausente: verificar Procedure 1.4.
- Client ID mismatch: comparar com `COHERENCE_18_PLUS_OAUTH_CLIENT_ID`.

## Rollback

Caso o usuario queira reverter para OAuth global (legacy):

1. Reativar secret `google-oauth-token` (NAO deletar antes da reversao).
2. Reverter commit `ff6375f` (Fase D) com `git revert ff6375f`.
3. Push da reversao na branch `test`.

## Pendencias

- [ ] Usuario configura Authorized redirect URIs e JavaScript origins.
- [ ] Usuario confirma os 5 scopes no Console.
- [ ] Usuario executa OAuth para `+5511966830020`.
- [ ] Usuario valida pre-fetch de calendar/email/drive no WhatsApp.
- [ ] Marcar este checklist como completo no `docs/fases/fase_F/checklist.md`.