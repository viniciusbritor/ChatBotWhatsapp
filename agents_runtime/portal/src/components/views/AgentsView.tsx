import React from 'react';
import { Agent } from '../../types';

interface AgentsViewProps {
  agents: Agent[];
  onAddNew: () => void;
  onEditPrompt: (agent: Agent) => void;
  searchQuery: string;
}

export const AgentsView: React.FC<AgentsViewProps> = ({
  agents,
  onAddNew,
  onEditPrompt,
  searchQuery
}) => {
  const filtered = agents.filter(
    (a) => {
      const q = (searchQuery || '').toLowerCase();
      const name = (a.name || '').toLowerCase();
      const key = (a.key || '').toLowerCase();
      const desc = (a.description || '').toLowerCase();
      return !q || name.includes(q) || key.includes(q) || desc.includes(q);
    }
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#c2c6d6]/30 pb-4">
        <div>
          <h2 className="text-[32px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Agentes
          </h2>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-0.5">
            Gerenciador de orquestradores e sub-agentes Omnichannel
          </p>
        </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          + Novo Agente
        </button>
      </div>

      {/* Agents Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {filtered.map((agent) => (
          <div
            key={agent.id}
            className="bg-white dark:bg-[#191b23] border border-[#e2e8f0] dark:border-[#2e3038] rounded-xl p-6 shadow-xs hover:shadow-md hover:border-[#c2c6d6] transition-all flex flex-col gap-4"
          >
            <div className="flex justify-between items-start gap-4">
              <div>
                <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white leading-snug">
                  {agent.name}
                </h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="inline-flex items-center bg-[#ecedf7] dark:bg-[#2e3038] text-[#191b23] dark:text-white font-mono text-[12px] px-2 py-0.5 rounded-md">
                    {agent.key}
                  </span>
                  <span className="inline-flex items-center text-[#424754] dark:text-[#c2c6d6] font-mono text-[12px] px-2 py-0.5 rounded-md border border-[#c2c6d6]">
                    {agent.model}
                  </span>
                </div>
              </div>

              {/* Status Pill */}
              <div className="bg-[#1a6b52]/10 text-[#196b52] font-semibold text-[11px] px-2.5 py-1 rounded-full flex items-center gap-1 shrink-0 border border-[#1a6b52]/20">
                <div className="w-2 h-2 rounded-full bg-[#196b52]"></div>
                {agent.status}
              </div>
            </div>

            <p className="text-[#424754] dark:text-[#c2c6d6] text-[13px] leading-relaxed">
              {agent.description}
            </p>

            {agent.delegatesTo && agent.delegatesTo.length > 0 && (
              <div className="mt-1">
                <h4 className="text-[11px] font-semibold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1.5">
                  Delegates To:
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {agent.delegatesTo.map((sub) => (
                    <span
                      key={sub}
                      className="bg-[#f2f3fd] dark:bg-[#2e3038] text-[#424754] dark:text-[#adc6ff] font-mono text-[11px] px-2 py-0.5 rounded border border-[#c2c6d6]/30"
                    >
                      {sub}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-auto pt-4 border-t border-[#e2e8f0] dark:border-[#2e3038] flex justify-end">
              <button
                onClick={() => onEditPrompt(agent)}
                className="bg-white dark:bg-[#2e3038] border border-[#e2e8f0] dark:border-[#424754] text-[#0058be] dark:text-[#adc6ff] hover:bg-[#f2f3fd] font-semibold text-[12px] px-3.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 shadow-2xs"
              >
                <span className="material-symbols-outlined text-[16px]">edit</span>
                Editar Prompt
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
