// /frontend/src/components/ReportViewer.tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BookOpen, Languages, Copy, Check, FileText, Download, ExternalLink, Cpu } from 'lucide-react';
import { ArticleMetadata, AnalysisMode } from '@/types';

interface ReportViewerProps {
  markdownText: string;
  isStreaming: boolean;
  onTranslate?: () => void;
  isTranslating?: boolean;
  selectedArticles?: ArticleMetadata[];
  analysisMode?: AnalysisMode;
}

// --- Dedykowane style dla elementów Markdown ---
const customMarkdownComponents = {
  // 1. Zwiększone odstępy między punktami listy (rozwiązuje problem zlewającego się tekstu)
  li: ({ children }: any) => (
    <li className="mb-3.5 leading-relaxed text-slate-800 last:mb-0">
      {children}
    </li>
  ),
  // 2. Tabele z własnym przewijaniem, ramkami i poprawionym paddingiem
  table: ({ children }: any) => (
    <div className="my-6 overflow-x-auto rounded-lg border border-slate-200 shadow-2xs">
      <table className="w-full text-left text-sm border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="border-b border-slate-200 bg-slate-100/80 px-4 py-3 font-semibold text-slate-800">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="border-b border-slate-100 px-4 py-3 text-slate-700 align-top">
      {children}
    </td>
  ),
  // 3. Stylizacja cytatów / Raportu Rzetelności (niebieskie tło i wcięcie zamiast szarych kresek)
  blockquote: ({ children }: any) => (
    <blockquote className="my-4 rounded-r-lg border-l-4 border-indigo-500 bg-indigo-50/40 px-4 py-3 text-slate-700 not-italic prose-p:my-1">
      {children}
    </blockquote>
  ),
  // 4. Stylizacja linków (np. do PDF / arXiv)
  a: ({ href, children }: any) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-indigo-600 underline underline-offset-2 hover:text-indigo-800 transition-colors"
    >
      {children}
    </a>
  ),
  // 5. Stylizacja nagłówków
  h2: ({ children }: any) => (
    <h2 className="mt-8 mb-4 text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">
      {children}
    </h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="mt-6 mb-3 text-lg font-bold text-slate-800">
      {children}
    </h3>
  ),
};

export const ReportViewer: React.FC<ReportViewerProps> = ({
  markdownText,
  isStreaming,
  onTranslate,
  isTranslating = false,
  selectedArticles = [],
  analysisMode,
}) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(markdownText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // --- Eksport do pliku Markdown (.md) ---
  const handleDownloadMarkdown = () => {
    const blob = new Blob([markdownText], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'LazyProf_Report.md');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // --- Eksport do pliku PDF (.pdf) ---
  const handleDownloadPDF = async () => {
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
      const response = await fetch(`${baseUrl}/export-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown: markdownText }),
      });

      if (!response.ok) throw new Error('PDF generation failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'LazyProf_Report.pdf');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      alert('Failed to generate PDF. Make sure WeasyPrint is installed on backend.');
    }
  };

  if (!markdownText && !isStreaming) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 p-16 text-center bg-white">
        <BookOpen className="h-12 w-12 text-slate-300 mb-3" />
        <h3 className="text-base font-semibold text-slate-700">No report generated yet</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-md">
          Select research papers in the Search tab, configure your research objective, and run the pipeline.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Pasek narzędziowy z przyciskami eksportu */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-100 bg-slate-50/80 px-6 py-3.5 gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Literature Synthesis Report
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {onTranslate && (
            <button
              onClick={onTranslate}
              disabled={isStreaming || isTranslating || !markdownText}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              <Languages className="h-3.5 w-3.5 text-indigo-600" />
              {isTranslating ? 'Translating...' : 'Translate to Polish'}
            </button>
          )}

          <button
            onClick={handleCopy}
            disabled={!markdownText}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5 text-slate-500" />}
            Copy
          </button>

          <button
            onClick={handleDownloadMarkdown}
            disabled={!markdownText || isStreaming}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            <FileText className="h-3.5 w-3.5 text-blue-600" /> Export .MD
          </button>

          <button
            onClick={handleDownloadPDF}
            disabled={!markdownText || isStreaming}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Download className="h-3.5 w-3.5" /> Export PDF
          </button>
        </div>
      </div>

      {/* Pasek metadanych raportu */}
      {(selectedArticles.length > 0 || analysisMode) && (
        <div className="bg-slate-50/50 border-b border-slate-100 px-6 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs">
          {analysisMode && (
            <div className="flex items-center gap-1.5 text-slate-500">
              <Cpu className="h-3.5 w-3.5 text-indigo-500" />
              <span>Execution Mode:</span>
              <span className="font-semibold text-slate-700 uppercase text-[10px] bg-slate-200/70 px-2 py-0.5 rounded-md tracking-wide">
                {analysisMode}
              </span>
            </div>
          )}

          {selectedArticles.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 font-medium">Grounded Papers ({selectedArticles.length}):</span>
              <div className="flex flex-wrap gap-1.5 max-w-2xl">
                {selectedArticles.map((art) => (
                  <a
                    key={art.arxiv_id}
                    href={art.pdf_url}
                    target="_blank"
                    rel="noreferrer"
                    title={art.title}
                    className="inline-flex items-center gap-1 bg-white border border-slate-200 px-2 py-0.5 rounded text-[11px] text-slate-700 hover:border-indigo-300 hover:text-indigo-600 transition-colors shadow-2xs"
                  >
                    <span className="font-mono text-slate-400">[{art.arxiv_id}]</span>
                    <span className="truncate max-w-[140px] font-medium">{art.title}</span>
                    <ExternalLink className="h-2.5 w-2.5 text-slate-400 shrink-0" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Wyświetlanie treści na pełną szerokość */}
      <div className="p-8 overflow-x-auto text-slate-800 leading-relaxed">
        <div className="prose prose-slate max-w-none prose-blockquote:not-italic prose-blockquote:font-normal">
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            components={customMarkdownComponents}
          >
            {markdownText}
          </ReactMarkdown>
        </div>

        {isStreaming && (
          <span className="inline-block h-5 w-2 ml-1 bg-indigo-600 animate-pulse align-middle" />
        )}
      </div>
    </div>
  );
};