# Cleanup de Secrets Orfaos (Fase F)

> Procedure manual para o usuario deletar 2 secrets do GCP Secret Manager
> que se tornaram orfaos apos a consolidacao do webhook no `agents_runtime`
> (Fase A) e a migracao para OAuth per-user (Fases C/D).

## Contexto

Apos o commit `ff6375f` (Fase D), o codigo de producao NAO consulta mais os
seguintes secrets:

- `whatsapp-agente-url`: URL do `whatsapp-agente-test` (proxy deletado na Fase A).
- `agents-runtime-sa-token-clean`: duplicata de `agents-runtime-sa-token` (refresh ja existe no codigo).

Ambos podem ser deletados do Secret Manager do projeto `coherence-ominichannel-fs`
**sem impacto funcional** para `agents-runtime` e seus workers.

## Pre-condicoes

1. `gcloud` autenticado no projeto `coherence-ominichannel-fs`:
   ```powershell
   gcloud config set project coherence-ominichannel-fs
   gcloud auth login
   ```
2. Permissao `secretmanager.versions.destroy` no IAM.
3. Gate local verde (commit `6f095d8` ou HEAD atual da branch `test`).
4. Confirmar manualmente que `core.secrets.get_secret("GOOGLE_OAUTH_TOKEN")`
   nao e mais chamado em `agents_runtime/`. Comando rapido:
   ```powershell
   cd agents_runtime
   Select-String -Path "*.py" -Pattern 'get_secret..GOOGLE_OAUTH_TOKEN' -Recurse | Where-Object { $_.Path -notmatch "docs/" }
   ```
   Saida esperada: vazio.

## Procedure

### 1. Listar versoes atuais

```powershell
gcloud secrets versions list whatsapp-agente-url --project=coherence-ominichannel-fs
gcloud secrets versions list agents-runtime-sa-token-clean --project=coherence-ominichannel-fs
```

Confirme que a versao `latest` NAO e referenciada por nenhum Cloud Run service.

```powershell
gcloud run services list --project=coherence-ominichannel-fs --format="value(name)" | ForEach-Object {
    gcloud run services describe $_ --project=coherence-ominichannel-fs --format="value(spec.template.spec.containers[0].env)" 2>$null
} | Select-String "whatsapp-agente-url|agents-runtime-sa-token-clean"
```

Saida esperada: vazio.

### 2. Desabilitar versao (soft delete, reversivel)

```powershell
gcloud secrets versions disable latest --secret="whatsapp-agente-url" --project=coherence-ominichannel-fs
gcloud secrets versions disable latest --secret="agents-runtime-sa-token-clean" --project=coherence-ominichannel-fs
```

### 3. Destruir versao (hard delete, irreversivel)

Aguarde 7 dias OU destrua imediatamente (ambos sao seguros dado que o gate
local confirma que nao ha consumers):

```powershell
gcloud secrets versions destroy latest --secret="whatsapp-agente-url" --project=coherence-ominichannel-fs
gcloud secrets versions destroy latest --secret="agents-runtime-sa-token-clean" --project=coherence-ominichannel-fs
```

### 4. Deletar o secret inteiro (opcional)

```powershell
gcloud secrets delete "whatsapp-agente-url" --project=coherence-ominichannel-fs
gcloud secrets delete "agents-runtime-sa-token-clean" --project=coherence-ominichannel-fs
```

### 5. Confirmar

```powershell
gcloud secrets list --project=coherence-ominichannel-fs --filter="name:whatsapp-agente-url OR name:agents-runtime-sa-token-clean"
```

Saida esperada: vazio.

## Rollback

Caso algum servico dependa do secret (improvavel dado gate verde), restaure
via UI do Secret Manager ou:

```powershell
gcloud secrets versions enable latest --secret="whatsapp-agente-url" --project=coherence-ominichannel-fs
```

## Pendencias

- [ ] Usuario deleta `whatsapp-agente-url` do projeto `coherence-ominichannel-fs`.
- [ ] Usuario deleta `agents-runtime-sa-token-clean` do projeto `coherence-ominichannel-fs`.
- [ ] Confirmar saida vazia de `gcloud secrets list --filter=...`.
- [ ] Marcar este checklist como completo no `docs/fases/fase_F/checklist.md`.