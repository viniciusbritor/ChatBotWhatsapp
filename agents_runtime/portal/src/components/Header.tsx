import React from 'react';

interface HeaderProps {
  title: string;
  subtitle?: string;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  setMobileOpen: (open: boolean) => void;
  onCommitClick?: () => void;
  onDeployClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  searchQuery,
  setSearchQuery,
  setMobileOpen,
  onCommitClick,
  onDeployClick
}) => {
  return (
    <header className="sticky top-0 z-30 w-full h-16 bg-white/80 dark:bg-[#191b23]/80 backdrop-blur-md border-b border-[#c2c6d6]/40 shadow-2xs flex justify-between items-center px-4 md:px-8">
      {/* Left section: Hamburger for mobile + Page title */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setMobileOpen(true)}
          className="md:hidden text-[#424754] dark:text-[#c2c6d6] hover:bg-[#f2f3fd] dark:hover:bg-[#2e3038] p-2 rounded-lg transition-colors"
          aria-label="Abrir menu"
        >
          <span className="material-symbols-outlined text-[24px]">menu</span>
        </button>
        <div>
          <h1 className="text-[20px] md:text-[24px] font-bold text-[#191b23] dark:text-[#f9f9ff] tracking-tight">
            {title}
          </h1>
        </div>
      </div>

      {/* Right section: Search bar + Actions + Runtime Status */}
      <div className="flex items-center gap-3">
        {/* Search Input */}
        <div className="relative hidden sm:block">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#727785] text-[18px]">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className="pl-9 pr-4 py-1.5 bg-[#f2f3fd] dark:bg-[#2e3038] border border-[#c2c6d6]/50 rounded-full text-[13px] text-[#191b23] dark:text-white placeholder-[#727785] focus:outline-none focus:ring-2 focus:ring-[#0058be]/20 focus:border-[#0058be] w-48 md:w-64 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#727785] hover:text-[#191b23] text-[14px]"
            >
              ✕
            </button>
          )}
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-1">
          <button
            onClick={onCommitClick}
            title="Sincronizar / Commit"
            className="p-2 text-[#424754] dark:text-[#c2c6d6] hover:bg-[#f2f3fd] dark:hover:bg-[#2e3038] rounded-full transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">commit</span>
          </button>
          <button
            onClick={onDeployClick}
            title="Deploy / Publicar"
            className="p-2 text-[#424754] dark:text-[#c2c6d6] hover:bg-[#f2f3fd] dark:hover:bg-[#2e3038] rounded-full transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">rocket_launch</span>
          </button>
        </div>

        {/* RUNTIME OK Badge */}
        <div className="flex items-center gap-2 bg-[#f2f3fd] dark:bg-[#2e3038] px-3 py-1.5 rounded-full border border-[#c2c6d6]/40 shadow-2xs">
          <span className="w-2 h-2 rounded-full bg-[#196b52] animate-pulse"></span>
          <span className="text-[11px] font-bold text-[#0058be] dark:text-[#adc6ff] tracking-wider uppercase">
            RUNTIME OK
          </span>
        </div>
      </div>
    </header>
  );
};
