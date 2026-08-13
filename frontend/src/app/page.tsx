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
  AlertCircle,
  ArrowRight,
  BookOpenCheck,
} from 'lucide-react';

export default function Home() {
  // Stan zakładek: 'search' | 'report'
  const [activeTab, setActiveTab] = useState<'search' | 'report'>('search');

  // Wyszukiwanie
  const [searchQuery, setSearchQuery] = useState('Retrieval Augmented Generation');
  const [maxResults, setMaxResults] = useState(4);
  const [searchResults, setSearchResults] = useState<ArticleMetadata[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Koszyk
  const [selectedArticles, setSelectedArticles] = useState<ArticleMetadata[]>([]);

  // Instrukcja
  const [userInstruction, setUserInstruction] = useState(
    'Compare the RAG architectures proposed in these papers, highlighting their key contributions and comparative benchmarks in a summary table.'
  );

  // Raport
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState<string>('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

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

  const toggleArticleSelection = (article: ArticleMetadata) => {
    setSelectedArticles((prev) => {
      const exists = prev.some((a) => a.arxiv_id === article.arxiv_id);
      return exists ? prev.filter((a) => a.arxiv_id !== article.arxiv_id) : [...prev, article];
    });
  };

  const handleGoToReportConfig = () => {
    if (selectedArticles.length === 0) {
      alert('Please select at least one paper first.');
      return;
    }
    setActiveTab('report');
  };

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
        onStatus: (newStatus) => setStatus(newStatus),
        onToken: (token) => setReportMarkdown((prev) => prev + token),
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

  const handleTranslate = async () => {
    if (!reportMarkdown) return;

    setIsTranslating(true);
    setStreamError(null);
    setStatus({ step: 'translating', message: 'Translating report to Polish...' });

    abortControllerRef.current = new AbortController();

    await translateReportStream(
      reportMarkdown,
      'Polish',
      {
        onStatus: (newStatus) => setStatus(newStatus),
        onToken: (token) => setReportMarkdown((prev) => prev + token),
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
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans pb-16">
      {/* NAGŁÓWEK APLIKACJI */}
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

          {/* PASEK PRZEŁĄCZANIA ZAKŁADEK */}
          <div className="flex items-center rounded-lg bg-slate-100 p-1 border border-slate-200">
            <button
              onClick={() => setActiveTab('search')}
              className={`inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-xs font-semibold transition-all ${
                activeTab === 'search'
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Search className="h-3.5 w-3.5" />
              1. Search Papers
              {selectedArticles.length > 0 && (
                <span className="ml-1 rounded-full bg-indigo-600 px-1.5 py-0.5 text-[10px] text-white">
                  {selectedArticles.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('report')}
              className={`inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-xs font-semibold transition-all ${
                activeTab === 'report'
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <BookOpenCheck className="h-3.5 w-3.5" />
              2. Synthesis Report
            </button>
          </div>
        </div>
      </header>

      {/* GŁÓWNA TREŚĆ STRONY */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ================= ZAKŁADKA 1: WYSZUKIWANIE I SELEKCJA ================= */}
        {activeTab === 'search' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-8 space-y-6">
              {/* Formularz wyszukiwarki */}
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
                  <Search className="h-4 w-4 text-indigo-600" /> Search Research Papers on arXiv
                </h2>

                <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Enter keywords..."
                    className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={maxResults}
                      onChange={(e) => setMaxResults(Number(e.target.value))}
                      className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm bg-white"
                    >
                      <option value={2}>2 papers</option>
                      <option value={4}>4 papers</option>
                      <option value={6}>6 papers</option>
                    </select>
                    <button
                      type="submit"
                      disabled={isSearching}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      {isSearching ? 'Searching...' : 'Search'}
                    </button>
                  </div>
                </form>

                {searchError && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-red-600 bg-red-50 p-2.5 rounded-lg">
                    <AlertCircle className="h-4 w-4" />
                    <span>{searchError}</span>
                  </div>
                )}
              </div>

              {/* Lista wyników */}
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4">
                  {searchResults.map((article) => (
                    <ArticleCard
                      key={article.arxiv_id}
                      article={article}
                      isSelected={selectedArticles.some((a) => a.arxiv_id === article.arxiv_id)}
                      onToggleSelect={toggleArticleSelection}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Boczny panel z podglądem koszyka */}
            <div className="lg:col-span-4 space-y-4">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4 sticky top-24">
                <h3 className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center justify-between">
                  <span>Selected Papers ({selectedArticles.length})</span>
                  {selectedArticles.length > 0 && (
                    <button onClick={() => setSelectedArticles([])} className="text-xs text-red-600">
                      Clear
                    </button>
                  )}
                </h3>

                {selectedArticles.length === 0 ? (
                  <p className="text-xs text-slate-400 italic">No papers selected yet.</p>
                ) : (
                  <ul className="space-y-2 max-h-60 overflow-y-auto">
                    {selectedArticles.map((art) => (
                      <li
                        key={art.arxiv_id}
                        className="text-xs bg-indigo-50/50 p-2.5 rounded-lg border border-indigo-100 font-medium"
                      >
                        {art.title}
                      </li>
                    ))}
                  </ul>
                )}

                <button
                  onClick={handleGoToReportConfig}
                  disabled={selectedArticles.length === 0}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 py-3 text-xs font-bold uppercase tracking-wider text-white shadow-md hover:bg-indigo-700 disabled:opacity-50 transition-all"
                >
                  Configure & Generate Report <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ================= ZAKŁADKA 2: SYNTEZA I PEŁNOWYMIAROWY RAPORT ================= */}
        {activeTab === 'report' && (
          <div>
            {selectedArticles.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
                <BookOpenCheck className="mx-auto h-10 w-10 text-slate-300 mb-3" />
                <h3 className="text-sm font-bold text-slate-700">No papers selected for analysis</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Go back to the search tab and select at least one paper.
                </p>
                <button
                  onClick={() => setActiveTab('search')}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
                >
                  <Search className="h-3.5 w-3.5" /> Back to Search
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Panel parametrów zapytania */}
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                    <div>
                      <h2 className="text-base font-bold text-slate-900">Research Parameters & Prompt</h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Analyzing {selectedArticles.length} selected paper(s) with custom synthesis instructions.
                      </p>
                    </div>

                    <button
                      onClick={handleStartAnalysis}
                      disabled={isAnalyzing || isTranslating}
                      className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-md hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      <Sparkles className="h-4 w-4" /> Generate Report
                    </button>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Custom Prompt / Objective
                    </label>
                    <textarea
                      rows={2}
                      value={userInstruction}
                      onChange={(e) => setUserInstruction(e.target.value)}
                      className="w-full rounded-lg border border-slate-300 p-3 text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                    />
                  </div>
                </div>

                {/* Wskaźnik statusu */}
                <StatusIndicator status={status} />

                {streamError && (
                  <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 p-3 rounded-lg border border-red-200">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{streamError}</span>
                  </div>
                )}

                {/* Główny pełnowymiarowy czytnik raportu */}
                <ReportViewer
                  markdownText={reportMarkdown}
                  isStreaming={isAnalyzing || isTranslating}
                  onTranslate={handleTranslate}
                  isTranslating={isTranslating}
                />
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}