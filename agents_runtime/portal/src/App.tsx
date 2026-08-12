import { useState, useEffect } from 'react';
import {
  NavigationTab,
  WhatsAppAccount,
  Agent,
  Skill,
  Tool,
  Owner,
  Integration,
  ServiceConnection,
  KnowledgeCategory,
  SystemStatusMetric
} from './types';
import { api } from './api/client';

import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';

import { WhatsAppAccountsView } from './components/views/WhatsAppAccountsView';
import { AgentsView } from './components/views/AgentsView';
import { SkillsView } from './components/views/SkillsView';
import { ToolsView } from './components/views/ToolsView';
import { OwnersView } from './components/views/OwnersView';
import { IntegrationsView } from './components/views/IntegrationsView';
import { ConnectionsView } from './components/views/ConnectionsView';
import { KnowledgeView } from './components/views/KnowledgeView';
import { StatusView } from './components/views/StatusView';

import { EditPromptModal } from './components/modals/EditPromptModal';
import { TestToolModal } from './components/modals/TestToolModal';
import { UploadDocumentModal } from './components/modals/UploadDocumentModal';
import { ViewChunksModal } from './components/modals/ViewChunksModal';
import { NewItemModal } from './components/modals/NewItemModal';

function mapAccounts(data: any): WhatsAppAccount[] {
  return (data?.accounts || []).map((a: any) => ({
    id: a.id || a.instance || '',
    name: a.name || a.instance || a.id || '',
    phone: a.owner_phone ? '+' + a.owner_phone : '',
    ownerPhone: '+' + (a.owner_phone || ''),
    status: a.connection_status === 'open' ? 'Conectado'
          : a.connection_status === 'connecting' ? 'Aguardando QR' : 'Desconectado',
    instanceName: a.instance || a.id || '',
    updatedAt: a.updated_at || '',
  }));
}

function mapAgents(data: any): Agent[] {
  return (data?.agents || []).map((a: any) => ({
    id: a.agent_id || a.id || '',
    key: a.agent_id || a.id || '',
    name: a.name || a.agent_id || '',
    model: a.model || '',
    description: a.description || '',
    status: a.enabled === false ? 'Inactive' : 'Active',
    delegatesTo: a.delegates_to || [],
    systemPrompt: a.system_prompt || '',
  }));
}

function mapSkills(data: any): Skill[] {
  return (data?.skills || []).map((s: any) => ({
    id: s.skill_id || s.id || '',
    code: s.skill_id || s.id || '',
    name: s.name || s.skill_id || '',
    description: s.description || '',
    status: s.enabled === false ? 'INACTIVE' : 'ACTIVE',
    categoryTag: s.category || 'Skill',
  }));
}

function mapTools(data: any): Tool[] {
  return (data?.tools || []).map((t: any) => ({
    id: t.tool_id || t.id || '',
    code: t.tool_id || t.id || '',
    name: t.name || t.tool_id || '',
    category: 'Custom',
    typeFilter: (t.implementation || '').includes('composio') ? 'Composio MCP' : 'Google Native',
    description: t.description || '',
    status: t.enabled === false ? 'Inactive' : 'Active',
    permissions: [],
    samplePayload: '',
  }));
}

function mapConnections(users: any[]): ServiceConnection[] {
  const out: ServiceConnection[] = [];
  users.forEach((u) => {
    const phone = u.phone || u.id || '';
    const g = u.google || {};
    const googleSvcs: { key: string; name: string; desc: string; icon: string }[] = [
      { key: 'calendar', name: 'Agenda (Google Calendar)', desc: 'Ver e criar compromissos', icon: 'calendar_month' },
      { key: 'gmail', name: 'Email (Gmail)', desc: 'Ler e enviar emails', icon: 'mail' },
      { key: 'drive', name: 'Arquivos (Google Drive)', desc: 'Buscar e ler documentos', icon: 'folder' },
    ];
    googleSvcs.forEach((svc) => {
      out.push({
        id: `${phone}__google__${svc.key}`,
        name: svc.name,
        category: 'Conta Google',
        description: `${svc.desc} · ${phone}`,
        status: g.services && g.services[svc.key] ? 'OK' : 'Desconectado',
        icon: svc.icon,
      });
    });
    const comp = u.composio || {};
    Object.entries(comp).forEach(([slug, connected]) => {
      out.push({
        id: `${phone}__composio__${slug}`,
        name: slug,
        category: 'Outros serviços',
        description: `${slug} · ${phone}`,
        status: connected ? 'OK' : 'Desconectado',
        icon: 'hub',
      });
    });
  });
  return out;
}

