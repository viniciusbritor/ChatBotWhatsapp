import React from 'react';
import { NavigationTab, CurrentUser } from '../types';

interface SidebarProps {
  activeTab: NavigationTab;
  setActiveTab: (tab: NavigationTab) => void;
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
  currentUser?: CurrentUser | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  mobileOpen,
  setMobileOpen,
  currentUser
}) => {
  const navItems: { id: NavigationTab; label: string; icon: string; fillIcon?: boolean }[] = [
    { id: 'whatsapp', label: 'Contas WhatsApp', icon: 'chat' },
    { id: 'agentes', label: 'Agentes', icon: 'smart_toy' },
    { id: 'skills', label: 'Skills', icon: 'psychology' },
    { id: 'tools', label: 'Tools', icon: 'build' },
    { id: 'proprietarios', label: 'Proprietários', icon: 'group' },
    { id: 'integracoes', label: 'Integrações', icon: 'settings_input_component' },
    { id: 'conexoes', label: 'Conexões', icon: 'hub' },
    { id: 'conhecimento', label: 'Conhecimento', icon: 'menu_book' },
    { id: 'status', label: 'Status', icon: 'signal_cellular_alt' }
  ];

  const visibleNavItems = currentUser && !currentUser.isAdmin
    ? navItems.filter((item) => item.id === 'conexoes' || item.id === 'conhecimento')
    : navItems;

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden backdrop-blur-xs transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`bg-[#f9f9ff] dark:bg-[#191b23] border-r border-[#c2c6d6]/40 h-screen w-64 fixed left-0 top-0 flex flex-col gap-4 p-4 pt-6 z-50 transition-transform duration-300 md:translate-x-0 ${
          mobileOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="px-2 mb-2 flex items-center justify-between">
          <div>
            <h1 className="font-semibold text-[22px] tracking-tight text-[#0058be] dark:text-[#adc6ff] flex items-center gap-2">
              <span className="material-symbols-outlined text-[26px]">tune</span>
              Control Plane
            </h1>
            <p className="text-[12px] text-[#424754] dark:text-[#c2c6d6] font-medium tracking-wide mt-0.5">
              Management Console
            </p>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            className="md:hidden text-[#424754] hover:bg-[#e1e2ec] p-1.5 rounded-lg"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Navigation items list */}
        <nav className="flex flex-col gap-1 w-full flex-1 overflow-y-auto pr-1">
          {visibleNavItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setMobileOpen(false);
                }}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-semibold transition-all duration-200 text-left w-full group ${
                  isActive
                    ? 'text-[#0058be] dark:text-[#d8e2ff] bg-[#d8e2ff]/50 dark:bg-[#2170e4]/30 shadow-xs border border-[#0058be]/20'
                    : 'text-[#424754] dark:text-[#c2c6d6] hover:bg-[#e6e7f2] dark:hover:bg-[#2e3038] hover:text-[#191b23]'
                }`}
              >
                <span
                  className="material-symbols-outlined text-[20px] transition-transform group-hover:scale-110"
                  style={{
                    fontVariationSettings: isActive ? "'FILL' 1" : "'FILL' 0"
                  }}
                >
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Bottom system badge */}
        <div className="pt-3 border-t border-[#c2c6d6]/30 px-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#196b52] animate-pulse"></span>
            <span className="text-[11px] font-semibold text-[#196b52] tracking-wider uppercase">
              Omnichannel v2.3
            </span>
          </div>
          <span className="text-[10px] text-[#727785] font-mono">100% OK</span>
        </div>
      </aside>
    </>
  );
};
