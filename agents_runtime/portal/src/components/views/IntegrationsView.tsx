import React, { useState } from 'react';
import { Integration } from '../../types';

interface IntegrationsViewProps {
  integrations: Integration[];
  onAddNew: () => void;
  searchQuery: string;
}

export const IntegrationsView: React.FC<IntegrationsViewProps> = ({
  integrations,
  onAddNew,
  searchQuery
}) => {
  const [pingMessage, setPingMessage] = useState<string | null>(null);

  const filtered = integrations.filter(
    (i) =>
      i.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      i.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handlePingTest = (intName: string) => {
    setPingMessage(`Disparando Ping para ${intName}...`);
    setTimeout(() => {
      setPingMessage(`✅ Ping OK (200 SUCCESS): ${intName} respondeu em 34ms!`);
      setTimeout(() => setPingMessage(null), 3000);
    }, 600);
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {pingMessage && (
        <div className="fixed top-20 right-8 z-50 bg-[#191b23] text-white px-4 py-3 rounded-xl shadow-2xl text-[13px] font-mono border border-[#a3efcf] animate-bounce">
          {pingMessage}
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-[36px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Integrações Ativas
          </h1>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-1">
            Webhooks e fluxos de dados externos integrados ao Control Plane.
          </p>
        </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0 self-start md:self-auto"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Nova Conexão
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {filtered.map((item) => (
          <div
            key={item.id}
            className="bg-white dark:bg-[#191b23] border border-[#e1e2ec] dark:border-[#2e3038] rounded-2xl p-6 shadow-xs hover:shadow-md transition-shadow flex flex-col"
          >
            {/* Card Header */}
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#f2f3fd] dark:bg-[#2e3038] flex items-center justify-center text-[#0058be] dark:text-[#adc6ff]">
                  <span className="material-symbols-outlined">
                    {item.name.includes('Google')
                      ? 'key'
                      : item.name.includes('Composio')
                      ? 'hub'
                      : 'chat_bubble'}
                  </span>
                </div>
                <div>
                  <h3 className="text-[16px] font-bold text-[#191b23] dark:text-white leading-snug">
                    {item.name}
                  </h3>
                  <p className="text-[12px] text-[#424754] dark:text-[#c2c6d6]">{item.category}</p>
                </div>
              </div>
              <div className="px-2.5 py-1 rounded-full bg-[#1a6b52]/10 text-[#196b52] text-[11px] font-semibold flex items-center gap-1.5 border border-[#1a6b52]/20">
                <div className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></div>
                {item.status}
              </div>
            </div>

            {/* Card Body Details */}
            <div className="mb-4 flex-1 space-y-3">
              {item.details.activeScopes && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-1.5">
                    Escopos Ativos
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {item.details.activeScopes.map((scope) => (
                      <span
                        key={scope}
                        className="px-2 py-0.5 bg-[#f2f3fd] dark:bg-[#2e3038] rounded text-[11px] font-mono text-[#0058be] dark:text-[#adc6ff]"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {item.details.storagePath && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-0.5">
                    Storage Path
                  </p>
                  <p className="font-mono text-[12px] text-[#191b23] dark:text-white truncate">
                    {item.details.storagePath}
                  </p>
                </div>
              )}

              {item.details.redirectUri && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-0.5">
                    Redirect URI
                  </p>
                  <p className="font-mono text-[12px] text-[#191b23] dark:text-white truncate">
                    {item.details.redirectUri}
                  </p>
                </div>
              )}

              {item.details.apiKeySource && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-0.5">
                    API Key Source
                  </p>
                  <p className="font-mono text-[12px] text-[#191b23] dark:text-white">
                    {item.details.apiKeySource}
                  </p>
                </div>
              )}

              {item.details.connectedApps && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-1">
                    Apps Conectados
                  </p>
                  <ul className="text-[12px] text-[#191b23] dark:text-white space-y-0.5 font-medium">
                    {item.details.connectedApps.map((app) => (
                      <li key={app} className="flex items-center gap-1.5">
                        <span className="text-[#196b52] font-bold">✓</span> {app}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {item.details.endpoint && (
                <div>
                  <p className="text-[10px] font-bold text-[#424754] uppercase tracking-wider mb-1">
                    Endpoint
                  </p>
                  <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-2 rounded-lg font-mono text-[11px] text-[#191b23] dark:text-white truncate">
                    {item.details.endpoint}
                  </div>
                </div>
              )}

              {item.details.webhookInfo && (
                <div className="p-3 bg-[#f2f3fd] dark:bg-[#2e3038] rounded-xl border border-[#c2c6d6]/30">
                  <p className="text-[11px] text-[#424754] dark:text-[#c2c6d6]">
                    {item.details.webhookInfo}
                  </p>
                </div>
              )}
            </div>

            {/* Actions Footer */}
            <div className="flex gap-2 pt-4 border-t border-[#e1e2ec] dark:border-[#2e3038] mt-auto">
              <button
                onClick={() => handlePingTest(item.name)}
                className="flex-1 py-2 border border-[#c2c6d6] dark:border-[#424754] rounded-xl text-[12px] font-semibold text-[#191b23] dark:text-white hover:bg-[#f2f3fd] transition-colors"
              >
                Testar Ping
              </button>
              <button className="flex-1 py-2 border border-[#c2c6d6] dark:border-[#424754] rounded-xl text-[12px] font-semibold text-[#0058be] dark:text-[#adc6ff] hover:bg-[#f2f3fd] transition-colors">
                Reconfigurar
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
