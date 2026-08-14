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
  SystemStatusMetric,
  CurrentUser,
  PortalUser
} from './types';
import { api, getToken, getPortalUrl } from './api/client';

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
  return (data?.tools || []).map((t: any) => {
    const id = t.tool_id || t.id || t.name || '';
    const isComposio = (t.implementation || '').includes('composio') || (t.type_filter || '').includes('composio');
    return {
      id: id,
      code: id,
      name: t.name || id,
      category: (t.category || 'Custom') as any,
      typeFilter: isComposio ? 'Composio' : 'Google Native',
      description: t.description || '',
      status: t.enabled === false ? 'Inactive' : 'Active',
      permissions: t.permissions || [],
      samplePayload: t.sample_payload || '',
    };
  });
}

function mapConnections(users: any[]): ServiceConnection[] {
  const out: ServiceConnection[] = [];
  users.forEach((u) => {
    const phone = u.phone || u.id || '';
    // Google — itera a lista dinâmica retornada pelo backend
    const g = u.google || {};
    (g.services || []).forEach((svc: any) => {
      out.push({
        id: `${phone}__google__${svc.id}`,
        name: svc.label || svc.id,
        category: 'Conta Google',
        description: svc.connected
          ? `Conectado · ${phone}`
          : `Pendente — clique para autorizar · ${phone}`,
        status: svc.connected ? 'OK' : 'Desconectado',
        icon: svc.icon || 'cloud',
      });
    });
    // Composio — itera a lista dinâmica retornada pelo backend
    const comp = u.composio || {};
    (comp.services || []).forEach((svc: any) => {
      out.push({
        id: `${phone}__composio__${svc.id}`,
        name: svc.label || svc.id,
        category: 'Outros serviços',
        description: svc.connected
          ? `Conectado · ${phone}`
          : `Pendente — clique para autorizar · ${phone}`,
        status: svc.connected ? 'OK' : 'Desconectado',
        icon: svc.icon || 'hub',
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
    ownerId: d.owner_phone || d.owner_id || '',
    fileCount: 1,
    chunkCount: d.chunk_count || 0,
    status: 'Indexado',
    chunks: [],
  }));
}

function mapOwners(data: any): Owner[] {
  return (data?.owners || []).map((o: any) => ({
    id: o.owner_uid || o.owner_phone || o.phone || '',
    name: o.display_name || o.name || o.owner_phone || o.phone || '',
    role: 'Owner',
    uid: o.owner_uid || o.owner_phone || '',
    phone: o.owner_phone || o.phone || '',
    instance: o.instance || '',
  }));
}

function mapIntegrations(data: any): Integration[] {
  return (data?.integrations || []).map((i: any) => ({
    id: i.id || '',
    name: i.name || i.id || '',
    category: i.category || 'Integração',
    status: (i.status || 'Desconectado') as any,
    details: {
      activeScopes: i.details?.active_scopes ? [`${i.details.active_scopes} scopes`] : [],
      storagePath: i.details?.storage_path || i.details?.storagePath || '',
      redirectUri: i.details?.redirect_uri || i.details?.redirectUri || '',
      apiKeySource: i.details?.api_key_source || i.details?.apiKeySource || '',
      connectedApps: i.details?.connected_apps
        ? [`${i.details.connected_apps} apps`]
        : (i.details?.connectedApps || []),
      endpoint: i.details?.endpoint || '',
      webhookInfo: i.details?.webhook_info || i.details?.webhookInfo || '',
    },
  }));
}

function mapStatus(data: any): SystemStatusMetric[] {
  const out: SystemStatusMetric[] = [];
  const kpis: any[] = Array.isArray(data?.kpis) ? data.kpis : [];
  // Info do runtime como detalhes
  const runtimeDetails: Record<string, string> = {};
  if (data?.agents_summary?.counts) {
    const c = data.agents_summary.counts;
    runtimeDetails['Agentes configurados'] = String(c.configured ?? 0);
    runtimeDetails['Agentes roteáveis'] = String(c.routable ?? 0);
    runtimeDetails['Agentes saudáveis'] = String(c.healthy ?? 0);
    runtimeDetails['Execuções em voo'] = String(c.in_flight ?? 0);
  }
  if (data?.llm?.provider) runtimeDetails['LLM Provider'] = data.llm.provider;
  if (data?.llm?.model) runtimeDetails['Modelo'] = data.llm.model;
  if (data?.stt?.primary) runtimeDetails['STT Primário'] = data.stt.primary;
  kpis.forEach((k, idx) => {
    const val = String(k.value ?? '—');
    const isHealthyMetric = String(k.label || '').includes('healthy');
    out.push({
      id: `kpi-${idx}`,
      name: (k.label || '').replace(/_/g, ' '),
      code: val,
      status: data?.runtime_ok ? 'Healthy' : (isHealthyMetric && Number(val) === 0 ? 'Degraded' : 'Healthy'),
      primaryStatLabel: k.label || '',
      primaryStatValue: val,
      secondaryStatLabel: k.sub || '',
      secondaryStatValue: k.sub ? '—' : '',
      sparklineType: data?.runtime_ok ? 'healthy' : 'degraded',
      details: runtimeDetails,
    });
  });
  return out;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('whatsapp');
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [rawUsers, setRawUsers] = useState<PortalUser[]>([]);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [statusMetrics, setStatusMetrics] = useState<SystemStatusMetric[]>([]);
  const [loadError, setLoadError] = useState<string>('');

  const [editingAgentPrompt, setEditingAgentPrompt] = useState<Agent | null>(null);
  const [testingTool, setTestingTool] = useState<Tool | null>(null);
  const [uploadDocOpen, setUploadDocOpen] = useState<boolean>(false);
  const [viewChunksCat, setViewChunksCat] = useState<KnowledgeCategory | null>(null);
  const [newItemModalOpen, setNewItemModalOpen] = useState<boolean>(false);

  useEffect(() => {
    if (!getToken()) {
      // Acesso direto ao modulo sem token: redireciona para o Portal Coherence.
      window.location.href = getPortalUrl();
      return;
    }
    (async () => {
      const fetchSafe = async (path: string, fallback: any) => {
        try {
          return await api(path);
        } catch (e: any) {
          if (path === '/admin/me' && e.status === 401) {
            setLoadError('Sessão expirada. Faça login novamente no Portal Coherence.');
          }
          return fallback;
        }
      };
      try {
        const me = await fetchSafe('/admin/me', { role: 'agent_user', phone: '', is_admin: false });
        const curUser: CurrentUser = {
          role: me?.role || 'agent_user',
          phone: me?.phone || '',
          isAdmin: Boolean(me?.is_admin),
          email: me?.email || '',
          name: me?.name || '',
          picture: me?.picture || '',
        };
        setCurrentUser(curUser);

        if (!curUser.isAdmin) {
          setActiveTab('conexoes');
          const [acc, ag, users, kn, st] = await Promise.all([
            fetchSafe('/admin/accounts', { accounts: [] }),
            fetchSafe('/admin/agents', { agents: [] }),
            fetchSafe('/admin/users', { users: [] }),
            fetchSafe('/admin/knowledge', { documents: [] }),
            fetchSafe('/admin/status', {}),
          ]);
          setAccounts(mapAccounts(acc));
          setAgents(mapAgents(ag));
          const usersList = (users as any)?.users || [];
          setRawUsers(
            usersList.map((u: any) => ({
              id: u.phone || u.id || '',
              phone: u.phone || u.id || '',
              name: u.name || u.push_name || '',
              role: u.role || 'agent_user',
              email: u.email || '',
            }))
          );
          setConnections(mapConnections(usersList));
          setCategories(mapKnowledge(kn));
          setStatusMetrics(mapStatus(st as any));
        } else {
          const [acc, ag, sk, tl, users, kn, ow, integ, st] = await Promise.all([
            fetchSafe('/admin/accounts', { accounts: [] }),
            fetchSafe('/admin/agents', { agents: [] }),
            fetchSafe('/admin/skills', { skills: [] }),
            fetchSafe('/admin/tools', { tools: [] }),
            fetchSafe('/admin/users', { users: [] }),
            fetchSafe('/admin/knowledge', { documents: [] }),
            fetchSafe('/admin/owners', { owners: [] }),
            fetchSafe('/admin/integrations', { integrations: [] }),
            fetchSafe('/admin/status', {}),
          ]);
          setAccounts(mapAccounts(acc));
          setAgents(mapAgents(ag));
          setSkills(mapSkills(sk));
          setTools(mapTools(tl));
          const usersList = (users as any)?.users || [];
          setRawUsers(
            usersList.map((u: any) => ({
              id: u.phone || u.id || '',
              phone: u.phone || u.id || '',
              name: u.name || u.push_name || '',
              role: u.role || 'agent_user',
              email: u.email || '',
            }))
          );
          setConnections(mapConnections(usersList));
          setCategories(mapKnowledge(kn));
          setOwners(mapOwners(ow));
          setIntegrations(mapIntegrations(integ));
          setStatusMetrics(mapStatus(st as any));
        }
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

  const refreshConnections = async () => {
    try {
      const users: any = await api('/admin/users');
      const usersList = users?.users || [];
      setConnections(mapConnections(usersList));
      return true;
    } catch {
      return false;
    }
  };

  const authorizeGoogle = (phone: string) => {
    const base = window.location.origin;
    // Abre 1 aba apenas. Apos autorizar, o callback do OAuth volta e a
    // pagina recarrega via polling do refreshConnections.
    window.open(`${base}/oauth/google?phone=${encodeURIComponent(phone)}`, '_blank');
    const timer = setInterval(async () => {
      const users: any = await api('/admin/users').catch(() => null);
      if (users) {
        const usersList = users?.users || [];
        const updated = mapConnections(usersList);
        setConnections(updated);
        // Verifica se os servicos do phone agora estao conectados
        const user = usersList.find((u: any) => (u.phone || '') === phone);
        const allConnected = user && user.google && user.google.services &&
          user.google.services.every((s: any) => s.connected || !s.needs_scope);
        if (allConnected || user?.google?.scopes_loaded === user?.google?.scopes_total) {
          clearInterval(timer);
          alert('Google conectado! ✅');
        }
      }
    }, 3000);
    setTimeout(() => clearInterval(timer), 120000);
  };

  const authorizeComposio = async (phone: string) => {
    try {
      const base = window.location.origin;
      const res: any = await api(`${base}/a/${encodeURIComponent(phone)}/composio`, { method: 'POST' });
      const links = (res && res.links) || [];
      const pendentes = links.filter((l: any) => l.url);
      if (pendentes.length) {
        // Abre apenas a PRIMEIRA aba pendente (evita muitas abas).
        window.open(pendentes[0].url, '_blank');
        alert(`Autorize o app ${pendentes[0].toolkit || ''}. Depois volte aqui e clique novamente para o próximo.`);
      } else {
        alert('Todos os apps já estão conectados! ✅');
        await refreshConnections();
      }
    } catch (e: any) {
      alert('Erro ao iniciar Composio: ' + e.message);
    }
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
        <div style={{ background: '#fef2f2', color: '#991b1b', padding: '10px 16px', fontSize: 13, borderBottom: '1px solid #fecaca', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ flex: 1 }}>⚠️ {loadError}</span>
          <button
            onClick={() => window.location.href = window.location.origin + '/'}
            style={{ background: '#991b1b', color: '#fff', border: 0, padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
          >
            Refazer login
          </button>
        </div>
      )}

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        currentUser={currentUser}
        hasOwnInstance={accounts.length > 0}
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
              users={rawUsers}
              currentUser={currentUser}
              onToggleConnection={handleToggleConnection}
              onAuthorizeGoogle={authorizeGoogle}
              onAuthorizeComposio={authorizeComposio}
              searchQuery={searchQuery}
            />
          )}

          {activeTab === 'conhecimento' && (
            <KnowledgeView
              categories={categories}
              currentUser={currentUser}
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
