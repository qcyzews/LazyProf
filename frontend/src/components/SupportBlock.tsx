'use client';

import React from 'react';
import {
  Heart,
  MessageSquare,
  ExternalLink,
} from 'lucide-react';

// SVG Dedykowana ikona LinkedIn
function LinkedInIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
    </svg>
  );
}

interface SupportBlockProps {
  showBuyMeACoffee?: boolean;
}

export function SupportBlock({ showBuyMeACoffee = false }: SupportBlockProps) {
  return (
    <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/60 via-white to-purple-50/40 p-8 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-indigo-100 pb-5">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Heart className="h-5 w-5 text-rose-500 fill-rose-500/20" /> Support & Shape the Future
          </h3>
          <p className="text-xs text-slate-600 mt-1">
            Have feedback, feature ideas, or want to connect? Your input is immensely appreciated!
          </p>
        </div>

        {/* Przycisk LinkedIn */}
        <a
          href="https://www.linkedin.com/in/rczyzewski" 
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 transition-colors shrink-0"
        >
          <LinkedInIcon className="h-4 w-4 text-blue-400" />
          Connect on LinkedIn
          <ExternalLink className="h-3 w-3 opacity-60" />
        </a>
      </div>

      <div className={`grid grid-cols-1 ${showBuyMeACoffee ? 'md:grid-cols-2' : ''} gap-4`}>
        {/* Karta Donacji (Opcjonalna / Domyślnie Ukryta) */}
        {showBuyMeACoffee && (
          <div className="p-5 rounded-xl border border-slate-200/80 bg-white/80 backdrop-blur-sm space-y-3">
            <div className="flex items-center gap-2 text-slate-900 font-bold text-xs">
              <span className="p-1.5 bg-amber-50 rounded-lg border border-amber-200 text-amber-600">☕</span>
              Support Project Infrastructure
            </div>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Running high-precision LLM reasoning pipelines and processing multi-page arXiv PDFs requires continuous API budget.
            </p>
            <a
              href="https://buymeacoffee.com/czyzewski"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 w-full rounded-lg bg-amber-500 hover:bg-amber-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition-colors"
            >
              <Heart className="h-3.5 w-3.5 fill-white" /> Buy Me a Coffee / Support API
            </a>
          </div>
        )}

        {/* Karta GitHub Issues / Feedback */}
        <div className="p-5 rounded-xl border border-slate-200/80 bg-white/80 backdrop-blur-sm space-y-3">
          <div className="flex items-center gap-2 text-slate-900 font-bold text-xs">
            <span className="p-1.5 bg-blue-50 rounded-lg border border-blue-200 text-blue-600">
              <MessageSquare className="h-3.5 w-3.5" />
            </span>
            Share Feedback & Feature Ideas
          </div>
          <p className="text-[11px] text-slate-600 leading-relaxed">
            Help steer development toward what matters most to your research workflow. Found a bug or need a specific export format?
          </p>
          <a
            href="https://github.com/qcyzews/LazyProf/issues/new/choose"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 w-full sm:w-auto rounded-lg bg-indigo-600 hover:bg-indigo-700 px-5 py-2 text-xs font-bold text-white shadow-sm transition-colors"
          >
            <MessageSquare className="h-3.5 w-3.5" /> Submit Feedback on GitHub
          </a>
        </div>
      </div>
    </div>
  );
}