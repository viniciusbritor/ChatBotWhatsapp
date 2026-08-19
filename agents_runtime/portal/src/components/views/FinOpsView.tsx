import React, { useState, useEffect } from 'react';
import { CurrentUser } from '../../types';
import { api } from '../../api/client';
import { ShieldAlert, ShieldCheck, DollarSign, MessageSquare, Users, AlertTriangle, RefreshCw, Lock, Unlock, Search } from 'lucide-react';

interface FinOpsUser {
  phone: string;
  name: string;
  email?: string;
  role: string;
  total_messages: number;
  total_tokens_input: number;
  total_tokens_output: number;
  estimated_cost_usd: number;
  estimated_cost_brl: number;
  is_quarantined: boolean;
  quarantine_reason?: string;
  quarantined_at?: string;
  last_active_at?: string;
  groups: string[];
  instance: string;
}

interface FinOpsOverview {
  total_cost_usd: number;
  total_cost_brl: number;
  total_messages: number;
  active_users_count: number;
  quarantined_users_count: number;
  users: FinOpsUser[];
}

interface FinOpsViewProps {
  currentUser?: CurrentUser | null;
  searchQuery: string;
}

export const FinOpsView: React.FC<FinOpsViewProps> = ({
  currentUser,
  searchQuery,
}) => {
  const [data, setData] = useState<FinOpsOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedInstance, setSelectedInstance] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'quarantined'>('all');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchFinOps = async () => {
    setLoading(true);
    try {
      const url = selectedInstance === 'all'
        ? '/admin/finops/overview'
        : `/admin/finops/overview?instance=${encodeURIComponent(selectedInstance)}`;
      const json = await api<FinOpsOverview>(url);
      if (json) {
        setData(json);
      }
    } catch (err) {
      console.error('Failed to load FinOps overview', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFinOps();
  }, [selectedInstance]);

  const handleToggleBlock = async (phone: string, currentlyBlocked: boolean) => {
    setActionLoading(phone);
    setActionMessage(null);
    try {
      const endpoint = currentlyBlocked ? `/admin/users/${phone}/unblock` : `/admin/users/${phone}/block`;
      await api(endpoint, { method: 'POST' });
      setActionMessage(`Usuário +${phone} ${currentlyBlocked ? 'desbloqueado' : 'bloqueado'} com sucesso!`);
      await fetchFinOps();
    } catch (err) {
      setActionMessage(`Erro ao alterar status de +${phone}`);
    } finally {
      setActionLoading(null);
      setTimeout(() => setActionMessage(null), 4000);
    }
  };

  const q = (searchQuery || '').toLowerCase();


  const filteredUsers = (data?.users || []).filter((u) => {
    const matchSearch =
      (u.name || '').toLowerCase().includes(q) ||
      (u.phone || '').includes(q) ||
      (u.email || '').toLowerCase().includes(q) ||
      (u.groups || []).some(g => {
        const str = typeof g === 'object' && g ? ((g as any).subject || (g as any).gid || '') : String(g || '');
        return str.toLowerCase().includes(q);
      });

    if (!matchSearch) return false;

    if (statusFilter === 'active') return !u.is_quarantined;
    if (statusFilter === 'quarantined') return u.is_quarantined;
    return true;
  });


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white dark:bg-[#191b23] p-6 rounded-2xl border border-[#c2c6d6]/40">
        <div>
          <h2 className="text-2xl font-bold text-[#191b23] dark:text-white flex items-center gap-3">
            <DollarSign className="w-7 h-7 text-emerald-600" />
            FinOps & Escudo de Segurança (Anti-Flood)
          </h2>
          <p className="text-[#424754] dark:text-[#c2c6d6] text-sm mt-1">
            Monitoramento de custos em tempo real, detecção de ataques de bots e controle de bloqueio de usuários.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedInstance}
            onChange={(e) => setSelectedInstance(e.target.value)}
            className="bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] text-[#191b23] dark:text-white text-sm rounded-xl px-4 py-2.5 outline-none focus:border-emerald-500 transition-colors"
          >
            <option value="all">Todas as Contas (WhatsApp)</option>
            <option value="Jennifer">Instância Jennifer</option>
          </select>
          <button
            onClick={fetchFinOps}
            disabled={loading}
            className="flex items-center gap-2 bg-[#ecedf7] dark:bg-[#2e3038] hover:bg-[#d8e2ff] dark:hover:bg-[#424754] text-[#191b23] dark:text-white px-4 py-2.5 rounded-xl text-sm font-medium border border-[#c2c6d6] transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 px-5 py-3 rounded-xl text-sm flex items-center justify-between">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage(null)} className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-800 text-xs font-semibold">✕</button>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Custo Total */}
        <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6]/40 p-5 rounded-2xl relative overflow-hidden group hover:border-emerald-500/50 transition-all">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs font-semibold uppercase tracking-wider">Custo Total Estimado</p>
              <h3 className="text-2xl font-bold text-[#191b23] dark:text-white mt-1">
                {data?.total_cost_usd?.toFixed(4) || '0.0000'} <span className="text-sm font-normal text-emerald-600 dark:text-emerald-400">USD</span>
              </h3>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs mt-1">
                ≈ R$ {data?.total_cost_brl?.toFixed(2) || '0.00'} reais
              </p>
            </div>
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-600 dark:text-emerald-400">
              <DollarSign className="w-5 h-5" />
            </div>
          </div>
        </div>

        {/* Card 2: Total de Mensagens */}
        <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6]/40 p-5 rounded-2xl relative overflow-hidden group hover:border-blue-500/50 transition-all">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs font-semibold uppercase tracking-wider">Mensagens Processadas</p>
              <h3 className="text-2xl font-bold text-[#191b23] dark:text-white mt-1">
                {data?.total_messages?.toLocaleString() || 0}
              </h3>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs mt-1">Interações no WhatsApp</p>
            </div>
            <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-600 dark:text-blue-400">
              <MessageSquare className="w-5 h-5" />
            </div>
          </div>
        </div>

        {/* Card 3: Usuários em Quarentena */}
        <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6]/40 p-5 rounded-2xl relative overflow-hidden group hover:border-red-500/50 transition-all">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs font-semibold uppercase tracking-wider">Em Quarentena (Bloqueados)</p>
              <h3 className="text-2xl font-bold text-[#191b23] dark:text-white mt-1">
                {data?.quarantined_users_count || 0}
              </h3>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs mt-1">Gatilho de Flood ou Manual</p>
            </div>
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-600 dark:text-red-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
          </div>
        </div>

        {/* Card 4: Usuários Ativos */}
        <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6]/40 p-5 rounded-2xl relative overflow-hidden group hover:border-purple-500/50 transition-all">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs font-semibold uppercase tracking-wider">Contatos Ativos</p>
              <h3 className="text-2xl font-bold text-[#191b23] dark:text-white mt-1">
                {data?.active_users_count || 0}
              </h3>
              <p className="text-[#424754] dark:text-[#c2c6d6] text-xs mt-1">Interagindo normalmente</p>
            </div>
            <div className="p-3 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-600 dark:text-purple-400">
              <Users className="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#ecedf7] dark:bg-[#2e3038] p-1 rounded-xl border border-[#c2c6d6]">
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              statusFilter === 'all'
                ? 'bg-white dark:bg-[#191b23] text-[#191b23] dark:text-white shadow-sm border border-[#c2c6d6]'
                : 'text-[#424754] dark:text-[#c2c6d6] hover:text-[#191b23] dark:hover:text-white'
            }`}
          >
            Todos os Contatos ({(data?.users || []).length})
          </button>
          <button
            onClick={() => setStatusFilter('active')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              statusFilter === 'active'
                ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                : 'text-[#424754] dark:text-[#c2c6d6] hover:text-[#191b23] dark:hover:text-white'
            }`}
          >
            Ativos ({data?.active_users_count || 0})
          </button>
          <button
            onClick={() => setStatusFilter('quarantined')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              statusFilter === 'quarantined'
                ? 'bg-red-500/20 text-red-700 dark:text-red-300 border border-red-500/30'
                : 'text-[#424754] dark:text-[#c2c6d6] hover:text-[#191b23] dark:hover:text-white'
            }`}
          >
            Em Quarentena ({data?.quarantined_users_count || 0})
          </button>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#c2c6d6]/30 bg-[#f2f3fd] dark:bg-[#2e3038] text-[#424754] dark:text-[#c2c6d6] text-xs font-semibold uppercase tracking-wider">
                <th className="py-4 px-6">Contato / Telefone</th>
                <th className="py-4 px-6">Grupos de Origem</th>
                <th className="py-4 px-6">Mensagens</th>
                <th className="py-4 px-6">Tokens (In / Out)</th>
                <th className="py-4 px-6">Custo Estimado</th>
                <th className="py-4 px-6">Status</th>
                <th className="py-4 px-6 text-right">Ação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#c2c6d6]/30 text-sm">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-[#727785]">
                    Nenhum contato encontrado com os filtros aplicados.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((u) => {
                  const isBlocked = u.is_quarantined;
                  return (
                    <tr key={u.phone} className="hover:bg-[#f2f3fd] dark:hover:bg-[#2e3038] transition-colors">
                      {/* Contato */}
                      {/* Contato */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs ${
                            u.phone === '5511917389901' || u.role === 'bot'
                              ? 'bg-blue-500/20 text-blue-700 dark:text-blue-400 border border-blue-500/40'
                              : isBlocked
                              ? 'bg-red-500/20 text-red-700 dark:text-red-400 border border-red-500/40'
                              : 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-500/40'
                          }`}>
                            {u.phone === '5511917389901' || u.role === 'bot' ? '🤖' : (u.name ? u.name.charAt(0).toUpperCase() : '+')}
                          </div>
                          <div>
                            <div className="font-medium text-[#191b23] dark:text-white flex items-center gap-2">
                              {u.name}
                              {(u.phone === '5511917389901' || u.role === 'bot') && (
                                <span className="bg-blue-500/20 text-blue-700 dark:text-blue-300 text-[10px] font-bold px-2 py-0.5 rounded-full border border-blue-500/30">Bot Assistente</span>
                              )}
                              {u.role === 'admin' && (
                                <span className="bg-purple-500/20 text-purple-700 dark:text-purple-300 text-[10px] font-bold px-2 py-0.5 rounded-full border border-purple-500/30">Admin</span>
                              )}
                            </div>
                            <div className="text-xs text-[#727785] font-mono mt-0.5">+{u.phone}</div>
                          </div>
                        </div>
                      </td>

                      {/* Grupos */}
                      <td className="py-4 px-6">
                        {u.groups && u.groups.length > 0 ? (
                          <div className="flex flex-wrap gap-1 max-w-xs">
                            {u.groups.slice(0, 2).map((g, idx) => {
                              const gName = typeof g === 'object' && g ? ((g as any).subject || (g as any).gid || '') : String(g || '');
                              return (
                                <span key={idx} className="bg-[#ecedf7] dark:bg-[#2e3038] text-[#424754] dark:text-[#c2c6d6] text-[11px] px-2 py-0.5 rounded-md border border-[#c2c6d6] truncate max-w-[140px]">
                                  {gName.replace('@g.us', '').slice(0, 16)}
                                </span>
                              );
                            })}
                            {u.groups.length > 2 && (
                              <span className="text-[10px] text-[#727785] self-center">+{u.groups.length - 2}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-[#727785]">Apenas DM</span>
                        )}
                      </td>


                      {/* Mensagens */}
                      <td className="py-4 px-6 text-[#191b23] dark:text-[#c2c6d6] font-medium">
                        {u.total_messages} msgs
                      </td>

                      {/* Tokens */}
                      <td className="py-4 px-6 text-xs text-[#424754] dark:text-[#c2c6d6] font-mono">
                        <div>{u.total_tokens_input.toLocaleString()} in</div>
                        <div className="text-[#727785]">{u.total_tokens_output.toLocaleString()} out</div>
                      </td>

                      {/* Custo */}
                      <td className="py-4 px-6">
                        <div className="font-semibold text-emerald-700 dark:text-emerald-400 font-mono">
                          {u.estimated_cost_usd.toFixed(4)} USD
                        </div>
                        <div className="text-xs text-[#424754] dark:text-[#727785] mt-0.5">
                          ≈ R$ {u.estimated_cost_brl.toFixed(2)}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-4 px-6">
                        {u.phone === '5511917389901' || u.role === 'bot' ? (
                          <span className="inline-flex items-center gap-1.5 bg-blue-500/10 text-blue-700 dark:text-blue-400 border border-blue-500/30 text-xs font-semibold px-2.5 py-1 rounded-full">
                            <ShieldCheck className="w-3.5 h-3.5" />
                            Bot (Protegido)
                          </span>
                        ) : isBlocked ? (
                          <span className="inline-flex items-center gap-1.5 bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/30 text-xs font-semibold px-2.5 py-1 rounded-full">
                            <ShieldAlert className="w-3.5 h-3.5" />
                            Quarentena
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 text-xs font-semibold px-2.5 py-1 rounded-full">
                            <ShieldCheck className="w-3.5 h-3.5" />
                            Ativo
                          </span>
                        )}
                      </td>

                      {/* Ação */}
                      <td className="py-4 px-6 text-right">
                        {u.phone === '5511917389901' || u.role === 'bot' ? (
                          <span className="text-xs text-blue-600 dark:text-blue-400 font-medium italic">Imune</span>
                        ) : (
                          <button
                            onClick={() => handleToggleBlock(u.phone, isBlocked)}
                            disabled={actionLoading === u.phone}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-50 ${
                              isBlocked
                                ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm'
                                : 'bg-[#ecedf7] dark:bg-[#2e3038] hover:bg-red-500/20 text-[#191b23] dark:text-[#c2c6d6] hover:text-red-700 dark:hover:text-red-300 border border-[#c2c6d6] hover:border-red-500/30'
                            }`}
                          >
                            {actionLoading === u.phone ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : isBlocked ? (
                              <>
                                <Unlock className="w-3.5 h-3.5" />
                                Desbloquear
                              </>
                            ) : (
                              <>
                                <Lock className="w-3.5 h-3.5" />
                                Bloquear
                              </>
                            )}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
