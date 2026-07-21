# Plano de execução — Gate B.6

## Entendimento

- O escopo é exclusivamente o fechamento técnico do gate B.6.
- Os testes específicos cobrem o pipeline áudio, webhook, Pub/Sub, orquestração e RAG.
- A validação deve ocorrer em Python 3.12, igual ao Cloud Build.
- A suite deve ser isolada de secrets reais e de implementações posteriores.
- Não fazem parte do escopo: B.7, documentação permanente, commit ou deploy.

## Premissas

- O estado atual do workspace não será revertido ou apagado.
- Correções serão limitadas aos bloqueadores comprovados do gate.
- Nenhum teste será afrouxado, removido ou marcado para ignorar apenas para obter resultado verde.
- O gate exige zero falhas em testes, Ruff e mypy.

## Execução

1. Registrar o estado Git e o diff atual.
2. Criar um worktree temporário dentro do projeto a partir do HEAD.
3. Aplicar ao worktree somente as alterações da Fase B e seus testes.
4. Preparar um ambiente Python 3.12 isolado.
5. Remover secrets LLM do ambiente de teste e desabilitar acesso ao Secret Manager.
6. Executar os 17 testes específicos da Fase B.
7. Executar a suite geral existente no estado isolado.
8. Executar Ruff.
9. Executar mypy.
10. Corrigir somente bloqueadores diretamente relacionados ao gate e repetir todos os validadores.
11. Transferir ao workspace principal apenas correções mínimas confirmadas.
12. Remover o worktree temporário e apresentar as evidências.

## Critérios de aceite

- 17 testes específicos da Fase B aprovados.
- Suite geral com zero falhas e zero erros.
- Ruff com código de saída zero.
- mypy com código de saída zero.
- Nenhuma alteração posterior à Fase B incluída na validação.
- Nenhum commit ou deploy executado.

## Decisões

| Decisão | Alternativas | Motivo |
|---|---|---|
| Usar worktree isolado | Validar o workspace atual; reverter alterações posteriores | Evita misturar Pub/Sub, OAuth e demais fases sem perder trabalho local |
| Usar Python 3.12 | Usar Python 3.14 local | Mantém paridade com Cloud Build e dependências oficiais |
| Neutralizar secrets reais | Aceitar secrets disponíveis no ambiente | Torna os testes LLM determinísticos e evita chamadas externas |
| Aplicar correções mínimas | Refatorar módulos durante o gate | Reduz risco e preserva o escopo exclusivo do B.6 |
