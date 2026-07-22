# Cleanup do Repositorio Legado (Fase F)

> Procedure manual para o usuario deletar a pasta local `WhatsappAgente/`
> e o repo GitHub `viniciusbritor/WhatsappAgente`, redundantes apos a Fase A
> consolidar o webhook Evolution no `agents_runtime`.

## Contexto

Apos o commit `e38471a` (Fase A), o `agents_runtime` absorveu o webhook
Evolution. O thin proxy externo `whatsapp-agente` (repo separado
`viniciusbritor/WhatsappAgente`) NAO e mais deployado nem referenciado
em nenhum Cloud Build trigger (confirmado em `docs/HARNESS.md`):
> `deploy-whatsapp-agente-*` | **deletado 2026-07-21** (proxy consolidado em agents-runtime)

## Pre-condicoes

1. Branch `test` local com commits `1862d51` + `ff6375f` + `6f095d8` aplicados.
2. `.gitignore` ja exclui `WhatsappAgente/` (commit `1862d51`).
3. Nenhum script operacional referencia o repo legado:
   ```powershell
   cd C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp
   Select-String -Path "*.yaml" -Pattern "whatsapp-agente|WhatsappAgente" -Recurse
   ```
   Saida esperada: vazio ou apenas mencoes em `docs/` (historico).

## Procedure — pasta local

### 1. Confirmar conteudo

```powershell
Get-ChildItem -LiteralPath "C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente" -Recurse | Select-Object -First 20
```

Confirme que nao ha trabalho nao commitado dentro de `WhatsappAgente/`.

### 2. Backup opcional

```powershell
Compress-Archive -Path "C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente" -DestinationPath "C:\Users\vinic\AppData\Local\Temp\WhatsappAgente-backup-$(Get-Date -Format yyyyMMdd).zip"
```

### 3. Deletar pasta

```powershell
Remove-Item -LiteralPath "C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente" -Recurse -Force
```

### 4. Confirmar

```powershell
Test-Path -LiteralPath "C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente"
```

Saida esperada: `False`.

## Procedure — repo GitHub

### 1. Verificar que nao ha PRs/Issues abertas

Abra `https://github.com/viniciusbritor/WhatsappAgente/issues` e
`https://github.com/viniciusbritor/WhatsappAgente/pulls` no browser.
Confirme que nao ha itens em aberto.

### 2. Arquivar antes de deletar (recomendado)

GitHub permite reverter delete em ate 90 dias. Para manter
rastro, prefira `Archive`:

```powershell
gh repo archive viniciusbritor/WhatsappAgente --confirm
```

OU via UI: `https://github.com/viniciusbritor/WhatsappAgente/settings` ->
"Archive this repository".

### 3. Deletar definitivamente (irreversivel)

Via UI apenas:
1. `https://github.com/viniciusbritor/WhatsappAgente/settings`
2. Scroll ate "Danger Zone"
3. "Delete this repository"
4. Digitar `viniciusbritor/WhatsappAgente` para confirmar.

OU via CLI (requer `gh auth login` e permissao admin):

```powershell
gh repo delete viniciusbritor/WhatsappAgente --confirm
```

### 4. Limpar referencias locais

```powershell
git remote remove whatsapp-agente 2>$null
git config --unset-all remote.whatsapp-agente.url 2>$null
```

## Pendencias

- [ ] Usuario deleta pasta local `C:\Users\vinic\workspace_antigravity\ChatBotWhatsapp\WhatsappAgente\`.
- [ ] Usuario arquiva ou deleta repo `viniciusbritor/WhatsappAgente` no GitHub.
- [ ] Confirmar saida `False` em `Test-Path`.
- [ ] Marcar este checklist como completo no `docs/fases/fase_F/checklist.md`.