import React, { useState } from 'react';
import { Agent } from '../../types';

interface EditPromptModalProps {
  agent: Agent | null;
  onClose: () => void;
  onSave: (updatedAgent: Agent) => void;
}

export const EditPromptModal: React.FC<EditPromptModalProps> = ({ agent, onClose, onSave }) => {
  if (!agent) return null;

  const [prompt, setPrompt] = useState(agent.systemPrompt);
  const [model, setModel] = useState(agent.model);
  const [temp, setTemp] = useState(agent.temperature ?? 0.2);
  const [testInput, setTestInput] = useState('');
  const [testOutput, setTestOutput] = useState('');
  const [isTesting, setIsTesting] = useState(false);

  const handleTestPrompt = () => {
    if (!testInput.trim()) return;
    setIsTesting(true);
    setTestOutput('');

    setTimeout(() => {
      setIsTesting(false);
      setTestOutput(
        `[SIMULAÇÃO LLM - ${model}]\nPrompt de Sistema ativo. Resposta processada para: "${testInput}"\n\n> Entendido! Como agente ${agent.name}, processo sua requisição e mantenho os parâmetros delegados ativos.`
      );
    }, 700);
  };

  const handleSave = () => {
    onSave({
      ...agent,
      systemPrompt: prompt,
      model,
      temperature: temp
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-2xl w-full p-6 shadow-2xl flex flex-col gap-4 my-8">
        {/* Modal Header */}
        <div className="flex justify-between items-start border-b border-[#c2c6d6]/30 pb-3">
          <div>
            <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
              <span className="material-symbols-outlined text-[#0058be]">edit</span>
              Editar Prompt - {agent.name}
            </h3>
            <p className="text-[12px] text-[#424754] font-mono mt-0.5">ID: {agent.key}</p>
          </div>
          <button
            onClick={onClose}
            className="text-[#727785] hover:text-[#191b23] p-1 rounded-lg hover:bg-[#e1e2ec]"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Configurations Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              Modelo LLM
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-lg px-3 py-2 text-[13px] font-mono text-[#191b23] dark:text-white"
            >
              <option value="deepseek-v4-flash">deepseek-v4-flash</option>
              <option value="gpt-4-turbo">gpt-4-turbo</option>
              <option value="gemini-2.5-flash">gemini-2.5-flash</option>
              <option value="claude-3-5-sonnet">claude-3-5-sonnet</option>
            </select>
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              Temperatura ({temp})
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={temp}
              onChange={(e) => setTemp(parseFloat(e.target.value))}
              className="w-full h-2 bg-[#e1e2ec] rounded-lg appearance-none cursor-pointer accent-[#0058be] mt-2"
            />
          </div>
        </div>

        {/* System Prompt Editor */}
        <div>
          <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
            System Prompt Instruções
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={6}
            className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl p-3 text-[13px] font-mono text-[#191b23] dark:text-white leading-relaxed focus:outline-none focus:ring-2 focus:ring-[#0058be]/20"
          />
        </div>

        {/* Test Prompt Simulator */}
        <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-4 rounded-xl border border-[#c2c6d6]/40 space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-[12px] font-bold text-[#0058be] flex items-center gap-1">
              <span className="material-symbols-outlined text-[16px]">play_circle</span>
              Testar Prompt
            </span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder="Digite uma mensagem de teste..."
              className="flex-1 bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-lg px-3 py-1.5 text-[12px] text-[#191b23] dark:text-white"
            />
            <button
              onClick={handleTestPrompt}
              disabled={isTesting}
              className="bg-[#0058be] text-white px-3 py-1.5 rounded-lg text-[12px] font-semibold hover:bg-[#2170e4] disabled:opacity-50"
            >
              {isTesting ? 'Executando...' : 'Testar'}
            </button>
          </div>
          {testOutput && (
            <pre className="p-3 bg-[#191b23] text-[#a3efcf] text-[11px] font-mono rounded-lg overflow-x-auto whitespace-pre-wrap">
              {testOutput}
            </pre>
          )}
        </div>

        {/* Actions Footer */}
        <div className="flex justify-end gap-3 pt-3 border-t border-[#c2c6d6]/30">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-[#c2c6d6] rounded-xl text-[13px] font-semibold text-[#424754] hover:bg-[#e1e2ec]"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-[#0058be] text-white rounded-xl text-[13px] font-semibold hover:bg-[#2170e4] shadow-xs"
          >
            Salvar Alterações
          </button>
        </div>
      </div>
    </div>
  );
};
