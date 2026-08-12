import React, { useState } from 'react';
import { KnowledgeCategory } from '../../types';

interface ViewChunksModalProps {
  category: KnowledgeCategory | null;
  onClose: () => void;
}

export const ViewChunksModal: React.FC<ViewChunksModalProps> = ({ category, onClose }) => {
  if (!category) return null;

  const [filterQuery, setFilterQuery] = useState('');

  const filteredChunks = category.chunks.filter((c) =>
    c.previewText.toLowerCase().includes(filterQuery.toLowerCase()) ||
    c.filename.toLowerCase().includes(filterQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-4 my-8">
        <div className="flex justify-between items-start border-b border-[#c2c6d6]/30 pb-3">
          <div>
            <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
              <span className="material-symbols-outlined text-[#0058be]">database</span>
              Chunks Indexados: {category.title}
            </h3>
            <p className="text-[12px] font-mono text-[#424754] mt-0.5">
              Collection: {category.collection} | Class: {category.classification}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[#727785] hover:text-[#191b23] p-1 rounded-lg hover:bg-[#e1e2ec]"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Filter Input */}
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#727785] text-[18px]">
            search
          </span>
          <input
            type="text"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Filtrar por texto ou arquivo..."
            className="w-full pl-9 pr-4 py-2 bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl text-[12px] text-[#191b23] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0058be]"
          />
        </div>

        {/* Chunks List */}
        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {filteredChunks.length === 0 ? (
            <p className="text-[12px] text-[#727785] text-center py-6">
              Nenhum chunk encontrado com os termos pesquisados.
            </p>
          ) : (
            filteredChunks.map((chunk) => (
              <div
                key={chunk.id}
                className="p-3 bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6]/40 rounded-xl space-y-1.5"
              >
                <div className="flex justify-between items-center text-[11px]">
                  <span className="font-semibold text-[#0058be] dark:text-[#adc6ff] font-mono">
                    📄 {chunk.filename}
                  </span>
                  <span className="px-2 py-0.5 bg-[#a3efcf]/30 text-[#196b52] font-mono font-bold rounded-full">
                    Score: {(chunk.score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-[12px] text-[#191b23] dark:text-[#e1e2ec] font-mono leading-relaxed bg-white dark:bg-[#191b23] p-2.5 rounded-lg border border-[#c2c6d6]/30">
                  {chunk.previewText}
                </p>
              </div>
            ))
          )}
        </div>

        <div className="flex justify-end pt-2 border-t border-[#c2c6d6]/30">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#0058be] text-white font-semibold text-[12px] rounded-xl hover:bg-[#2170e4]"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
};
