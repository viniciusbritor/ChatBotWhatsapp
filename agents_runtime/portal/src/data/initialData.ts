import {
  WhatsAppAccount,
  Agent,
  Skill,
  Tool,
  Owner,
  Integration,
  ServiceConnection,
  KnowledgeCategory,
  SystemStatusMetric
} from '../types';

export const INITIAL_WHATSAPP_ACCOUNTS: WhatsAppAccount[] = [
  {
    id: 'wa-1',
    name: 'Jennifer',
    phone: '+5511966830020',
    ownerPhone: '+5511966830020',
    status: 'Conectado',
    instanceName: 'Jennifer_Prod',
    updatedAt: '2026-08-11T19:30:00Z'
  }
];

export const INITIAL_AGENTS: Agent[] = [
  {
    id: 'agent-1',
    key: 'jennifier',
    name: 'Jennifier (Maestro Principal)',
    model: 'deepseek-v4-flash',
    description: 'Orquestrador primario do WhatsApp Omnichannel',
    status: 'Active',
    delegatesTo: [
      'agent-knowledge-retriever',
      'agent-categorizer',
      'manager-calendar',
      'manager-email',
      'manager-drive'
    ],
    temperature: 0.2,
    systemPrompt: `Você é a Jennifer, a assistente principal do sistema Coherence WhatsApp Omnichannel.
Sua função é receber mensagens de usuários no WhatsApp, entender a intenção principal e delegar requisições específicas aos sub-agentes adequados (Busca de Conhecimento, Agendamento no Google Calendar, Gestão de Emails no Gmail e Arquivos no Google Drive). Responda sempre de forma profissional, ágil e em Português do Brasil.`
  },
  {
    id: 'agent-2',
    key: 'agent-knowledge-retriever',
    name: 'Knowledge Retriever (RAG Sub-Agent)',
    model: 'deepseek-v4-flash',
    description: 'Busca vetorial semantica no Firestore (agent-knowledge-v2) com score > 0.7 e suporte a clarification prompts.',
    status: 'Active',
    temperature: 0.1,
    systemPrompt: `Você é o agente de busca de conhecimento RAG. Receba perguntas contextuais e busque apenas trechos relevantes no banco vetorial agent-knowledge-v2 com corte de similaridade de cosseno em 0.7. Monte respostas precisas citando as fontes.`
  },
  {
    id: 'agent-3',
    key: 'agent-categorizer',
    name: 'Knowledge Categorizer',
    model: 'deepseek-v4-flash',
    description: 'Classifica anexos PDF/DOCX/XLSX em 15 classes e 50 grupos antes de persistir.',
    status: 'Active',
    temperature: 0.0,
    systemPrompt: `Sua tarefa é analisar o conteúdo ou metadados de arquivos recebidos (PDF, DOCX, XLSX) e retornar a classificação em formato JSON estrito, categorizando em até 15 classes predefinidas como ata_reuniao, relatorio_tecnico, planilha_dados.`
  },
  {
    id: 'agent-4',
    key: 'manager-calendar',
    name: 'Calendar Manager',
    model: 'deepseek-v4-flash',
    description: 'Integracao Google Calendar per-user com suporte a OAuth.',
    status: 'Active',
    temperature: 0.1,
    systemPrompt: `Você gerencia horários e compromissos na agenda do Google Calendar do usuário ativo. Valide disponibilidade antes de sugerir agendamentos.`
  },
  {
    id: 'agent-5',
    key: 'manager-email',
    name: 'Email Manager',
    model: 'deepseek-v4-flash',
    description: 'Integracao Gmail per-user para envio e leitura de emails.',
    status: 'Active',
    temperature: 0.2,
    systemPrompt: `Você gerencia caixa de entrada e envios no Gmail via OAuth. Monte rascunhos limpos e solicite confirmação antes de disparar e-mails para contatos externos.`
  },
  {
    id: 'agent-6',
    key: 'manager-drive',
    name: 'Drive Manager',
    model: 'deepseek-v4-flash',
    description: 'Leitura e upload de arquivos no Google Drive (Omnichannel/Atas/).',
    status: 'Active',
    temperature: 0.1,
    systemPrompt: `Você lê, organiza e faz upload de atas e documentos na pasta corporativa do Google Drive.`
  }
];

