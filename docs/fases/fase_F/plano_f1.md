# Fase F — Cleanup + Documentação Final

## Entendimento

- Apos 5 fases (A-E) de commits atomicos, o gate local esta verde e os
  pendentes internos estao zerados. Restam apenas pendencias **externas**:
  4 secrets orfaos, 1 pasta local, 1 repo GitHub, configuracao de OAuth no
  Google Cloud Console e execucao manual do OAuth pelo usuario.
- A Fase F e puramente de **documentacao**: criar procedures claras para o
  usuario executar o cleanup manual, atualizar `HARNESS.md` com troubleshooting
  OAuth e lista de secrets, e fechar 4 docs permanentes com o status final
  da esteira.
- O gate local exige zero falhas, zero erros, zero warnings, Ruff zero,
  mypy zero e LGPD zero (validar para garantir que nao regrediu).

## Premissas

- A esteira local NAO tera mais codigo novo ate o merge da branch `test`.
- Nenhum segredo real sera carregado pelo ambiente.
- Nenhum teste sera afrouxado, removido ou marcado como `xfail`/`skip`.
- A documentacao permanente sera atualizada **somente** apos o gate tecnico
  ficar verde.
- A pasta `C:\Users\vinic\workspace_antigravity\WhatsappAgente\` sera deletada
  APENAS pelo usuario (cleanup manual com `rmdir /s /q` ou `Remove-Item
  -Recurse -Force`), nao pelo agente.
- O repo `viniciusbritor/WhatsappAgente` sera deletado APENAS pelo usuario
  via GitHub Settings > Danger Zone.

## Escopo tecnico

| Bloco | Itens | Arquivos |
|---|---|---|
| F.1 | Procedure de cleanup do secret `whatsapp-agente-url` | `docs/fases/fase_F/cleanup_secrets.md` |
| F.2 | Procedure de cleanup do secret `agents-runtime-sa-token-clean` | `docs/fases/fase_F/cleanup_secrets.md` |
| F.3 | Procedure de cleanup da pasta local `WhatsappAgente/` | `docs/fases/fase_F/cleanup_repo.md` |
| F.4 | Procedure de cleanup do repo `viniciusbritor/WhatsappAgente` | `docs/fases/fase_F/cleanup_repo.md` |
| F.5 | Procedure OAuth no Google Cloud Console + execucao manual | `docs/fases/fase_F/oauth_setup.md` |
| F.6 | Atualizar `HARNESS.md` com troubleshooting OAuth + lista de secrets | `docs/HARNESS.md` |
| F.7 | Atualizar `GUARDRAILS.md` com regra 56 (cleanup post-merge) | `docs/GUARDRAILS.md` |
| F.8 | Atualizar `ARQUITETURA.md` com status final dos componentes | `docs/ARQUITETURA.md` |
| F.9 | Fechar `DIARIO_BORDO.md` com status da Fase F | `docs/DIARIO_BORDO.md` |
| F.10 | Checklist final da Fase F | `docs/fases/fase_F/checklist.md` |

## Execucao

1. Validar gate local (pytest 316 passed, 10 skipped).
2. Criar `cleanup_secrets.md`, `cleanup_repo.md` e `oauth_setup.md` com
   procedures PowerShell + gcloud + GitHub CLI.
3. Atualizar `HARNESS.md` secao "Autenticação e Segredos" com troubleshooting.
4. Atualizar `GUARDRAILS.md` com regra 56.
5. Atualizar `ARQUITETURA.md` e `DIARIO_BORDO.md`.
6. Rodar gate ate zero.
7. Commit atomico `chore(fase-F): cleanup procedures e docs finais`.

## Criterios de aceite

- 4 docs permanentes atualizadas.
- 3 procedures de cleanup criadas em `docs/fases/fase_F/`.
- Gate local verde (pytest 316+, ruff 0, mypy 0, LGPD 0).
- Checklist final da Fase F assinado.

## Decisoes

| Decisao | Alternativas | Motivo |
|---|---|---|
| Procedures em Markdown, nao scripts | Scripts PowerShell auto-executaveis | Usuario controla execucao; cleanup e irreversivel |
| Manter `WhatsappAgente/.gitignore` bloqueando o folder | Deletar a pasta agora | Cleanup manual e reversivel ate o merge da branch |
| Incluir troubleshooting OAuth na HARNESS | Wiki separado | HARNESS e o doc canonico operacional |