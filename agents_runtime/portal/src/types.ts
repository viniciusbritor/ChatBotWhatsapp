export type NavigationTab =
  | 'whatsapp'
  | 'agentes'
  | 'skills'
  | 'tools'
  | 'proprietarios'
  | 'integracoes'
  | 'conexoes'
  | 'conhecimento'
  | 'status';

export interface WhatsAppAccount {
  id: string;
  name: string;
  phone: string;
  ownerPhone: string;
  status: 'Conectado' | 'Desconectado' | 'Aguardando QR';
  instanceName: string;
  updatedAt: string;
}

export interface Agent {
  id: string;
  key: string; // e.g. 'jennifier'
  name: string;
  model: string; // e.g. 'deepseek-v4-flash'
  description: string;
  status: 'Active' | 'Inactive';
  delegatesTo?: string[];
  systemPrompt: string;
  temperature?: number;
}

export interface Skill {
  id: string;
  code: string; // e.g. 'pdf', 'docx'
  name: string;
  description: string;
  status: 'ACTIVE' | 'INACTIVE';
  categoryTag: string; // e.g. 'Knowledge / Parsing'
  documentationUrl?: string;
  detailedDoc?: string;
}

export interface Tool {
  id: string;
  code: string; // e.g. 'calendar.read_events'
  name: string;
  category: 'Google Calendar' | 'Gmail' | 'Google Drive' | 'Composio' | 'Custom';
  typeFilter: 'Google Native' | 'Composio';
  description: string;
  status: 'Active' | 'Inactive';
  permissions: string[];
  samplePayload: string;
}

export interface Owner {
  id: string;
  name: string;
  role: string;
  uid: string;
  phone: string;
  instance: string;
}

export interface Integration {
  id: string;
  name: string;
  category: string;
  status: 'Conectado' | 'Ativo' | 'Desconectado';
  details: {
    activeScopes?: string[];
    storagePath?: string;
    redirectUri?: string;
    apiKeySource?: string;
    connectedApps?: string[];
    endpoint?: string;
    webhookInfo?: string;
  };
}

export interface ServiceConnection {
  id: string;
  name: string;
  category: 'Conta Google' | 'Outros serviços';
  description: string;
  status: 'OK' | 'Desconectado';
  icon: string;
}

export interface KnowledgeCategory {
  id: string;
  title: string;
  formats: string;
  collection: string;
  classification: string;
  ownerId?: string;
  fileCount: number;
  chunkCount: number;
  status: 'Indexado' | 'Em processamento' | 'Pendente';
  chunks: {
    id: string;
    filename: string;
    score: number;
    previewText: string;
  }[];
}

export interface SystemStatusMetric {
  id: string;
  name: string;
  code: string;
  status: 'Healthy' | 'Degraded' | 'Operacional' | 'Saudável';
  primaryStatLabel: string;
  primaryStatValue: string;
  secondaryStatLabel: string;
  secondaryStatValue: string;
  sparklineType: 'healthy' | 'degraded' | 'flat';
  details?: Record<string, string>;
}
