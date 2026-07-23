# Política de Privacidade — ChatBotWhatsapp

> Última atualização: 2026-07-22.
> Esta política descreve como o módulo `Agentes Omnichannel` trata dados
> pessoais coletados via WhatsApp, Gmail, Google Drive, Google Calendar e
> documentos armazenados em Google Cloud Storage.

## 1. Controlador e encarregado

- **Operador**: Coherence AI — projeto GCP `coherence-ominichannel-fs`.
- **Encarregado de dados (DPO)**: ver `docs/LGPD_DPO.md` (módulo OmniChannel).
- **Contato**: `dpo@coherenceai.com.br`.

## 2. Dados coletados

- **Mensagens WhatsApp** recebidas e enviadas (texto, áudio transcrito,
  metadados como telefone, push name, timestamps).
- **Tokens OAuth Google** (refresh token, escopos autorizados) armazenados em
  Firestore no documento `usuarios/{phone}`. `client_id` e `client_secret`
  nunca são persistidos.
- **Conteúdo vetorial** (texto mascarado, embeddings OpenAI) em
  `conversation-memory-v2`, `agent-knowledge-v2` e `public-knowledge-v2`.
- **Logs operacionais** estruturados (em JSON, com mascaramento PII) e
  trilha de auditoria em `audit/` (retenção 5 anos).

## 3. Finalidades

- Responder mensagens via WhatsApp conforme configuração do agente.
- Executar ferramentas Google (Calendar, Drive, Gmail) somente para o
  telefone autorizado do proprietário da conta Evolution.
- Manter memória vetorial privada por proprietário e por conta.
- Operar o módulo `Agentes Omnichannel` (logs, métricas, auditoria).

## 4. Base legal

- **Execução de contrato** quando o titular é o próprio usuário conectado.
- **Legítimo interesse** para segurança operacional (anti-spam, DLQ,
  auditoria).
- **Consentimento explícito** para fallback STT Gemini 2.5 Flash,
  proatividade e armazenamento de apelidos.

## 5. Compartilhamento

- Dados são processados exclusivamente no projeto GCP da Coherence AI.
- Provedores externos: OpenAI (embeddings, sob contrato), Google APIs (sob
  OAuth do titular), Gemini 2.5 Flash (fallback STT sob consentimento).
- Nenhum dado é vendido ou compartilhado com terceiros para fins próprios.

## 6. Retenção

- Conversas e memória vetorial: 90 dias (TTL).
- Auditoria: 5 anos.
- Logs operacionais: 30 dias (Google Cloud Logging) com mascaramento.

## 7. Direitos do titular (Art. 18 LGPD)

- Acesso, correção, portabilidade e exclusão via endpoints do módulo.
- Revogação de consentimento (`POST /oauth/google` re-link ou remoção manual
  de `usuarios/{phone}`).
- Exportação de dados próprios via `core/lgpd.export_user`.

## 8. Segurança

- Criptografia em repouso (GCP padrão).
- Autenticação: Bearer SA ou Firebase ID token; webhook Evolution é
  público mas validado por filtros de payload.
- Máscara PII obrigatória antes de qualquer LLM externo.
- Owner-only Google: Gmail/Drive/Calendar só executam quando o telefone
  remetente coincide com o `owner_phone` da conta Evolution.

## 9. Encarregado

Para solicitações, contacte `dpo@coherenceai.com.br` ou abra issue no
repositório.

---

> Este documento é a versão canônica para o ChatBotWhatsapp. As cópias em
> `agents_runtime/docs/` foram removidas.