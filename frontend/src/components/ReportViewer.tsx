import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, Languages, BookOpen, Download, FileText } from 'lucide-react';

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
      {/* Pasek narzędziwy z przyciskami eksportu */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-100 bg-slate-50/80 px-6 py-3.5 gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Literature Synthesis Report</span>
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

      {/* Wyświetlanie treści na pełną szerokość */}
      <div className="p-8 overflow-x-auto text-slate-800 leading-relaxed">
        <div className="prose prose-slate max-w-none prose-headings:font-bold prose-headings:text-slate-900 prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-table:border-collapse prose-th:border prose-th:border-slate-200 prose-th:bg-slate-50 prose-th:p-3 prose-td:border prose-td:border-slate-200 prose-td:p-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
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