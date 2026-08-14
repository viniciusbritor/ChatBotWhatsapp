import React, { useState, useEffect } from 'react';
import { ServiceConnection, CurrentUser } from '../../types';

interface ConnectionsViewProps {
  connections: ServiceConnection[];
  users?: Array<{ phone: string; name?: string; id?: string }>;
  currentUser?: CurrentUser | null;
  onToggleConnection: (id: string) => void;
  onAuthorizeGoogle: (phone: string) => void;
  onAuthorizeComposio: (phone: string) => void;
  searchQuery: string;
}

export const ConnectionsView: React.FC<ConnectionsViewProps> = ({
  connections,
  users = [],
  currentUser,
  onToggleConnection,
  onAuthorizeGoogle,
  onAuthorizeComposio,
  searchQuery
}) => {
  const defaultPhone = () => {
    if (currentUser?.phone) {
      return currentUser.phone.startsWith('+') ? currentUser.phone : '+' + currentUser.phone;
    }
    if (users.length > 0 && users[0].phone) {
      return users[0].phone.startsWith('+') ? users[0].phone : '+' + users[0].phone;
    }
    return '+5511966830020';
  };

  const [selectedUser, setSelectedUser] = useState<string>(defaultPhone);

  useEffect(() => {
    if (currentUser?.phone) {
      const formatted = currentUser.phone.startsWith('+') ? currentUser.phone : '+' + currentUser.phone;
      setSelectedUser(formatted);
    } else if (users.length > 0 && !users.some(u => (u.phone.startsWith('+') ? u.phone : '+' + u.phone) === selectedUser)) {
      setSelectedUser(users[0].phone.startsWith('+') ? users[0].phone : '+' + users[0].phone);
    }
  }, [currentUser, users]);

  const cleanSelectedPhone = selectedUser.replace(/\D/g, '');

  const userConns = connections.filter((c) => {
    if (!cleanSelectedPhone) return true;
    return c.id.startsWith(cleanSelectedPhone + '__');
  });

  const googleConns = userConns.filter(
    (c) =>
      c.category === 'Conta Google' &&
      (c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const otherConns = userConns.filter(
    (c) =>
      c.category === 'Outros serviços' &&
      (c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const [inviteStatus, setInviteStatus] = useState<string | null>(null);
  const [inviting, setInviting] = useState<boolean>(false);

  const handleSendInvite = async () => {
    if (!cleanSelectedPhone) return;
    setInviting(true);
    try {
      const tok = sessionStorage.getItem('_ctok') || new URLSearchParams(location.search).get('token') || '';
      const res = await fetch(`/admin/users/${cleanSelectedPhone}/invite?token=${tok}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setInviteStatus(`Convite enviado via WhatsApp para +${cleanSelectedPhone}!`);
      } else {
        setInviteStatus(`Erro ao enviar convite: ${data.message || 'Falha na Evolution API'}`);
      }
    } catch (e: any) {
      setInviteStatus(`Falha de rede ao disparar convite.`);
    } finally {
      setInviting(false);
      setTimeout(() => setInviteStatus(null), 4000);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Toast Alert */}
      {inviteStatus && (
        <div className="fixed top-20 right-8 z-50 bg-[#191b23] text-[#a3efcf] px-4 py-3 rounded-xl shadow-2xl text-[13px] font-mono border border-[#a3efcf]">
          💬 {inviteStatus}
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-white dark:bg-[#191b23] p-6 rounded-2xl shadow-xs border border-[#c2c6d6]/40 space-y-4">
        <h2 className="text-[32px] font-bold text-[#191b23] dark:text-white tracking-tight">
          Conexões
        </h2>
        <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6]">
          Serviços que a Jennifer pode acessar por você — conecte sua conta para liberar cada funcionalidade
        </p>

        <div className="flex flex-wrap items-center gap-3 pt-2">
          <label htmlFor="user-select" className="text-[14px] font-semibold text-[#191b23] dark:text-white">
            Usuário:
          </label>
          {isAdmin ? (
            <div className="flex flex-wrap items-center gap-3">
              <select
                id="user-select"
                value={selectedUser}
                onChange={(e) => setSelectedUser(e.target.value)}
                className="bg-[#f9f9ff] dark:bg-[#2e3038] border border-[#c2c6d6] text-[#191b23] dark:text-white rounded-xl px-4 py-1.5 font-mono text-[13px] shadow-2xs focus:ring-2 focus:ring-[#0058be]"
              >
                {users.length > 0 ? (
                  users.map((u) => {
                    const val = u.phone.startsWith('+') ? u.phone : '+' + u.phone;
                    const label = u.name ? `${u.name} (${val})` : val;
                    return (
                      <option key={u.phone} value={val}>
                        {label}
                      </option>
                    );
                  })
                ) : (
                  <option value={selectedUser}>{selectedUser}</option>
                )}
              </select>
              <button
                onClick={handleSendInvite}
                disabled={inviting}
                className="bg-[#196b52] hover:bg-[#145541] disabled:opacity-50 text-white font-semibold text-[12px] px-3 py-1.5 rounded-xl transition-all flex items-center gap-1.5 shadow-xs"
              >
                <span className="material-symbols-outlined text-[16px]">send</span>
                {inviting ? 'Enviando...' : 'Enviar convite no WhatsApp'}
              </button>
            </div>
          ) : (
            <span className="bg-[#ecedf7] dark:bg-[#2e3038] px-3 py-1 rounded-lg font-mono text-[13px] text-[#0058be] dark:text-[#adc6ff] font-semibold">
              {currentUser?.name ? `${currentUser.name} (${selectedUser})` : selectedUser}
            </span>
          )}
        </div>
      </div>

      {/* Conta Google Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[20px] font-bold text-[#191b23] dark:text-white">
            Conta Google
          </h3>
          <button
            onClick={() => onAuthorizeGoogle(selectedUser.replace('+', ''))}
            className="text-[#0058be] font-semibold text-[12px] hover:bg-[#d8e2ff]/30 px-3 py-1 rounded-lg transition-colors border border-[#0058be]/20"
          >
            Atualizar permissões
          </button>
        </div>
        <div className="flex flex-col gap-3">
          {googleConns.map((conn) => (
            <div
              key={conn.id}
              onClick={() => onToggleConnection(conn.id)}
              className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] dark:border-[#2e3038] rounded-2xl p-4 flex items-center justify-between hover:shadow-md transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-[#ecedf7] dark:bg-[#2e3038] flex items-center justify-center rounded-xl group-hover:bg-[#d8e2ff]/50 transition-colors text-[#0058be]">
                  <span className="material-symbols-outlined text-[22px]">{conn.icon}</span>
                </div>
                <div>
                  <h4 className="text-[15px] font-bold text-[#191b23] dark:text-white">
                    {conn.name}
                  </h4>
                  <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6]">{conn.description}</p>
                </div>
              </div>

              {conn.status === 'OK' ? (
                <div className="bg-[#196b52]/10 px-3 py-1 rounded-full flex items-center gap-1.5 border border-[#196b52]/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></span>
                  <span className="text-[11px] font-semibold text-[#196b52] tracking-wider">OK</span>
                </div>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    const parts = conn.id.split('__');
                    const phone = parts[0] || '';
                    if (conn.category === 'Conta Google') onAuthorizeGoogle(phone);
                    else onAuthorizeComposio(phone);
                  }}
                  className="text-[#0058be] font-semibold text-[12px] hover:bg-[#d8e2ff]/30 px-3 py-1 rounded-lg transition-colors border border-[#0058be]/20"
                >
                  Conectar
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Outros Serviços Section */}
      <div className="space-y-3">
        <h3 className="text-[20px] font-bold text-[#191b23] dark:text-white">
          Outros serviços
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {otherConns.map((conn) => (
            <div
              key={conn.id}
              onClick={() => onToggleConnection(conn.id)}
              className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] dark:border-[#2e3038] rounded-2xl p-4 flex items-center justify-between hover:shadow-md transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-[#ecedf7] dark:bg-[#2e3038] flex items-center justify-center rounded-xl group-hover:bg-[#d8e2ff]/50 transition-colors text-[#191b23] dark:text-white">
                  <span className="material-symbols-outlined text-[22px]">{conn.icon}</span>
                </div>
                <div>
                  <h4 className="text-[15px] font-bold text-[#191b23] dark:text-white">
                    {conn.name}
                  </h4>
                  <p className="text-[12px] text-[#424754] dark:text-[#c2c6d6]">{conn.description}</p>
                </div>
              </div>

              {conn.status === 'OK' ? (
                <div className="bg-[#196b52]/10 px-3 py-1 rounded-full flex items-center gap-1.5 border border-[#196b52]/20 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></span>
                  <span className="text-[11px] font-semibold text-[#196b52] tracking-wider">OK</span>
                </div>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    const parts = conn.id.split('__');
                    const phone = parts[0] || '';
                    if (conn.category === 'Conta Google') onAuthorizeGoogle(phone);
                    else onAuthorizeComposio(phone);
                  }}
                  className="text-[#0058be] font-semibold text-[12px] hover:bg-[#d8e2ff]/30 px-3 py-1 rounded-lg transition-colors border border-[#0058be]/20 shrink-0"
                >
                  Conectar
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
