import React, { useState } from 'react';
import { Tool } from '../../types';

interface ToolsViewProps {
  tools: Tool[];
  onAddNew: () => void;
  onTestTool: (tool: Tool) => void;
  searchQuery: string;
}

export const ToolsView: React.FC<ToolsViewProps> = ({
  tools,
  onAddNew,
  onTestTool,
  searchQuery
}) => {
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string>('Tudo');
  const [permissionModalTool, setPermissionModalTool] = useState<Tool | null>(null);

  const filtered = tools.filter((tool) => {
    const matchesSearch =
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase());

    if (activeCategoryFilter === 'Google Native') {
      return matchesSearch && tool.typeFilter === 'Google Native';
    }
    if (activeCategoryFilter === 'Composio MCP') {
      return matchesSearch && tool.typeFilter === 'Composio MCP';
    }
    return matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-[#c2c6d6]/30 pb-4">
        <div>
          <h2 className="text-[30px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Tools
          </h2>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-0.5">
            Gerencie as ferramentas e integrações disponíveis para seus agentes.
          </p>
        </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Nova Ferramenta
        </button>
      </div>

      {/* Category Pills Filter */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {['Tudo', 'Google Native', 'Composio MCP'].map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategoryFilter(cat)}
            className={`px-4 py-1.5 rounded-full text-[13px] font-semibold transition-all ${
              activeCategoryFilter === cat
                ? 'bg-[#0058be] text-white shadow-xs'
                : 'bg-[#e6e7f2] dark:bg-[#2e3038] text-[#191b23] dark:text-white hover:bg-[#e1e2ec]'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Tools Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {filtered.map((tool) => (
          <div
            key={tool.id}
            className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] dark:border-[#2e3038] rounded-2xl p-6 shadow-xs hover:shadow-md hover:border-[#727785] transition-all duration-200 flex flex-col"
          >
            <div className="flex justify-between items-start mb-3">
              <div>
                <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white">
                  {tool.name}
                </h3>
                <div className="mt-1.5 inline-flex items-center bg-[#f1f5f9] dark:bg-[#2e3038] rounded px-2 py-0.5 font-mono text-[12px] text-[#424754] dark:text-[#c2c6d6] border border-[#c2c6d6]/30">
                  <code>{tool.code}</code>
                </div>
              </div>
              <div className="bg-[#a3efcf]/20 text-[#196b52] px-3 py-1 rounded-full text-[11px] font-semibold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></span>
                {tool.status}
              </div>
            </div>

            <div className="mb-3">
              <span className="text-[11px] font-bold text-[#0058be] dark:text-[#adc6ff] bg-[#d8e2ff]/40 dark:bg-[#2170e4]/30 px-2.5 py-1 rounded-md">
                {tool.category}
              </span>
            </div>

            <div className="mb-6 flex-1">
              <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6] leading-relaxed">
                {tool.description}
              </p>
            </div>

            <div className="flex justify-start gap-3 mt-auto pt-4 border-t border-[#c2c6d6]/40">
              <button
                onClick={() => onTestTool(tool)}
                className="text-[#0058be] dark:text-[#adc6ff] font-semibold text-[12px] px-3.5 py-1.5 rounded-lg hover:bg-[#d8e2ff]/30 transition-colors"
              >
                Testar Tool
              </button>
              <button
                onClick={() => setPermissionModalTool(tool)}
                className="text-[#0f172a] dark:text-white bg-white dark:bg-[#2e3038] border border-[#e2e8f0] dark:border-[#424754] font-semibold text-[12px] px-3.5 py-1.5 rounded-lg hover:bg-[#f2f3fd] transition-colors shadow-2xs"
              >
                Ver Permissões
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Permissions Modal */}
      {permissionModalTool && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b border-[#c2c6d6]/30 pb-3">
              <h3 className="text-[16px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
                <span className="material-symbols-outlined text-[#0058be]">lock</span>
                Permissões: {permissionModalTool.name}
              </h3>
              <button
                onClick={() => setPermissionModalTool(null)}
                className="text-[#727785] hover:text-[#191b23] p-1"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
            <div className="space-y-2">
              <p className="text-[12px] font-semibold text-[#424754]">Escopos OAuth / API Requeridos:</p>
              <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-3 rounded-xl space-y-1">
                {permissionModalTool.permissions.map((perm) => (
                  <div key={perm} className="text-[11px] font-mono text-[#0058be] dark:text-[#adc6ff]">
                    ✓ {perm}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setPermissionModalTool(null)}
                className="px-4 py-1.5 bg-[#0058be] text-white text-[12px] font-semibold rounded-xl hover:bg-[#2170e4]"
              >
                Entendido
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
