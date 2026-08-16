import React from 'react';
import { WhatsAppAccount } from '../../types';

interface WhatsAppAccountsViewProps {
  accounts: WhatsAppAccount[];
  onAddNew: () => void;
  onEditAccount: (acc: WhatsAppAccount) => void;
  searchQuery: string;
}

export const WhatsAppAccountsView: React.FC<WhatsAppAccountsViewProps> = ({
  accounts,
  onAddNew,
  onEditAccount,
  searchQuery
}) => {
  const filtered = accounts.filter(
    (acc) =>
      acc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      acc.phone.includes(searchQuery) ||
      acc.ownerPhone.includes(searchQuery)
  );

  return (
    <div className="space-y-6">
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-[28px] font-bold text-[#191b23] dark:text-white tracking-tight">
              Contas WhatsApp
            </h2>
            <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-1">
              Instâncias conectadas via Evolution API. Owner_phone = whatsapp_accounts.owner_phone.
            </p>
          </div>
        <button
          onClick={onAddNew}
          className="bg-[#2170e4] hover:bg-[#0058be] text-white font-semibold text-[13px] px-4 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Nova conta
        </button>
      </div>

      {/* Grid of Accounts */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {filtered.map((acc) => (
          <div
            key={acc.id}
            className="bg-white dark:bg-[#191b23] rounded-2xl border border-[#e2e8f0] dark:border-[#2e3038] p-6 shadow-xs hover:shadow-md transition-all duration-300 flex flex-col gap-4 relative group overflow-hidden"
          >
            {/* Ambient Background Blob */}
            <div className="absolute -right-4 -top-4 w-24 h-24 bg-[#d8e2ff]/30 rounded-full blur-2xl group-hover:bg-[#d8e2ff]/60 transition-all duration-500"></div>

            <div className="flex justify-between items-start z-10">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-[#f2f3fd] dark:bg-[#2e3038] flex items-center justify-center text-[#0058be] dark:text-[#adc6ff]">
                  <span className="material-symbols-outlined text-[28px]">chat_bubble</span>
                </div>
                <div>
                  <h3 className="text-[18px] font-semibold text-[#191b23] dark:text-white">
                    {acc.name}
                  </h3>
                  <p className="text-[13px] text-[#424754] dark:text-[#c2c6d6] font-mono mt-0.5">
                    {acc.phone}
                  </p>
                </div>
              </div>

              {/* Status Pill */}
              <div className="bg-[#1a6b52]/10 text-[#196b52] font-semibold text-[11px] px-3 py-1 rounded-full flex items-center gap-1.5 border border-[#1a6b52]/20 tracking-wide">
                <span className="w-1.5 h-1.5 rounded-full bg-[#196b52]"></span>
                {acc.status}
              </div>
            </div>

            <div className="z-10 mt-1">
              <span className="inline-flex items-center bg-[#f1f5f9] dark:bg-[#2e3038] text-[#475569] dark:text-[#c2c6d6] font-mono text-[12px] px-2.5 py-1 rounded-md border border-[#e2e8f0] dark:border-[#424754]">
                Owner: {acc.ownerPhone}
              </span>
            </div>

            <div className="mt-auto pt-3 border-t border-[#f2f3fd] dark:border-[#2e3038] flex justify-end z-10">
              <button
                onClick={() => onEditAccount(acc)}
                className="bg-white dark:bg-[#2e3038] border border-[#e2e8f0] dark:border-[#424754] text-[#0f172a] dark:text-white hover:bg-[#f8fafc] px-4 py-1.5 rounded-xl text-[12px] font-semibold transition-colors flex items-center gap-1.5 shadow-2xs"
              >
                <span className="material-symbols-outlined text-[16px]">edit</span>
                Editar
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
