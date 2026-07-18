# Correção de Bugs do ChatBotWhatsapp

O diagnóstico dos problemas apontou três falhas estruturais que serão resolvidas com as alterações abaixo:

## User Review Required

> [!CAUTION]
> A correção do Firestore (`orchestrator.py`) substituirá o uso puramente síncrono por uma execução via `asyncio.to_thread` ou `run_in_executor` e adicionará tratamento de exceções adequado.

## Open Questions

- Como a Evolution API / `WhatsappAgente` está repassando o áudio via webhook? (Por base64 no `audio_base64` ou apenas a URL no `audio_url`?) No plano abaixo, prevemos o suporte a ambos de forma agnóstica para garantir que a feature de transcrição de voz retome o funcionamento.

## Proposed Changes

### Orquestrador e Vector DB
#### [MODIFY] [orchestrator.py](file:///c:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/orchestrator.py)
- Alterar a função `_index_message` para proteger a obtenção do embedding caso `embed_query` retorne `None`.
- Desacoplar a chamada síncrona bloqueante `db.collection(...).add()` enviando-a para um thread executor (`asyncio.to_thread`) para evitar bloqueios na event loop.
- Adicionar logs explícitos de sucesso e de erro no processo de indexação do RAG.

### Processamento de Áudio
#### [MODIFY] [main.py](file:///c:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/main.py)
- Alterar a verificação na rota `POST /chat` para `if extra.get("has_audio"):` ao invés de depender de `audio_base64`.
- Adicionar suporte para processar o áudio via `audio_url` caso `audio_base64` não esteja presente, garantindo a compatibilidade conforme especificado na `ARQUITETURA.md`.

### Frontend / Dashboard do Portal (Erros 403)
#### [MODIFY] [main.py](file:///c:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/main.py)
- Na string HTML em `/admin/dashboard/diagrama`, corrigir o helper `api()` em Javascript (linhas ~544 e ~551).
- Substituir:
  `const sep = path.includes('?') ? '&amp;' : '';`
  Por:
  `const sep = path.includes('?') ? '&' : '?';`
- Isso fará com que a URL passe o token como query string (`?token=XYZ` ou `&token=XYZ`), validando corretamente no `auth_middleware` sem quebrar as rotas e gerar os erros **403**.

## Verification Plan

### Manual Verification
- Validar as abas no painel `/admin/dashboard/diagrama` com a aplicação rodando.
- O usuário deve enviar uma mensagem de voz pelo WhatsApp para atestar que a assistente consegue escutar e transcrever.
- Validar pelo Firestore se novas mensagens de texto estão sendo armazenadas corretamente na coleção `conversation-memory-{phone}` contendo o campo de vetores preenchido.

## Revisão de Execução — 18/07/2026

O plano foi aprovado como diagnóstico inicial, mas a execução da Fase 3 foi ampliada para eliminar as causas estruturais:

- Provider canônico MiniMax `embo-01` com 1536 dimensões, sem fallback dimensional.
- Collections fixas v2 com isolamento por `owner_hash`.
- Campo Firestore `Vector` em todas as bases vetoriais.
- Busca nativa com `find_nearest`, sem varredura integral em Python.
- Schema versionado e reindexação obrigatória.
- Memória privada mascarada, com retenção de 90 dias e exclusão LGPD.
- Indexação não bloqueante, observável e idempotente.
- Testes automatizados obrigatórios antes do início da Fase 4.

### Resultado da Fase 3

- 16 testes RAG passaram.
- Suite completa: 168 passed, 9 skipped.
- Reindexador validado em dry-run com 143 paginas e 192 chunks.
- Fase 4 liberada somente apos o gate verde.

### Resultado das Fases 4 e 5

- Fase 4: 41 testes especificos; suite completa com 193 passed e 9 skipped.
- Fase 5: 30 testes especificos; suite completa com 212 passed e 9 skipped.
- Audio somente por voz agora e aceito.
- Base64 e prioritario; URL e fallback seguro.
- Whisper local substituiu Gemini no STT.
- Inventario operacional e resposta deterministica corrigem a consulta sobre agentes.
