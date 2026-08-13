import React from 'react';
import { ArticleMetadata } from '@/types';
import { ExternalLink, CheckCircle2, PlusCircle, Calendar, User } from 'lucide-react';

interface ArticleCardProps {
  article: ArticleMetadata;
  isSelected: boolean;
  onToggleSelect: (article: ArticleMetadata) => void;
}

export const ArticleCard: React.FC<ArticleCardProps> = ({
  article,
  isSelected,
  onToggleSelect,
}) => {
  return (
    <div
      className={`relative flex flex-col justify-between rounded-xl border p-5 transition-all duration-200 shadow-sm ${
        isSelected
          ? 'border-indigo-500 bg-indigo-50/30 ring-2 ring-indigo-500/20'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-md'
      }`}
    >
      <div>
        {/* Górny nagłówek karty */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <span className="inline-flex items-center rounded-md bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
            arXiv:{article.arxiv_id}
          </span>
          <button
            onClick={() => onToggleSelect(article)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              isSelected
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {isSelected ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" /> Selected
              </>
            ) : (
              <>
                <PlusCircle className="h-3.5 w-3.5" /> Add to Analysis
              </>
            )}
          </button>
        </div>

        {/* Tytuł */}
        <h3 className="text-base font-bold text-slate-900 leading-snug mb-2 line-clamp-2">
          {article.title}
        </h3>

        {/* Autorzy i data */}
        <div className="flex flex-wrap items-center gap-y-1 gap-x-4 text-xs text-slate-500 mb-3">
          <div className="flex items-center gap-1">
            <User className="h-3.5 w-3.5 text-slate-400" />
            <span className="truncate max-w-[200px]">
              {article.authors.slice(0, 3).join(', ')}
              {article.authors.length > 3 && ' et al.'}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Calendar className="h-3.5 w-3.5 text-slate-400" />
            <span>{article.published}</span>
          </div>
        </div>

        {/* Abstrakt / Podsumowanie */}
        <p className="text-xs text-slate-600 leading-relaxed line-clamp-3 mb-4">
          {article.summary}
        </p>
      </div>

      {/* Stopka karty z linkiem do PDF */}
      <div className="pt-3 border-t border-slate-100 flex justify-end">
        <a
          href={article.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
        >
          View arXiv PDF <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
};