export const INITIAL_SKILLS: Skill[] = [
  {
    id: 'skill-1',
    code: 'pdf',
    name: 'PDF Knowledge Processing Skill',
    description: 'Extrai texto e estruturacao de tabelas/relatorios em PDF com fallback para OCR.',
    status: 'ACTIVE',
    categoryTag: 'Knowledge / Parsing',
    documentationUrl: '#',
    detailedDoc: 'Skill de parsing inteligente de arquivos PDF. Suporta extração nativa de vetores de texto, tabelas estruturadas e fallback automático via OCR Gemini Vision.'
  },
  {
    id: 'skill-2',
    code: 'docx',
    name: 'Word Document Processing Skill',
    description: 'Processamento e indexacao de documentos Word (DOCX) com preservacao de titulos e secoes.',
    status: 'ACTIVE',
    categoryTag: 'Knowledge / Parsing',
    documentationUrl: '#',
    detailedDoc: 'Extrai parágrafos, cabeçalhos, listas e tabelas em arquivos .docx mantendo a hierarquia H1/H2/H3 para chunking semântico limpo.'
  },
  {
    id: 'skill-3',
    code: 'xlsx',
    name: 'Excel Spreadsheet Processing Skill',
    description: 'Converte planilhas Excel (XLSX) em matrizes de dados formatadas em tabelas ASCII com bordas.',
    status: 'ACTIVE',
    categoryTag: 'Knowledge / Parsing',
    documentationUrl: '#',
    detailedDoc: 'Converte cada aba de planilhas Excel em tabelas ASCII estruturadas facilitando a interpretação do modelo LLM.'
  },
  {
    id: 'skill-4',
    code: 'drive',
    name: 'Google Drive Knowledge Integration',
    description: 'Integracao com Google Drive para leitura direta de arquivos e sincronizacao de atas.',
    status: 'ACTIVE',
    categoryTag: 'Knowledge / Cloud Storage',
    documentationUrl: '#',
    detailedDoc: 'Conecta via Drive API v3 para monitorar alterações na pasta corporativa e disparar reindexação RAG automática.'
  },
  {
    id: 'skill-5',
    code: 'text',
    name: 'Plain Text / Markdown Processing',
    description: 'Indexacao direta de notas, transcripts de reuniao e arquivos de texto puro.',
    status: 'ACTIVE',
    categoryTag: 'Knowledge / Parsing',
    documentationUrl: '#',
    detailedDoc: 'Divisão recursiva por parágrafos e frases em notas TXT/MD.'
  },
  {
    id: 'skill-6',
    code: 'google_calendar_manager',
    name: 'Google Calendar Manager Skill',
    description: 'Skill de gestao de compromissos, checagem de conflitos e envio de lembretes na agenda.',
    status: 'ACTIVE',
    categoryTag: 'Productivity / Agenda',
    documentationUrl: '#',
    detailedDoc: 'Interage com a API do Google Calendar para ler e adicionar eventos com fusos horários configuráveis.'
  },
  {
    id: 'skill-7',
    code: 'agent-knowledge-router',
    name: 'Knowledge Router Skill',
    description: 'Sub-agente roteador que classifica o tipo de anexo e escolhe a melhor skill de extracao.',
    status: 'ACTIVE',
    categoryTag: 'Orchestration / Router',
    documentationUrl: '#',
    detailedDoc: 'Analisa arquivos recebidos via webhook e encaminha para o pipeline PDF, DOCX ou XLSX correspondente.'
  }
];

