import React from 'react';
import { StreamStatus } from '@/types';
import { Loader2, Download, Cpu, Sparkles, Languages } from 'lucide-react';

interface StatusIndicatorProps {
  status: StreamStatus | null;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({ status }) => {
  if (!status) return null;

  const getStepIcon = (step: StreamStatus['step']) => {
    switch (step) {
      case 'downloading':
        return <Download className="h-4 w-4 text-amber-500 animate-pulse" />;
      case 'map':
        return <Cpu className="h-4 w-4 text-blue-500 animate-pulse" />;
      case 'reduce':
        return <Sparkles className="h-4 w-4 text-indigo-500 animate-pulse" />;
      case 'translating':
        return <Languages className="h-4 w-4 text-emerald-500 animate-pulse" />;
      default:
        return <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />;
    }
  };

  return (
    <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4 text-sm text-indigo-900 shadow-sm animate-in fade-in duration-300">
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-sm border border-indigo-100">
        {getStepIcon(status.step)}
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-xs uppercase tracking-wider text-indigo-600">
            {status.step.toUpperCase()} STEP
          </span>
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
        </div>
        <p className="text-xs font-medium text-slate-700 mt-0.5">{status.message}</p>
      </div>
    </div>
  );
};