function mapKnowledge(data: any): KnowledgeCategory[] {
  return (data?.documents || data?.items || []).map((d: any) => ({
    id: d.title || d.source_title || d.id || '',
    title: d.title || d.source_title || d.id || '',
    formats: d.klass || '',
    collection: d.collection || 'agent-knowledge-v2',
    classification: d.klass || d.class || '',
    fileCount: 1,
    chunkCount: d.chunk_count || 0,
    status: 'Indexado',
    chunks: [],
  }));
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('whatsapp');
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [owners] = useState<Owner[]>([]);
  const [integrations] = useState<Integration[]>([]);
  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [statusMetrics] = useState<SystemStatusMetric[]>([]);
  const [loadError, setLoadError] = useState<string>('');

  const [editingAgentPrompt, setEditingAgentPrompt] = useState<Agent | null>(null);
  const [testingTool, setTestingTool] = useState<Tool | null>(null);
  const [uploadDocOpen, setUploadDocOpen] = useState<boolean>(false);
  const [viewChunksCat, setViewChunksCat] = useState<KnowledgeCategory | null>(null);
  const [newItemModalOpen, setNewItemModalOpen] = useState<boolean>(false);

  useEffect(() => {
    (async () => {
      try {
        const [acc, ag, sk, tl, users, kn] = await Promise.all([
          api('/admin/accounts').catch(() => ({ accounts: [] })),
          api('/admin/agents').catch(() => ({ agents: [] })),
          api('/admin/skills').catch(() => ({ skills: [] })),
          api('/admin/tools').catch(() => ({ tools: [] })),
          api('/admin/users').catch(() => ({ users: [] })),
          api('/admin/knowledge').catch(() => ({ documents: [] })),
        ]);
        setAccounts(mapAccounts(acc));
        setAgents(mapAgents(ag));
        setSkills(mapSkills(sk));
        setTools(mapTools(tl));
        const usersList = (users as any)?.users || [];
        setConnections(mapConnections(usersList));
        setCategories(mapKnowledge(kn));
      } catch (e: any) {
        setLoadError(e.message || 'Falha ao carregar dados do backend');
      }
    })();
  }, []);

  const handleSaveAgent = async (updatedAgent: Agent) => {
    try {
      await api('/admin/agents', {
        method: 'POST',
        body: JSON.stringify({
          id: updatedAgent.key,
          agent_id: updatedAgent.key,
          name: updatedAgent.name,
          model: updatedAgent.model,
          description: updatedAgent.description,
          system_prompt: updatedAgent.systemPrompt,
          enabled: updatedAgent.status !== 'Inactive',
          delegates_to: updatedAgent.delegatesTo,
        }),
      });
      setAgents((prev) => prev.map((a) => (a.id === updatedAgent.id ? updatedAgent : a)));
    } catch (e: any) {
      alert('Erro ao salvar agente: ' + e.message);
    }
  };

  const handleToggleConnection = (id: string) => {
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: c.status === 'OK' ? 'Desconectado' : 'OK' } : c))
    );
  };

  const handleReindexCategory = (catId: string) => {
    setCategories((prev) =>
      prev.map((c) => (c.id === catId ? { ...c, status: 'Indexado', chunkCount: c.chunkCount + 2 } : c))
    );
  };

  const handleAddNewItem = (newItem: any) => {
    switch (activeTab) {
      case 'whatsapp':
        setAccounts((prev) => [newItem, ...prev]);
        break;
      case 'agentes':
        setAgents((prev) => [...prev, newItem]);
        break;
      case 'skills':
        setSkills((prev) => [...prev, newItem]);
        break;
      case 'tools':
        setTools((prev) => [...prev, newItem]);
        break;
      default:
        break;
    }
  };

  const getPageTitle = (): string => {
    switch (activeTab) {
      case 'whatsapp': return 'Contas WhatsApp';
      case 'agentes': return 'Agentes';
      case 'skills': return 'Skills';
      case 'tools': return 'Tools';
      case 'proprietarios': return 'Proprietários';
      case 'integracoes': return 'Integrações';
      case 'conexoes': return 'Conexões';
      case 'conhecimento': return 'Conhecimento';
      case 'status': return 'Status / Monitoramento';
    }
  };

  return (
    <div className="min-h-screen bg-[#f9f9ff] text-[#191b23] flex flex-col font-sans">
      {loadError && (
        <div style={{ background: '#fef2f2', color: '#991b1b', padding: '10px 16px', fontSize: 13, borderBottom: '1px solid #fecaca' }}>
          ⚠️ {loadError}
        </div>
      )}

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
      />

      <div className="flex-1 md:ml-64 flex flex-col min-h-screen transition-all duration-300">
        <Header
          title={getPageTitle()}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          setMobileOpen={setMobileOpen}
          onCommitClick={() => alert('Coherence Sync: Todos os módulos e agentes salvos.')}
          onDeployClick={() => alert('Rocket Deploy: Instância ativa rodando em Cloud Run.')}
        />

        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          {activeTab === 'whatsapp' && (
            <WhatsAppAccountsView
              accounts={accounts}
              onAddNew={() => setNewItemModalOpen(true)}
              onEditAccount={(acc) => {
                const newName = prompt('Editar nome da conta:', acc.name);
                if (newName) {
                  setAccounts((prev) => prev.map((a) => (a.id === acc.id ? { ...a, name: newName } : a)));
                }
              }}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'agentes' && (
            <AgentsView
              agents={agents}
              onAddNew={() => setNewItemModalOpen(true)}
              onEditPrompt={(agent) => setEditingAgentPrompt(agent)}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'skills' && (
            <SkillsView
              skills={skills}
              onAddNew={() => setNewItemModalOpen(true)}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'tools' && (
            <ToolsView
              tools={tools}
              onAddNew={() => setNewItemModalOpen(true)}
              onTestTool={(tool) => setTestingTool(tool)}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'proprietarios' && (
            <OwnersView owners={owners} onAddNew={() => setNewItemModalOpen(true)} searchQuery={searchQuery} />
          )}

          {activeTab === 'integracoes' && (
            <IntegrationsView integrations={integrations} onAddNew={() => setNewItemModalOpen(true)} searchQuery={searchQuery} />
          )}

          {activeTab === 'conexoes' && (
            <ConnectionsView
              connections={connections}
              onToggleConnection={handleToggleConnection}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'conhecimento' && (
            <KnowledgeView
              categories={categories}
              onUploadClick={() => setUploadDocOpen(true)}
              onViewChunks={(cat) => setViewChunksCat(cat)}
              onReindex={handleReindexCategory}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'status' && (
            <StatusView metrics={statusMetrics} searchQuery={searchQuery} />
          )}
        </main>
      </div>

      <EditPromptModal agent={editingAgentPrompt} onClose={() => setEditingAgentPrompt(null)} onSave={handleSaveAgent} />
      <TestToolModal tool={testingTool} onClose={() => setTestingTool(null)} />
      <UploadDocumentModal isOpen={uploadDocOpen} onClose={() => setUploadDocOpen(false)} onUpload={(newCat) => setCategories((prev) => [newCat, ...prev])} />
      <ViewChunksModal category={viewChunksCat} onClose={() => setViewChunksCat(null)} />
      <NewItemModal type={activeTab} isOpen={newItemModalOpen} onClose={() => setNewItemModalOpen(false)} onAdd={handleAddNewItem} />
    </div>
  );
}
