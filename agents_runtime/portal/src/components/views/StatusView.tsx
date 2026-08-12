import React from 'react';
import { SystemStatusMetric } from '../../types';

interface StatusViewProps {
  metrics: SystemStatusMetric[];
  searchQuery: string;
}

export const StatusView: React.FC<StatusViewProps> = ({ metrics, searchQuery }) => {
  const filtered = metrics.filter(
    (m) =>
      m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.code.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h2 className="text-[32px] font-bold text-[#191b23] dark:text-white tracking-tight">
          Status / Monitoramento
        </h2>
        <p className="text-[14px] text-[#424754] dark:text-[#c2c6d6] mt-0.5">
          Monitoramento de saúde do sistema e serviços
        </p>
      </div>

      {/* Health Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {filtered.map((item) => {
          const isDegraded = item.status === 'Degraded';

          return (
            <div
              key={item.id}
              className="bg-white dark:bg-[#191b23] border border-[#c2c6d6] dark:border-[#2e3038] rounded-xl p-6 shadow-xs hover:shadow-md transition-shadow duration-300 group flex flex-col justify-between"
            >
              {/* Card Header */}
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-[18px] font-bold text-[#191b23] dark:text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#727785]">
                      {item.name.includes('API')
                        ? 'api'
                        : item.name.includes('Database') || item.name.includes('Vector')
                        ? 'database'
                        : item.name.includes('LLM')
                        ? 'psychology'
                        : item.name.includes('Cloud')
                        ? 'cloud_queue'
                        : 'webhook'}
                    </span>
                    {item.name}
                  </h3>
                  <p className="font-mono text-[12px] text-[#727785] mt-1 bg-[#f2f3fd] dark:bg-[#2e3038] px-2 py-0.5 rounded inline-block">
                    {item.code}
                  </p>
                </div>

                {/* Status Badge */}
                <div
                  className={`px-3 py-1 rounded-full flex items-center gap-1.5 border text-[11px] font-semibold ${
                    isDegraded
                      ? 'bg-[#ffdad6]/40 text-[#b75b00] border-[#b75b00]/30'
                      : 'bg-[#196b52]/10 text-[#196b52] border-[#196b52]/20'
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full animate-pulse ${
                      isDegraded ? 'bg-[#b75b00]' : 'bg-[#196b52]'
                    }`}
                  ></span>
                  {item.status}
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-[#f9f9ff] dark:bg-[#2e3038] p-3 rounded-xl border border-[#e1e2ec] dark:border-[#424754]">
                  <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
                    {item.primaryStatLabel}
                  </p>
                  <p className="text-[20px] font-bold text-[#191b23] dark:text-white">
                    {item.primaryStatValue}
                  </p>
                </div>
                <div className="bg-[#f9f9ff] dark:bg-[#2e3038] p-3 rounded-xl border border-[#e1e2ec] dark:border-[#424754]">
                  <p className="text-[11px] font-bold text-[#424754] dark:text-[#c2c6d6] uppercase tracking-wider mb-1">
                    {item.secondaryStatLabel}
                  </p>
                  <p
                    className={`text-[20px] font-bold ${
                      isDegraded ? 'text-[#b75b00]' : 'text-[#191b23] dark:text-white'
                    }`}
                  >
                    {item.secondaryStatValue}
                  </p>
                </div>
              </div>

              {item.details && (
                <div className="mb-3 space-y-1">
                  {Object.entries(item.details).map(([k, v]) => (
                    <p key={k} className="text-[12px] text-[#424754] dark:text-[#c2c6d6] font-mono">
                      <span className="font-semibold">{k}:</span> {v}
                    </p>
                  ))}
                </div>
              )}

              {/* Sparkline Graphic */}
              <div className="h-14 w-full mt-2 relative overflow-hidden rounded-lg bg-[#f2f3fd]/50 dark:bg-[#2e3038]/50 p-1">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
                  {isDegraded ? (
                    <>
                      <path
                        d="M0 100 L0 60 L10 50 L20 80 L30 40 L40 90 L50 30 L60 85 L70 20 L80 75 L90 10 L100 60 L100 100 Z"
                        fill="rgba(183, 91, 0, 0.15)"
                      />
                      <polyline
                        fill="none"
                        points="0,60 10,50 20,80 30,40 40,90 50,30 60,85 70,20 80,75 90,10 100,60"
                        stroke="#b75b00"
                        strokeWidth="2.5"
                        vectorEffect="non-scaling-stroke"
                      />
                    </>
                  ) : (
                    <>
                      <path
                        d="M0 100 L0 65 L15 60 L30 70 L45 55 L60 62 L75 50 L90 58 L100 45 L100 100 Z"
                        fill="rgba(25, 107, 82, 0.15)"
                      />
                      <polyline
                        fill="none"
                        points="0,65 15,60 30,70 45,55 60,62 75,50 90,58 100,45"
                        stroke="#196b52"
                        strokeWidth="2.5"
                        vectorEffect="non-scaling-stroke"
                      />
                    </>
                  )}
                </svg>
              </div>
            </div>
          );
        })}
      </div>

      {/* Global Metrics Footer Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-[#c2c6d6]/40">
        <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-4 rounded-xl border border-[#c2c6d6]/40">
          <p className="text-[11px] font-bold text-[#424754] uppercase tracking-wider mb-1">
            Requisições 24h
          </p>
          <p className="text-[22px] font-bold text-[#191b23] dark:text-white">3.840</p>
        </div>

        <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-4 rounded-xl border border-[#c2c6d6]/40">
          <p className="text-[11px] font-bold text-[#424754] uppercase tracking-wider mb-1">
            Erros 5xx (24h)
          </p>
          <p className="text-[22px] font-bold text-[#196b52]">0.01%</p>
        </div>

        <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-4 rounded-xl border border-[#c2c6d6]/40">
          <p className="text-[11px] font-bold text-[#424754] uppercase tracking-wider mb-1">
            Tempo Médio
          </p>
          <p className="text-[22px] font-bold text-[#191b23] dark:text-white">1.45s</p>
        </div>

        <div className="bg-[#f2f3fd] dark:bg-[#2e3038] p-4 rounded-xl border border-[#c2c6d6]/40">
          <p className="text-[11px] font-bold text-[#424754] uppercase tracking-wider mb-1">
            Módulo
          </p>
          <p className="text-[14px] font-mono font-bold text-[#0058be] dark:text-[#adc6ff]">
            Agentes v2.3.7
          </p>
        </div>
      </div>
    </div>
  );
};
