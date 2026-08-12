import React, { useState } from 'react';
import { ServiceConnection } from '../../types';

interface ConnectionsViewProps {
  connections: ServiceConnection[];
  onToggleConnection: (id: string) => void;
  searchQuery: string;
}

export const ConnectionsView: React.FC<ConnectionsViewProps> = ({
  connections,
  onToggleConnection,
  searchQuery
}) => {
  const [selectedUser, setSelectedUser] = useState('+5511966830020');

  const googleConns = connections.filter(
    (c) =>
      c.category === 'Conta Google' &&
      (c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const otherConns = connections.filter(
    (c) =>
      c.category === 'Outros serviços' &&
      (c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header Banner */}
      <div className="bg-white dark:bg-[#191b23] p-6 rounded-2xl shadow-xs border border-[#c2c6d6]/40 space-y-4">
        <h2 className="text-[32px] font-bold text-[#191b23] dark:text-white tracking-tight">
          Conexões
        </h2>
        <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6]">
          Serviços que a Jennifer pode acessar por você — conecte sua conta para liberar cada funcionalidade
        </p>

        <div className="flex items-center gap-3 pt-2">
          <label htmlFor="user-select" className="text-[14px] font-semibold text-[#191b23] dark:text-white">
            Usuário:
          </label>
          <select
            id="user-select"
            value={selectedUser}
            onChange={(e) => setSelectedUser(e.target.value)}
            className="bg-[#f9f9ff] dark:bg-[#2e3038] border border-[#c2c6d6] text-[#191b23] dark:text-white rounded-xl px-4 py-1.5 font-mono text-[13px] shadow-2xs focus:ring-2 focus:ring-[#0058be]"
          >
            <option value="+5511966830020">+5511966830020</option>
            <option value="+5511998765432">+5511998765432</option>
            <option value="+5511988776655">+5511988776655</option>
          </select>
        </div>
      </div>

      {/* Conta Google Section */}
      <div className="space-y-3">
        <h3 className="text-[20px] font-bold text-[#191b23] dark:text-white">
          Conta Google
        </h3>
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
                <button className="text-[#0058be] font-semibold text-[12px] hover:bg-[#d8e2ff]/30 px-3 py-1 rounded-lg transition-colors border border-[#0058be]/20">
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
                <button className="text-[#0058be] font-semibold text-[12px] hover:bg-[#d8e2ff]/30 px-3 py-1 rounded-lg transition-colors border border-[#0058be]/20 shrink-0">
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