export const INITIAL_TOOLS: Tool[] = [
  {
    id: 'tool-1',
    code: 'calendar.read_events',
    name: 'Calendar Read Events',
    category: 'Google Calendar',
    typeFilter: 'Google Native',
    description: 'Lê eventos do calendário do usuário autenticado.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/calendar.readonly'],
    samplePayload: JSON.stringify({ timeMin: '2026-08-11T00:00:00Z', timeMax: '2026-08-11T23:59:59Z' }, null, 2)
  },
  {
    id: 'tool-2',
    code: 'calendar.create_event',
    name: 'Calendar Create Event',
    category: 'Google Calendar',
    typeFilter: 'Google Native',
    description: 'Cria novos eventos no calendário do usuário.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/calendar.events'],
    samplePayload: JSON.stringify({ summary: 'Reunião de Alinhamento Coherence', start: '2026-08-12T10:00:00-03:00', end: '2026-08-12T11:00:00-03:00' }, null, 2)
  },
  {
    id: 'tool-3',
    code: 'gmail.list_messages',
    name: 'Gmail List Messages',
    category: 'Gmail',
    typeFilter: 'Google Native',
    description: 'Lista mensagens da caixa de entrada do Gmail.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/gmail.readonly'],
    samplePayload: JSON.stringify({ q: 'is:unread label:INBOX', maxResults: 10 }, null, 2)
  },
  {
    id: 'tool-4',
    code: 'gmail.send_email',
    name: 'Gmail Send Email',
    category: 'Gmail',
    typeFilter: 'Google Native',
    description: 'Envia emails em nome do usuário autenticado.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/gmail.send'],
    samplePayload: JSON.stringify({ to: 'cliente@exemplo.com.br', subject: 'Ata de Reunião Coherence', body: 'Olá, segue em anexo o resumo...' }, null, 2)
  },
  {
    id: 'tool-5',
    code: 'drive.read_file_content',
    name: 'Drive Read File Content',
    category: 'Google Drive',
    typeFilter: 'Google Native',
    description: 'Lê o conteúdo de arquivos armazenados no Google Drive.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/drive.readonly'],
    samplePayload: JSON.stringify({ fileId: '1A2b3C4d5E6f7G8h9I0j' }, null, 2)
  },
  {
    id: 'tool-6',
    code: 'drive.upload_file',
    name: 'Drive Upload File',
    category: 'Google Drive',
    typeFilter: 'Google Native',
    description: 'Faz upload de novos arquivos para o Google Drive.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/drive.file'],
    samplePayload: JSON.stringify({ name: 'relatorio_agosto.pdf', mimeType: 'application/pdf', folderId: 'root' }, null, 2)
  },
  {
    id: 'tool-7',
    code: 'linkedin.post_update',
    name: 'LinkedIn Post Update',
    category: 'Composio MCP',
    typeFilter: 'Composio MCP',
    description: 'Publica atualizações e posts no LinkedIn.',
    status: 'Active',
    permissions: ['w_member_social', 'r_liteprofile'],
    samplePayload: JSON.stringify({ text: 'Lançamos novas atualizações no nosso Control Plane de Agentes de IA! 🚀' }, null, 2)
  },
  {
    id: 'tool-8',
    code: 'youtube.search_videos',
    name: 'YouTube Search Videos',
    category: 'Composio MCP',
    typeFilter: 'Composio MCP',
    description: 'Busca vídeos no YouTube com base em palavras-chave.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/youtube.readonly'],
    samplePayload: JSON.stringify({ query: 'Tutoriais AI Agents Orchestration', maxResults: 5 }, null, 2)
  },
  {
    id: 'tool-9',
    code: 'googledocs.create_doc',
    name: 'Google Docs Creator',
    category: 'Composio MCP',
    typeFilter: 'Composio MCP',
    description: 'Cria novos documentos no Google Docs.',
    status: 'Active',
    permissions: ['https://www.googleapis.com/auth/documents'],
    samplePayload: JSON.stringify({ title: 'Proposta Comercial - Cliente Coherence', content: 'Documento gerado automaticamente pela Jennifer...' }, null, 2)
  }
];

