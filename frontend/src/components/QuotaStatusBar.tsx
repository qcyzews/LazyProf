// src/components/QuotaStatusBar.tsx
import React from 'react';
import { ModeStatus } from '@/types';
import { Zap, Cpu, BrainCircuit, RefreshCw } from 'lucide-react';

interface QuotaStatusBarProps {
  modes?: Record<string, ModeStatus | undefined>;
  onRefresh?: () => void;
  isLoading?: boolean;
}

export const QuotaStatusBar: React.FC<QuotaStatusBarProps> = ({ modes, onRefresh, isLoading }) => {
  if (!modes) return null;

  const modeIcons: Record<string, React.ReactNode> = {
    fast: <Zap className="h-3.5 w-3.5 text-amber-500" />,
    medium: <Cpu className="h-3.5 w-3.5 text-indigo-500" />,
    high: <BrainCircuit className="h-3.5 w-3.5 text-purple-600" />
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-white text-slate-700 text-xs rounded-xl shadow-sm border border-slate-200">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-bold text-slate-500 uppercase tracking-wider text-[10px]">
          API Quota (RPD):
        </span>
        {Object.entries(modes).map(([modeKey, info]) => {
          if (!info) return null;
          const isExhausted = !info.available || info.remaining_rpd <= 0;

          return (
            <div
              key={modeKey}
              className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200"
            >
              {modeIcons[modeKey] || <Zap className="h-3 w-3 text-slate-400" />}
              <span className="font-semibold capitalize text-slate-800">{modeKey}:</span>
              <span className="font-mono text-[10px] text-slate-400">({info.model_name})</span>
              <span
                className={`font-mono font-bold ${
                  isExhausted ? 'text-rose-600' : 'text-emerald-600'
                }`}
              >
                {info.remaining_rpd}/{info.max_rpd}
              </span>
            </div>
          );
        })}
      </div>

      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors disabled:opacity-50"
          title="Odśwież stan limitów"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Odśwież</span>
        </button>
      )}
    </div>
  );
};