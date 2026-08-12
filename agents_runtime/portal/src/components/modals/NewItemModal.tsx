import React, { useState } from 'react';
import { NavigationTab } from '../../types';

interface NewItemModalProps {
  type: NavigationTab;
  isOpen: boolean;
  onClose: () => void;
  onAdd: (newItem: any) => void;
}

export const NewItemModal: React.FC<NewItemModalProps> = ({ type, isOpen, onClose, onAdd }) => {
  if (!isOpen) return null;

  const [name, setName] = useState('');
  const [detail1, setDetail1] = useState('');
  const [detail2, setDetail2] = useState('');
  const [detail3, setDetail3] = useState('');

  const getModalMeta = () => {
    switch (type) {
      case 'whatsapp':
        return {
          title: 'Nova Conta WhatsApp',
          label1: 'Nome da Instância / Agente',
          placeholder1: 'Ex: Jennifer Vendas',
          label2: 'Número de Telefone (com DDI/DDD)',
          placeholder2: 'Ex: +5511999887766',
          label3: 'Telefone do Proprietário (Owner)',
          placeholder3: 'Ex: +5511966830020'
        };
      case 'agentes':
        return {
          title: 'Novo Agente de IA',
          label1: 'Nome do Agente',
          placeholder1: 'Ex: Suporte Técnico L1',
          label2: 'Chave / ID Único',
          placeholder2: 'Ex: agent-tech-support',
          label3: 'Descrição do Papel',
          placeholder3: 'Ex: Atendimento de nível 1 para dúvidas de infraestrutura'
        };
      case 'skills':
        return {
          title: 'Nova Skill',
          label1: 'Nome da Skill',
          placeholder1: 'Ex: CSV Table Parser',
          label2: 'Código da Skill',
          placeholder2: 'Ex: csv_parser',
          label3: 'Tag de Categoria',
          placeholder3: 'Ex: Knowledge / Parsing'
        };
      case 'tools':
        return {
          title: 'Nova Ferramenta (Tool)',
          label1: 'Nome da Tool',
          placeholder1: 'Ex: Slack Send Message',
          label2: 'Código da Tool',
          placeholder2: 'Ex: slack.send_message',
          label3: 'Categoria / Provedor',
          placeholder3: 'Ex: Google Native, Composio MCP ou Custom'
        };
      case 'proprietarios':
        return {
          title: 'Novo Proprietário',
          label1: 'Nome Completo',
          placeholder1: 'Ex: Maria Silva',
          label2: 'Telefone do Owner',
          placeholder2: 'Ex: +5511988776655',
          label3: 'UID ou Instância Associada',
          placeholder3: 'Ex: main_instance ou uid_998877'
        };
      default:
        return {
          title: 'Nova Conexão / Integração',
          label1: 'Nome da Integração',
          placeholder1: 'Ex: Webhook CRM Hubspot',
          label2: 'Categoria / Tipo',
          placeholder2: 'Ex: Webhook Inbound',
          label3: 'Endpoint / Configuração',
          placeholder3: 'Ex: https://api.crm.com/webhook'
        };
    }
  };

  const meta = getModalMeta();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    if (type === 'whatsapp') {
      onAdd({
        id: `wa-${Date.now()}`,
        name: name || 'Nova Instância',
        phone: detail1 || '+5511900000000',
        ownerPhone: detail2 || '+5511900000000',
        status: 'Conectado',
        instanceName: name.toLowerCase().replace(/\s+/g, '_'),
        updatedAt: new Date().toISOString()
      });
    } else if (type === 'agentes') {
      onAdd({
        id: `agent-${Date.now()}`,
        key: detail1 || name.toLowerCase().replace(/\s+/g, '-'),
        name,
        model: 'deepseek-v4-flash',
        description: detail2 || 'Novo agente cadastrado no Control Plane.',
        status: 'Active',
        delegatesTo: ['agent-knowledge-retriever'],
        systemPrompt: `Você é ${name}. Atue com precisão e siga as diretrizes organizacionais.`,
        temperature: 0.2
      });
    } else if (type === 'skills') {
      onAdd({
        id: `skill-${Date.now()}`,
        code: detail1 || 'custom_skill',
        name,
        description: detail2 || 'Descrição da nova skill cadastrada.',
        status: 'ACTIVE',
        categoryTag: detail3 || 'Custom / Extension'
      });
    } else if (type === 'tools') {
      onAdd({
        id: `tool-${Date.now()}`,
        code: detail1 || 'custom.tool',
        name,
        category: detail2 || 'Composio MCP',
        typeFilter: detail2?.includes('Google') ? 'Google Native' : 'Composio MCP',
        description: detail3 || 'Ferramenta de automação registrada.',
        status: 'Active',
        permissions: ['default:access'],
        samplePayload: JSON.stringify({ action: name, timestamp: new Date().toISOString() }, null, 2)
      });
    } else if (type === 'proprietarios') {
      onAdd({
        id: `owner-${Date.now()}`,
        name,
        role: 'Administrator / Owner',
        uid: detail2 || `uid_${Date.now().toString().slice(-6)}`,
        phone: detail1 || '+5511900000000',
        instance: detail3 || 'main_instance'
      });
    } else {
      onAdd({
        id: `int-${Date.now()}`,
        name,
        category: detail1 || 'Integration',
        status: 'Ativo',
        details: {
          endpoint: detail2 || 'https://api.coherence.com.br/endpoint',
          webhookInfo: detail3 || 'Webhook configurado e ativo.'
        }
      });
    }

    onClose();
    setName('');
    setDetail1('');
    setDetail2('');
    setDetail3('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] rounded-2xl max-w-md w-full p-6 shadow-2xl flex flex-col gap-4 my-8">
        <div className="flex justify-between items-center border-b border-[#c2c6d6]/30 pb-3">
          <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
            <span className="material-symbols-outlined text-[#0058be]">add_circle</span>
            {meta.title}
          </h3>
          <button
            onClick={onClose}
            className="text-[#727785] hover:text-[#191b23] p-1 rounded-lg hover:bg-[#e1e2ec]"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              {meta.label1}
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={meta.placeholder1}
              className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[13px] text-[#191b23] dark:text-white"
            />
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              {meta.label2}
            </label>
            <input
              type="text"
              value={detail1}
              onChange={(e) => setDetail1(e.target.value)}
              placeholder={meta.placeholder2}
              className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[13px] text-[#191b23] dark:text-white"
            />
          </div>

          <div>
            <label className="block text-[12px] font-semibold text-[#191b23] dark:text-white mb-1">
              {meta.label3}
            </label>
            <input
              type="text"
              value={detail2}
              onChange={(e) => setDetail2(e.target.value)}
              placeholder={meta.placeholder3}
              className="w-full bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6] rounded-xl px-3 py-2 text-[13px] text-[#191b23] dark:text-white"
            />
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
              className="px-5 py-2 bg-[#0058be] text-white rounded-xl text-[12px] font-semibold hover:bg-[#2170e4]"
            >
              Adicionar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
