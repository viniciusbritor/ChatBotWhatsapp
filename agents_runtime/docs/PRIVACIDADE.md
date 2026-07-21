# Política de Privacidade — Agents Runtime

**Versão:** 1.0  
**Vigência:** 21/07/2026

## Escopo

Esta política descreve o tratamento de dados realizado pelo módulo `agents_runtime`, responsável pela assistente Jennifer e pelas integrações de WhatsApp, Google Calendar, Google Drive e Gmail no ecossistema Coherence.

## Dados tratados

O módulo pode tratar:

- número de telefone e nome de exibição do WhatsApp;
- mensagens de texto e transcrições mascaradas;
- áudio recebido apenas durante o processamento da transcrição;
- identificadores de mensagem, conversa, instância e grupo;
- tokens OAuth individuais e escopos autorizados pelo usuário;
- eventos de calendário, arquivos e mensagens de e-mail solicitados pelo usuário;
- preferências, consentimentos e comandos de proatividade;
- logs técnicos, métricas e trilhas de auditoria.

## Finalidades

Os dados são usados para:

- responder mensagens e executar ações solicitadas;
- manter contexto e memória de conversa;
- transcrever áudio localmente;
- acessar serviços Google autorizados;
- impedir duplicidade, abuso e envio indevido;
- gerar atas e mensagens proativas consentidas;
- diagnosticar falhas e cumprir obrigações de segurança e auditoria.

## Inteligência artificial e minimização

Dados pessoais identificáveis são mascarados antes do envio a provedores externos de modelos. O módulo utiliza somente os dados necessários para cada solicitação. Áudio bruto, URLs temporárias de mídia e transcrições parciais não são armazenados na memória RAG.

A memória vetorial privada utiliza `owner_hash` e texto mascarado. Falhas de transcrição geram apenas um marcador técnico sanitizado.

## Armazenamento e retenção

- memória de conversa e histórico: até 90 dias;
- trilha de auditoria: até 5 anos quando necessária para rastreabilidade;
- tokens OAuth: enquanto a integração permanecer autorizada ou até revogação;
- áudio bruto: não é persistido pelo módulo;
- ações pendentes de consentimento: expiram automaticamente.

Os dados são processados em serviços GCP configurados pelo projeto, inclusive região fora do Brasil. São aplicadas medidas contratuais, controle de acesso e minimização para transferências internacionais.

## Compartilhamento

Dados podem ser processados por serviços estritamente necessários ao funcionamento, incluindo GCP, Evolution API e provedores de modelos configurados. Credenciais e tokens não são enviados aos modelos de IA.

## Direitos do titular

O titular pode solicitar confirmação de tratamento, acesso, correção, portabilidade, informação sobre compartilhamento, revogação de consentimento e exclusão nos limites legais. Enquanto a interface de autosserviço do Portal estiver em implantação, as solicitações são tratadas pelo operador responsável pelo ambiente Coherence.

## Segurança

O módulo adota Secret Manager, OAuth individual, mascaramento de PII, autenticação de endpoints protegidos, logs sanitizados, deduplicação e segregação por proprietário. Nenhuma chave deve ser armazenada em código ou repositório Git.

## Alterações

Mudanças materiais nesta política exigem nova versão, registro da data de vigência e comunicação apropriada aos usuários afetados.
