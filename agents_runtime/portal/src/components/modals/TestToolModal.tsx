import React, { useState } from 'react';
import { Tool } from '../../types';

interface TestToolModalProps {
  tool: Tool | null;
  onClose: () => void;
}

export const TestToolModal: React.FC<TestToolModalProps> = ({ tool, onClose }) => {
  if (!tool) return null;

  const [payload, setPayload] = useState(tool.samplePayload || '{}');
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleRunTest = () => {
    setIsRunning(true);
    setResult(null);

    setTimeout(() => {
      setIsRunning(false);
      try {
        const parsed = JSON.parse(payload);
        setResult(
          JSON.stringify(
            {
              status: 200,
              code: 'SUCCESS',
              message: `Execução da ferramenta ${tool.code} concluída com sucesso.`,
              timestamp: new Date().toISOString(),
              executedWith: parsed,
              output: {
                acknowledged: true,
                recordsProcessed: 1,
                simulatedResult: `Ação ${tool.name} executada e validada no ambiente de testes.`
              }
            },
            null,
            2
          )
        );
      } catch (err) {
        setResult(
          JSON.stringify(
            {
              status: 400,
              code: 'INVALID_JSON_PAYLOAD',
              error: 'O JSON fornecido contém erros de sintaxe.',
              details: String(err)
            },
            null,
            2
          )
        );
      }
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-xl w-full p-6 shadow-2xl flex flex-col gap-4 my-8">
        <div className="flex justify-between items-start border-b border-[#c2c6d6]/30 pb-3">
          <div>
            <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
              <span className="material-symbols-outlined text-[#0058be]">build</span>
              Testar Ferramenta: {tool.name}
            </h3>
            <p className="text-[12px] font-mono text-[#424754] mt-0.5">{tool.code}</p>
          </div>
          <button
            onClick={onClose}
            className="text-[#727785] hover:text-[#191b23] p-1 rounded-lg hover:bg-[#e1e2ec]"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <div>
          <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
            Payload de Entrada (JSON)
          </label>
          <textarea
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            rows={5}
            className="w-full bg-[#191b23] text-[#a3efcf] border border-[#c2c6d6]/30 rounded-xl p-3 text-[12px] font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-[#0058be]"
          />
        </div>

        <button
          onClick={handleRunTest}
          disabled={isRunning}
          className="w-full bg-[#0058be] text-white py-2.5 rounded-xl font-semibold text-[13px] hover:bg-[#2170e4] transition-colors flex items-center justify-center gap-2 shadow-xs disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[18px]">terminal</span>
          {isRunning ? 'Executando requisição...' : 'Executar Teste da Tool'}
        </button>

        {result && (
          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              Resultado da Resposta
            </label>
            <pre className="p-3 bg-[#191b23] text-[#a3efcf] text-[11px] font-mono rounded-xl overflow-x-auto max-h-56 leading-normal border border-[#c2c6d6]/20">
              {result}
            </pre>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#f2f3fd] hover:bg-[#e1e2ec] text-[#191b23] font-semibold text-[12px] rounded-xl border border-[#c2c6d6]"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
};
