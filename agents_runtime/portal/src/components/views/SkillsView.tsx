import React, { useState } from 'react';
import { Skill } from '../../types';

interface SkillsViewProps {
  skills: Skill[];
  onAddNew: () => void;
  searchQuery: string;
}

export const SkillsView: React.FC<SkillsViewProps> = ({ skills, onAddNew, searchQuery }) => {
  const [selectedDocSkill, setSelectedDocSkill] = useState<Skill | null>(null);

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-[36px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Skills
          </h1>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-0.5">
            Habilidades de processamento e parsers de conteúdo
          </p>
        </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Nova Skill
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((skill) => (
          <div
            key={skill.id}
            className="bg-white dark:bg-[#191b23] rounded-xl p-6 border border-[#e2e8f0] dark:border-[#2e3038] shadow-xs hover:shadow-md transition-all flex flex-col relative overflow-hidden"
          >
            <div className="flex justify-between items-start mb-3">
              <div className="p-2 bg-[#0058be]/10 rounded-lg text-[#0058be] dark:text-[#adc6ff]">
                <span className="material-symbols-outlined text-[24px]">description</span>
              </div>
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#a3efcf]/30 rounded-full border border-[#196b52]/20">
                <span className="w-2 h-2 rounded-full bg-[#196b52]"></span>
                <span className="text-[10px] text-[#196b52] font-bold tracking-wider">
                  {skill.status}
                </span>
              </div>
            </div>

            <div className="mb-2">
              <span className="font-mono text-[12px] bg-[#e1e2ec] dark:bg-[#2e3038] px-2 py-0.5 rounded text-[#424754] dark:text-[#c2c6d6]">
                {skill.code}
              </span>
            </div>

            <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white mb-2 leading-snug">
              {skill.name}
            </h3>

            <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6] flex-1 mb-4 leading-relaxed">
              {skill.description}
            </p>

            <div className="flex flex-col gap-3 mt-auto">
              <div className="flex gap-2">
                <span className="bg-[#f1f5f9] dark:bg-[#2e3038] text-[#475569] dark:text-[#c2c6d6] font-mono text-[11px] px-2.5 py-1 rounded">
                  {skill.categoryTag}
                </span>
              </div>

              <div className="flex items-center justify-between border-t border-[#e2e8f0] dark:border-[#2e3038] pt-3 text-[12px] font-semibold">
                <button
                  onClick={() => setSelectedDocSkill(skill)}
                  className="text-[#0058be] dark:text-[#adc6ff] hover:underline"
                >
                  Editar Skill
                </button>
                <button
                  onClick={() => setSelectedDocSkill(skill)}
                  className="text-[#424754] dark:text-[#c2c6d6] hover:underline"
                >
                  Ver Documentação
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Documentation Drawer/Modal */}
      {selectedDocSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-start border-b border-[#c2c6d6]/30 pb-3">
              <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
                <span className="material-symbols-outlined text-[#0058be]">menu_book</span>
                {selectedDocSkill.name}
              </h3>
              <button
                onClick={() => setSelectedDocSkill(null)}
                className="text-[#727785] hover:text-[#191b23] p-1"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
            <div className="space-y-2">
              <span className="font-mono text-[12px] px-2 py-0.5 bg-[#f2f3fd] dark:bg-[#2e3038] rounded text-[#0058be] font-bold">
                {selectedDocSkill.code}
              </span>
              <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6]">
                {selectedDocSkill.detailedDoc || selectedDocSkill.description}
              </p>
            </div>
            <div className="flex justify-end pt-3">
              <button
                onClick={() => setSelectedDocSkill(null)}
                className="px-4 py-2 bg-[#0058be] text-white text-[12px] font-semibold rounded-xl hover:bg-[#2170e4]"
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
