'use client';

import React, { useState, useRef } from 'react';
import { ArticleMetadata, StreamStatus } from '@/types';
import { searchArticles, analyzeArticlesStream, translateReportStream } from '@/lib/api';
import { ArticleCard } from '@/components/ArticleCard';
import { StatusIndicator } from '@/components/StatusIndicator';
import { ReportViewer } from '@/components/ReportViewer';
import {
  Search,
  GraduationCap,
  Sparkles,
  Trash2,
  AlertCircle,
  FileText,
  Sliders,
} from 'lucide-react';

export default function Home() {
  // --- Stan wyszukiwania ---
  const [searchQuery, setSearchQuery] = useState('Retrieval Augmented Generation');
  const [maxResults, setMaxResults] = useState(4);
  const [searchResults, setSearchResults] = useState<ArticleMetadata[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // --- Stan wyboru artykułów do koszyka ---
  const [selectedArticles, setSelectedArticles] = useState<ArticleMetadata[]>([]);

  // --- Stan instrukcji użytkownika ---
  const [userInstruction, setUserInstruction] = useState(
    'Compare the RAG architectures proposed in these papers, highlighting their key contributions and comparative benchmarks in a summary table.'
  );

  // --- Stan procesu SSE & Raportu ---
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState<string>('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Controller do przerywania żądań SSE
  const abortControllerRef = useRef<AbortController | null>(null);

  // --- Wyszukiwanie na arXiv ---
  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchError(null);

    try {
      const results = await searchArticles(searchQuery, maxResults);
      setSearchResults(results);
    } catch (err: any) {
      setSearchError(err.message || 'Failed to search articles.');
    } finally {
      setIsSearching(false);
    }
  };

  // --- Przełączanie zaznaczenia artykułu ---
  const toggleArticleSelection = (article: ArticleMetadata) => {
    setSelectedArticles((prev) => {
      const exists = prev.some((a) => a.arxiv_id === article.arxiv_id);
      if (exists) {
        return prev.filter((a) => a.arxiv_id !== article.arxiv_id);
      } else {
        return [...prev, article];
      }
    });
  };

  const clearSelection = () => {
    setSelectedArticles([]);
  };

  // --- Uruchomienie analizy (Generate Synthesis) ---
  const handleStartAnalysis = async () => {
    if (selectedArticles.length === 0) {
      alert('Please select at least one paper for analysis.');
      return;
    }

    setIsAnalyzing(true);
    setStreamError(null);
    setReportMarkdown('');
    setStatus({ step: 'downloading', message: 'Initializing pipeline...' });

    abortControllerRef.current = new AbortController();

    await analyzeArticlesStream(
      selectedArticles,
      userInstruction,
      {
        onStatus: (newStatus) => {
          setStatus(newStatus);
        },
        onToken: (token) => {
          setReportMarkdown((prev) => prev + token);
        },
        onComplete: () => {
          setIsAnalyzing(false);
          setStatus(null);
        },
        onError: (errMessage) => {
          setIsAnalyzing(false);
          setStatus(null);
          setStreamError(errMessage);
        },
      },
      abortControllerRef.current.signal
    );
  };

  // --- Uruchomienie tłumaczenia na język polski ---
  const handleTranslate = async () => {
    if (!reportMarkdown) return;

    setIsTranslating(true);
    setStreamError(null);
    setReportMarkdown(''); // Czyszczenie pod tłumaczenie
    setStatus({ step: 'translating', message: 'Translating report to Polish...' });

    abortControllerRef.current = new AbortController();

    await translateReportStream(
      reportMarkdown,
      'Polish',
      {
        onStatus: (newStatus) => {
          setStatus(newStatus);
        },
        onToken: (token) => {
          setReportMarkdown((prev) => prev + token);
        },
        onComplete: () => {
          setIsTranslating(false);
          setStatus(null);
        },
        onError: (errMessage) => {
          setIsTranslating(false);
          setStatus(null);
          setStreamError(errMessage);
        },
      },
      abortControllerRef.current.signal
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* --- NAGŁÓWEK APLIKACJI --- */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-200">
              <GraduationCap className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-900 leading-none">LazyProf AI</h1>
              <p className="text-xs text-slate-500 mt-0.5">Multi-Paper arXiv Synthesis & RAG Assistant</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 border border-indigo-100">
              <Sparkles className="h-3.5 w-3.5 text-indigo-500" /> Powered by Gemini
            </span>
          </div>
        </div>
      </header>

      {/* --- GŁÓWNY KONTENER --- */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* ================= SEKCJA LEWA: WYSZUKIWARKA & WYNIKI (7 kolumn) ================= */}
          <section className="lg:col-span-7 space-y-6">
            {/* Pasek wyszukiwania */}
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
                <Search className="h-4 w-4 text-indigo-600" /> Search Research Papers on arXiv
              </h2>
              
              <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Enter keywords (e.g. Graph RAG, Long-context LLM)..."
                    className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={maxResults}
                    onChange={(e) => setMaxResults(Number(e.target.value))}
                    className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm bg-white text-slate-700 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value={2}>2 papers</option>
                    <option value={4}>4 papers</option>
                    <option value={6}>6 papers</option>
                  </select>

                  <button
                    type="submit"
                    disabled={isSearching}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    {isSearching ? 'Searching...' : 'Search'}
                  </button>
                </div>
              </form>

              {searchError && (
                <div className="mt-3 flex items-center gap-2 text-xs text-red-600 bg-red-50 p-2.5 rounded-lg border border-red-100">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{searchError}</span>
                </div>
              )}
            </div>

            {/* Wyniki wyszukiwania */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider">
                  Search Results {searchResults.length > 0 && `(${searchResults.length})`}
                </h3>
              </div>

              {searchResults.length === 0 && !isSearching && (
                <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center bg-white/50">
                  <FileText className="h-8 w-8 text-slate-400 mx-auto mb-2" />
                  <p className="text-xs text-slate-500">
                    Use the search bar above to query academic literature from arXiv.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-1 gap-4">
                {searchResults.map((article) => {
                  const isSelected = selectedArticles.some((a) => a.arxiv_id === article.arxiv_id);
                  return (
                    <ArticleCard
                      key={article.arxiv_id}
                      article={article}
                      isSelected={isSelected}
                      onToggleSelect={toggleArticleSelection}
                    />
                  );
                })}
              </div>
            </div>
          </section>


          {/* ================= SEKCJA PRAWA: PANEL ANALIZY & RAPORT (5 kolumn) ================= */}
          <section className="lg:col-span-5 space-y-6">
            
            {/* Panel konfiguracji badania */}
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Sliders className="h-4 w-4 text-indigo-600" /> Research Basket
                </h2>
                {selectedArticles.length > 0 && (
                  <button
                    onClick={clearSelection}
                    className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-red-600 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Clear ({selectedArticles.length})
                  </button>
                )}
              </div>

              {/* Lista wybranych artykułów */}
              <div>
                {selectedArticles.length === 0 ? (
                  <p className="text-xs text-slate-400 italic py-2">
                    No papers selected. Click &quot;Add to Analysis&quot; on search cards.
                  </p>
                ) : (
                  <ul className="space-y-2 max-h-40 overflow-y-auto pr-1">
                    {selectedArticles.map((art) => (
                      <li
                        key={art.arxiv_id}
                        className="flex items-center justify-between gap-2 rounded-lg bg-indigo-50/50 p-2 text-xs border border-indigo-100/60"
                      >
                        <span className="font-medium text-slate-800 truncate">{art.title}</span>
                        <button
                          onClick={() => toggleArticleSelection(art)}
                          className="text-slate-400 hover:text-red-600 flex-shrink-0"
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Instrukcja dla Gemini */}
              <div className="pt-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Research Goal / Custom Prompt
                </label>
                <textarea
                  rows={3}
                  value={userInstruction}
                  onChange={(e) => setUserInstruction(e.target.value)}
                  placeholder="Specify what aspects to focus on (e.g. Compare accuracy, methodology, latency)..."
                  className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-none"
                />
              </div>

              {/* Przycisk generowania */}
              <button
                onClick={handleStartAnalysis}
                disabled={isAnalyzing || isTranslating || selectedArticles.length === 0}
                className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 py-3 text-xs font-bold uppercase tracking-wider text-white shadow-md shadow-indigo-100 hover:bg-indigo-700 disabled:opacity-50 transition-all"
              >
                <Sparkles className="h-4 w-4" />
                {isAnalyzing ? 'Generating Report...' : 'Generate Multi-Paper Synthesis'}
              </button>
            </div>

            {/* Wskaźnik statusu SSE */}
            <StatusIndicator status={status} />

            {/* Błąd strumienia */}
            {streamError && (
              <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 p-3 rounded-lg border border-red-200">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{streamError}</span>
              </div>
            )}

            {/* Wyświetlacz raportu w formacie Markdown */}
            <ReportViewer
              markdownText={reportMarkdown}
              isStreaming={isAnalyzing || isTranslating}
              onTranslate={handleTranslate}
              isTranslating={isTranslating}
            />

          </section>

        </div>
      </main>
    </div>
  );
}