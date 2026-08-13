import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, Languages, BookOpen } from 'lucide-react';

interface ReportViewerProps {
  markdownText: string;
  isStreaming: boolean;
  onTranslate?: () => void;
  isTranslating?: boolean;
}

export const ReportViewer: React.FC<ReportViewerProps> = ({
  markdownText,
  isStreaming,
  onTranslate,
  isTranslating = false,
}) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(markdownText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!markdownText && !isStreaming) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 p-12 text-center bg-slate-50/50">
        <BookOpen className="h-10 w-10 text-slate-400 mb-3" />
        <h3 className="text-sm font-semibold text-slate-700">No report generated yet</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Select research papers, enter your research goal or prompt, and click &quot;Generate Synthesis&quot; to build a custom multi-paper review.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Pasek narzędziwy raportu */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          <span className="text-xs font-semibold text-slate-700">Generated Literature Synthesis</span>
        </div>

        <div className="flex items-center gap-2">
          {onTranslate && (
            <button
              onClick={onTranslate}
              disabled={isStreaming || isTranslating || !markdownText}
              className="inline-flex items-center gap-1.5 rounded-md bg-white border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              <Languages className="h-3.5 w-3.5 text-indigo-600" />
              {isTranslating ? 'Translating...' : 'Translate to Polish'}
            </button>
          )}

          <button
            onClick={handleCopy}
            disabled={!markdownText}
            className="inline-flex items-center gap-1.5 rounded-md bg-white border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-600" /> Copied
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5 text-slate-500" /> Copy Markdown
              </>
            )}
          </button>
        </div>
      </div>

      {/* Treść raportu z klasami Prose dla czytelności */}
      <div className="p-6 md:p-8 overflow-x-auto text-slate-800 leading-relaxed text-sm">
        <div className="prose prose-slate max-w-none prose-headings:font-bold prose-headings:text-slate-900 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-table:border-collapse prose-th:border prose-th:border-slate-200 prose-th:bg-slate-50 prose-th:p-2 prose-td:border prose-td:border-slate-200 prose-td:p-2">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {markdownText}
          </ReactMarkdown>
        </div>

        {/* Kursor wskazujący aktywny strumień */}
        {isStreaming && (
          <span className="inline-block h-4 w-2 ml-1 bg-indigo-600 animate-pulse align-middle" />
        )}
      </div>
    </div>
  );
};