import React from 'react';
import { Owner } from '../../types';

interface OwnersViewProps {
  owners: Owner[];
  onAddNew: () => void;
  searchQuery: string;
}

export const OwnersView: React.FC<OwnersViewProps> = ({ owners, onAddNew, searchQuery }) => {
  const filtered = owners.filter(
    (o) =>
      o.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      o.phone.includes(searchQuery) ||
      o.uid.includes(searchQuery)
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-[36px] font-bold text-[#191b23] dark:text-white tracking-tight">
            Proprietários
          </h1>
          <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-1">
            Dono único por instância Evolution (whatsapp_accounts.owner_phone)
          </p>
        </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Novo Proprietário
        </button>
      </div>

      {/* Grid of Owners */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {filtered.map((owner) => (
          <article
            key={owner.id}
            className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] dark:border-[#2e3038] rounded-xl p-6 shadow-xs hover:shadow-md transition-all duration-300 relative group flex flex-col justify-between min-h-[160px]"
          >
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="text-[20px] font-bold text-[#191b23] dark:text-white">
                  {owner.name}
                </h3>
                <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6] mt-1 font-medium">
                  {owner.role}
                </p>
              </div>
              <button className="text-[#727785] hover:text-[#0058be] transition-colors p-1">
                <span className="material-symbols-outlined">more_vert</span>
              </button>
            </div>

            <div className="flex flex-wrap gap-2 items-center mt-auto pt-4 border-t border-[#f2f3fd] dark:border-[#2e3038]">
              {/* UID Badge (Jade Green) */}
              <span className="inline-flex items-center gap-1.5 bg-[#196b52] text-white font-mono text-[12px] px-3 py-1 rounded-md shadow-2xs">
                <span className="material-symbols-outlined text-[14px]">badge</span>
                uid {owner.uid}
              </span>

              {/* Phone Badge */}
              <span className="inline-flex items-center gap-1.5 bg-[#ecedf7] dark:bg-[#2e3038] text-[#191b23] dark:text-white border border-[#c2c6d6] font-mono text-[12px] px-3 py-1 rounded-md">
                <span className="material-symbols-outlined text-[14px]">call</span>
                {owner.phone}
              </span>

              {/* Instance Badge */}
              <span className="inline-flex items-center gap-1.5 bg-[#e1e2ec] dark:bg-[#2e3038] text-[#424754] dark:text-[#c2c6d6] font-mono text-[12px] px-3 py-1 rounded-md">
                <span className="material-symbols-outlined text-[14px]">dns</span>
                {owner.instance}
              </span>

              {/* Linked Accounts Badge */}
              <span className="inline-flex items-center gap-1.5 bg-[#0058be]/10 dark:bg-[#adc6ff]/20 text-[#0058be] dark:text-[#adc6ff] border border-[#0058be]/30 font-mono text-[12px] px-3 py-1 rounded-md">
                <span className="material-symbols-outlined text-[14px]">link</span>
                WhatsApp: {owner.phone}
              </span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
};
