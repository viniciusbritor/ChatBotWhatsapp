# Termos de Uso — ChatBotWhatsapp

> Última atualização: 2026-07-22.
> Estes Termos regulam o uso do módulo `Agentes Omnichannel` exposto pelo
> serviço `agents-runtime`.

## 1. Aceitação

Ao conectar uma conta Evolution, autorizar o OAuth Google ou utilizar o
plano de controle em `/admin/dashboard`, o titular declara estar de acordo
com estes Termos e com a Política de Privacidade.

## 2. Serviço

- Atendimento automatizado via WhatsApp para o telefone autorizado.
- Integração com Google Calendar, Drive e Gmail usando as credenciais do
  próprio titular.
- Memória vetorial privada e base pública de conhecimento.
- Fallback STT Gemini 2.5 Flash sob consentimento explícito.

## 3. Obrigações do titular

- Fornecer números de telefone válidos e contas Google autorizadas.
- Não utilizar o serviço para spam, assédio ou atividades ilícitas.
- Respeitar os limites da Evolution API e das APIs Google.
- Revogar tokens (`POST /oauth/google`) ou apagar o documento
  `usuarios/{phone}` para encerrar o uso.

## 4. Obrigações do operador

- Manter logs operacionais, auditoria e mascaramento PII.
- Fornecer exclusão e exportação de dados via `core/lgpd`.
- Aplicar guardrails de segurança em conformidade com a LGPD.
- Disponibilizar canal de contato com o encarregado de dados.

## 5. Limitações

- O serviço depende de provedores externos (OpenAI, Google APIs,
  Evolution). Falhas fora do nosso controle não geram indenização.
- O fallback STT Gemini é limitado a 20 chamadas/dia (`STT_FALLBACK_DAILY_LIMIT`).
- Proatividade respeita janelas 21h–9h BRT e caps anti-spam.

## 6. Suspensão

O operador pode suspender o serviço em caso de violação destes Termos ou
de ordens judiciais, mediante aviso prévio quando possível.

## 7. Alterações

Mudanças relevantes serão refletidas neste documento com nova data de
vigência.

## 8. Foro

Fica eleito o foro da Comarca de São Paulo/SP para dirimir quaisquer
questões, sem prejuízo de eventuais direitos do consumidor aplicáveis.

---

> Estes Termos são a versão canônica para o ChatBotWhatsapp. As cópias em
> `agents_runtime/docs/` foram removidas.