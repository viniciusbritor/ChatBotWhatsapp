import React, { useState } from 'react';
import { KnowledgeCategory } from '../../types';

interface KnowledgeViewProps {
  categories: KnowledgeCategory[];
  onUploadClick: () => void;
  onViewChunks: (cat: KnowledgeCategory) => void;
  onReindex: (catId: string) => void;
  searchQuery: string;
}

export const KnowledgeView: React.FC<KnowledgeViewProps> = ({
  categories,
  onUploadClick,
  onViewChunks,
  onReindex,
  searchQuery
}) => {
  const [reindexToast, setReindexToast] = useState<string | null>(null);

  const filtered = categories.filter((c) => {
    const q = (searchQuery || '').toLowerCase();
    const title = (c.title || '').toLowerCase();
    const coll = (c.collection || '').toLowerCase();
    const klass = (c.classification || '').toLowerCase();
    return !q || title.includes(q) || coll.includes(q) || klass.includes(q);
  });

  const totalChunks = categories.reduce((acc, c) => acc + c.chunkCount, 0);

  const handleReindexClick = (cat: KnowledgeCategory) => {
    onReindex(cat.id);
    setReindexToast(`Reindexação iniciada para: ${cat.title}`);
    setTimeout(() => setReindexToast(null), 2500);
  };

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {reindexToast && (
        <div className="fixed top-20 right-8 z-50 bg-[#191b23] text-[#a3efcf] px-4 py-3 rounded-xl shadow-2xl text-[13px] font-mono border border-[#a3efcf]">
          ⚡ {reindexToast}
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-[36px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Conhecimento
          </h1>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-0.5">
            Coleções vetoriais, chunks e modelo RAG
          </p>
        </div>
        <button
          onClick={onUploadClick}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          + Upload Documento
        </button>
      </div>

      {/* Summary Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-[#191b23] p-4 rounded-2xl border border-[#c2c6d6] dark:border-[#2e3038] shadow-2xs">
          <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
            Chunks Indexados
          </p>
          <p className="text-[28px] font-bold text-[#0058be] dark:text-[#adc6ff] leading-none">
            {totalChunks}
          </p>
          <p className="text-[12px] text-[#196b52] font-semibold mt-1">100% Categorizados</p>
        </div>

        <div className="bg-white dark:bg-[#191b23] p-4 rounded-2xl border border-[#c2c6d6] dark:border-[#2e3038] shadow-2xs">
          <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
            Coleções Ativas
          </p>
          <p className="text-[28px] font-bold text-[#191b23] dark:text-white leading-none">2</p>
          <p className="text-[12px] font-mono text-[#424754] dark:text-[#c2c6d6] truncate mt-1">
            agent-knowledge-v2, group...
          </p>
        </div>

        <div className="bg-white dark:bg-[#191b23] p-4 rounded-2xl border border-[#c2c6d6] dark:border-[#2e3038] shadow-2xs">
          <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
            Modelo de Embedding
          </p>
          <p className="text-[14px] font-bold text-[#191b23] dark:text-white leading-snug">
            OpenAI text-embedding-3-small
          </p>
          <p className="text-[12px] font-mono text-[#424754] dark:text-[#c2c6d6]">1536-dim</p>
        </div>

        <div className="bg-white dark:bg-[#191b23] p-4 rounded-2xl border border-[#c2c6d6] dark:border-[#2e3038] shadow-2xs">
          <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
            Retrieval Score Mínimo
          </p>
          <p className="text-[12px] font-mono text-[#191b23] dark:text-white mt-1">
            RAG_RETRIEVE_MIN_SCORE = 0.7
          </p>
        </div>
      </div>

      {/* Grid of Knowledge Categories */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((cat) => (
          <div
            key={cat.id}
            className="bg-white dark:bg-[#191b23] rounded-2xl border border-[#c2c6d6] dark:border-[#2e3038] p-5 shadow-xs flex flex-col gap-3"
          >
            <div className="flex justify-between items-start">
              <div className="w-10 h-10 rounded-xl bg-[#0058be]/10 flex items-center justify-center text-[#0058be] dark:text-[#adc6ff]">
                <span className="material-symbols-outlined">description</span>
              </div>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#196b52]/10 text-[#196b52] font-semibold text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></span> {cat.status}
              </span>
            </div>

            <div>
              <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white">
                {cat.title}
              </h3>
              <p className="text-[12px] font-mono text-[#424754] dark:text-[#c2c6d6] mt-1">
                Collection: {cat.collection}
              </p>
              <p className="text-[12px] font-mono text-[#727785]">Class: {cat.classification}</p>
              {cat.ownerId && (
                <p className="text-[12px] font-mono text-[#196b52] dark:text-[#a3efcf] mt-1">
                  👤 Owner: {cat.ownerId}
                </p>
              )}
            </div>

            <div className="py-2.5 border-y border-[#c2c6d6]/40 flex justify-between text-[13px] font-medium text-[#424754] dark:text-[#c2c6d6]">
              <span>{cat.fileCount} arquivos</span>
              <span>{cat.chunkCount} chunks</span>
            </div>

            <div className="flex gap-2 pt-1 mt-auto">
              <button
                onClick={() => onViewChunks(cat)}
                className="flex-1 py-2 rounded-xl border border-[#c2c6d6] text-[12px] font-semibold text-[#191b23] dark:text-white hover:bg-[#f2f3fd] transition-colors"
              >
                Ver Chunks
              </button>
              <button
                onClick={() => handleReindexClick(cat)}
                className="flex-1 py-2 rounded-xl border border-[#c2c6d6] text-[12px] font-semibold text-[#0058be] dark:text-[#adc6ff] hover:bg-[#f2f3fd] transition-colors"
              >
                Reindexar
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
