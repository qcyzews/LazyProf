import React from 'react';
import { StreamStatus } from '@/types';
import { Loader2, Download, Cpu, Sparkles, Languages } from 'lucide-react';

interface StatusIndicatorProps {
  status: StreamStatus | null;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({ status }) => {
  if (!status) return null;

  const getStepDetails = (step: StreamStatus['step']) => {
    switch (step) {
      case 'downloading':
        return {
          icon: <Download className="h-4 w-4 text-amber-500 animate-pulse" />,
          title: 'Pobieranie i przetwarzanie PDF',
          bg: 'bg-amber-50',
          border: 'border-amber-200',
        };
      case 'map':
        return {
          icon: <Cpu className="h-4 w-4 text-blue-500 animate-pulse" />,
          title: 'Gemini: Analiza częściowa (Map)',
          bg: 'bg-blue-50',
          border: 'border-blue-200',
        };
      case 'reduce':
        return {
          icon: <Sparkles className="h-4 w-4 text-indigo-500 animate-pulse" />,
          title: 'Gemini: Synteza i generowanie raportu',
          bg: 'bg-indigo-50',
          border: 'border-indigo-200',
        };
      case 'translating':
        return {
          icon: <Languages className="h-4 w-4 text-emerald-500 animate-pulse" />,
          title: 'Tłumaczenie raportu',
          bg: 'bg-emerald-50',
          border: 'border-emerald-200',
        };
      default:
        return {
          icon: <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />,
          title: 'Przetwarzanie',
          bg: 'bg-slate-50',
          border: 'border-slate-200',
        };
    }
  };

  const details = getStepDetails(status.step);

  return (
    <div className={`rounded-lg border ${details.border} ${details.bg} p-4 shadow-sm transition-all duration-300`}>
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-sm border border-slate-100 shrink-0">
          {details.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="font-bold text-xs uppercase tracking-wider text-slate-800 truncate">
              {details.title}
            </span>
            <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500 shrink-0" />
          </div>
          <p className="text-xs font-medium text-slate-600 mt-0.5 truncate">{status.message}</p>
        </div>
      </div>

      {typeof status.progress === 'number' && (
        <div className="mt-3 w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${Math.min(100, Math.max(0, status.progress))}%` }}
          />
        </div>
      )}
    </div>
  );
};