export const INITIAL_OWNERS: Owner[] = [
  {
    id: 'owner-1',
    name: 'Vinicius Brito',
    role: 'Administrator / Owner',
    uid: '5511998765432',
    phone: '+5511998765432',
    instance: 'main_instance'
  }
];

export const INITIAL_INTEGRATIONS: Integration[] = [
  {
    id: 'int-1',
    name: 'Google OAuth 2.0 (Per-User)',
    category: 'OAuth Core',
    status: 'Conectado',
    details: {
      activeScopes: ['gmail.readonly', 'gmail.send', 'drive', 'calendar'],
      storagePath: 'usuarios/{phone}.google_oauth_token',
      redirectUri: 'https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/oauth/callback'
    }
  },
  {
    id: 'int-2',
    name: 'Composio MCP SDK',
    category: 'Multi-App Automation',
    status: 'Ativo',
    details: {
      apiKeySource: 'GCP Secret Manager (COMPOSIO_API_KEY)',
      connectedApps: ['YouTube', 'LinkedIn', 'Google Docs']
    }
  },
  {
    id: 'int-3',
    name: 'Evolution API v2.3.7',
    category: 'Messaging Gateway',
    status: 'Conectado',
    details: {
      endpoint: 'https://evolution-api.coherence.com.br',
      webhookInfo: 'Webhook configurado para eventos de mensagem e status de conexão.'
    }
  }
];

export const INITIAL_SERVICE_CONNECTIONS: ServiceConnection[] = [
  {
    id: 'conn-1',
    name: 'Email (Gmail)',
    category: 'Conta Google',
    description: 'Ler e enviar emails',
    status: 'OK',
    icon: 'mail'
  },
  {
    id: 'conn-2',
    name: 'Agenda (Google Calendar)',
    category: 'Conta Google',
    description: 'Ver e criar compromissos',
    status: 'OK',
    icon: 'calendar_month'
  },
  {
    id: 'conn-3',
    name: 'Arquivos (Google Drive)',
    category: 'Conta Google',
    description: 'Buscar e ler seus documentos',
    status: 'OK',
    icon: 'folder'
  },
  {
    id: 'conn-4',
    name: 'LinkedIn',
    category: 'Outros serviços',
    description: 'Postar e ler seu perfil',
    status: 'OK',
    icon: 'work'
  },
  {
    id: 'conn-5',
    name: 'YouTube',
    category: 'Outros serviços',
    description: 'Gerenciar vídeos',
    status: 'Desconectado',
    icon: 'play_circle'
  },
  {
    id: 'conn-6',
    name: 'GitHub',
    category: 'Outros serviços',
    description: 'Acesso a repositórios',
    status: 'Desconectado',
    icon: 'code'
  },
  {
    id: 'conn-7',
    name: 'Notion',
    category: 'Outros serviços',
    description: 'Ler e escrever páginas',
    status: 'OK',
    icon: 'description'
  }
];

