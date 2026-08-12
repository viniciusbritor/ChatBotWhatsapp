import React, { useState } from 'react';
import { KnowledgeCategory } from '../../types';

interface UploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (newCategory: KnowledgeCategory) => void;
}

export const UploadDocumentModal: React.FC<UploadDocumentModalProps> = ({
  isOpen,
  onClose,
  onUpload
}) => {
  if (!isOpen) return null;

  const [title, setTitle] = useState('');
  const [collection, setCollection] = useState('agent-knowledge-v2');
  const [classification, setClassification] = useState('ata_reuniao');
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title) return;

    setIsProcessing(true);

    setTimeout(() => {
      setIsProcessing(false);
      const ext = file ? file.name.split('.').pop()?.toUpperCase() || 'PDF' : 'PDF';

      onUpload({
        id: `kc-${Date.now()}`,
        title: `${title} (${ext})`,
        formats: ext,
        collection,
        classification,
        fileCount: 1,
        chunkCount: 12,
        status: 'Indexado',
        chunks: [
          {
            id: `c-new-1`,
            filename: file ? file.name : `${title}.${ext.toLowerCase()}`,
            score: 0.95,
            previewText: 'Documento recebido e indexado com sucesso no pipeline RAG da Jennifer.'
          }
        ]
      });

      onClose();
    }, 800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-lg w-full p-6 shadow-2xl flex flex-col gap-4 my-8">
        <div className="flex justify-between items-center border-b border-[#c2c6d6]/30 pb-3">
          <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
            <span className="material-symbols-outlined text-[#0058be]">cloud_upload</span>
            Upload & Indexação de Documento
          </h3>
          <button
            onClick={onClose}
            className="text-[#727785] hover:text-[#191b23] p-1 rounded-lg hover:bg-[#e1e2ec]"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              Arquivo (PDF, DOCX, XLSX, TXT)
            </label>
            <div className="border-2 border-dashed border-[#c2c6d6] hover:border-[#0058be] rounded-xl p-6 text-center cursor-pointer transition-colors bg-[#f2f3fd] dark:bg-[#2e3038]">
              <input
                type="file"
                accept=".pdf,.docx,.xlsx,.txt,.md"
                onChange={handleFileChange}
                className="hidden"
                id="doc-file-input"
              />
              <label htmlFor="doc-file-input" className="cursor-pointer block">
                <span className="material-symbols-outlined text-[36px] text-[#0058be] mb-1">
                  upload_file
                </span>
                <p className="text-[13px] font-semibold text-[#191b23] dark:text-white">
                  {file ? file.name : 'Clique para selecionar um arquivo'}
                </p>
                <p className="text-[11px] text-[#727785] mt-1">Suporta PDF, DOCX, XLSX e Markdown</p>
              </label>
            </div>
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              Título da Categoria / Documento
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex: Manual de Procedimentos 2026"
              className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[13px] text-[#191b23] dark:text-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
                Coleção RAG
              </label>
              <select
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
                className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[12px] font-mono text-[#191b23] dark:text-white"
              >
                <option value="agent-knowledge-v2">agent-knowledge-v2</option>
                <option value="group-knowledge-v2">group-knowledge-v2</option>
              </select>
            </div>

            <div>
              <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
                Classificação
              </label>
              <select
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
                className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[12px] font-mono text-[#191b23] dark:text-white"
              >
                <option value="ata_reuniao">ata_reuniao</option>
                <option value="relatorio_tecnico">relatorio_tecnico</option>
                <option value="planilha_dados">planilha_dados</option>
                <option value="manual_sistema">manual_sistema</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-[#c2c6d6]/30">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-[#c2c6d6] rounded-xl text-[12px] font-semibold text-[#424754] hover:bg-[#e1e2ec]"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isProcessing}
              className="px-5 py-2 bg-[#0058be] text-white rounded-xl text-[12px] font-semibold hover:bg-[#2170e4] disabled:opacity-50"
            >
              {isProcessing ? 'Indexando Vetores...' : 'Upload & Processar RAG'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