export const INITIAL_KNOWLEDGE_CATEGORIES: KnowledgeCategory[] = [
  {
    id: 'kc-1',
    title: 'Atas de Reunião (DOCX/PDF)',
    formats: 'DOCX/PDF',
    collection: 'agent-knowledge-v2',
    classification: 'ata_reuniao',
    fileCount: 14,
    chunkCount: 128,
    status: 'Indexado',
    chunks: [
      { id: 'c1-1', filename: 'Ata_Diretoria_10_Agosto.pdf', score: 0.94, previewText: 'Deliberação sobre expansão do cluster de agentes e contratação de instâncias dedicadas Cloud Run...' },
      { id: 'c1-2', filename: 'Reuniao_Alinhamento_FinOps.docx', score: 0.88, previewText: 'Aprovação do guardrail 9 de throttling de CPU e escalonamento até zero instâncias ativas...' }
    ]
  },
  {
    id: 'kc-2',
    title: 'Relatórios Técnicos (PDF)',
    formats: 'PDF',
    collection: 'agent-knowledge-v2',
    classification: 'relatorio_tecnico',
    fileCount: 8,
    chunkCount: 140,
    status: 'Indexado',
    chunks: [
      { id: 'c2-1', filename: 'Arquitetura_RAG_Firestore.pdf', score: 0.92, previewText: 'Especificação técnica da busca de vetores utilizando distância de cosseno no Firestore Vector...' }
    ]
  },
  {
    id: 'kc-3',
    title: 'Planilhas Financeiras (XLSX)',
    formats: 'XLSX',
    collection: 'agent-knowledge-v2',
    classification: 'planilha_dados',
    fileCount: 5,
    chunkCount: 84,
    status: 'Indexado',
    chunks: [
      { id: 'c3-1', filename: 'Balancete_Q3_2026.xlsx', score: 0.89, previewText: 'Tabela ASCII formatada com resumo de custos da API DeepSeek e armazenamento no GCP Secret Manager...' }
    ]
  }
];

export const INITIAL_STATUS_METRICS: SystemStatusMetric[] = [
  {
    id: 'stat-1',
    name: 'Evolution API',
    code: 'v2.4.1',
    status: 'Healthy',
    primaryStatLabel: 'Uptime (30d)',
    primaryStatValue: '99.98%',
    secondaryStatLabel: 'Latency',
    secondaryStatValue: '42ms',
    sparklineType: 'healthy'
  },
  {
    id: 'stat-2',
    name: 'Database Cluster',
    code: 'primary-node-01',
    status: 'Healthy',
    primaryStatLabel: 'Active Conns',
    primaryStatValue: '1,204',
    secondaryStatLabel: 'Query Latency',
    secondaryStatValue: '8ms',
    sparklineType: 'healthy'
  },
  {
    id: 'stat-3',
    name: 'LLM Provider',
    code: 'gpt-4-turbo / DeepSeek V4',
    status: 'Degraded',
    primaryStatLabel: 'Token Limit',
    primaryStatValue: '85%',
    secondaryStatLabel: 'Avg Latency',
    secondaryStatValue: '1,420ms',
    sparklineType: 'degraded'
  },
  {
    id: 'stat-4',
    name: 'Webhook Delivery',
    code: 'event-bus-sync',
    status: 'Healthy',
    primaryStatLabel: 'Success Rate',
    primaryStatValue: '99.9%',
    secondaryStatLabel: 'Queue Delay',
    secondaryStatValue: '12ms',
    sparklineType: 'healthy'
  },
  {
    id: 'stat-5',
    name: 'Cloud Run Service',
    code: 'agents-runtime-test (us-central1)',
    status: 'Saudável',
    primaryStatLabel: 'CPU Throttling',
    primaryStatValue: 'True (Guardrail OK)',
    secondaryStatLabel: 'Memory / Max Inst.',
    secondaryStatValue: '4 GB / 5',
    sparklineType: 'healthy',
    details: {
      'Min Instances': '0 (Scale to zero OK)',
      'Region': 'us-central1'
    }
  },
  {
    id: 'stat-6',
    name: 'Vector Database & RAG Storage',
    code: 'Firestore Vector',
    status: 'Operacional',
    primaryStatLabel: 'Index Status',
    primaryStatValue: '3 Índices OK',
    secondaryStatLabel: 'Vector Metric',
    secondaryStatValue: 'Cosine Distance',
    sparklineType: 'healthy',
    details: {
      'Collection': 'agent-knowledge-v2 / group-knowledge-v2'
    }
  }
];
