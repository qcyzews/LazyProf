// /frontend/src/components/About.tsx
'use client';

import React from 'react';
import {
  GraduationCap,
  Search,
  Workflow,
  ShieldCheck,
  Cpu,
  Code2,
} from 'lucide-react';
import { SupportBlock } from './SupportBlock';

export function About() {
  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Wstęp */}
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-3 bg-indigo-50 rounded-xl text-indigo-600 border border-indigo-100">
            <GraduationCap className="h-7 w-7" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900">About LazyProf AI</h2>
            <p className="text-xs text-slate-500">
              Grounded Multi-Paper Academic Research & Synthesis Engine
            </p>
          </div>
        </div>
        <p className="text-sm text-slate-600 leading-relaxed">
          <strong>LazyProf AI</strong> is an automated scientific literature analysis platform. It enables
          researchers and engineers to query arXiv, select multiple related papers, extract their full-text PDF
          content, and run comparative cross-paper synthesis backed by verifiable citations and strict anti-hallucination verification loops.
        </p>

        <div className="mt-4 p-3.5 bg-slate-50 rounded-xl border border-slate-200/60 text-xs text-slate-600 flex items-start gap-2.5">
          <Code2 className="h-4 w-4 text-indigo-500 shrink-0 mt-0.5" />
          <span>
            This tool was built as a side project experimenting with practical AI applications that demand <strong>strict factual accuracy, high reliability, and determinism</strong>.
          </span>
        </div>
      </div>

      {/* Kluczowe filary architektury */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="h-10 w-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-4 border border-blue-100">
            <Search className="h-5 w-5" />
          </div>
          <h3 className="text-sm font-bold text-slate-900 mb-2">1. arXiv Search & Expansion</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Query understanding expands search keywords into specialized academic vocabulary to query arXiv API and retrieve precise PDF preprints.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="h-10 w-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4 border border-indigo-100">
            <Workflow className="h-5 w-5" />
          </div>
          <h3 className="text-sm font-bold text-slate-900 mb-2">2. Grounded Multi-Node RAG</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            PDFs are parsed into structured text sections. The engine processes document tokens with variable reasoning budgets (Fast, Medium, High).
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="h-10 w-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <h3 className="text-sm font-bold text-slate-900 mb-2">3. Fact-Checking & Auditing</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Synthesized claims are audited against raw source chunks. If hallucinations or inaccurate citations occur, a self-correction loop fixes the report.
          </p>
        </div>
      </div>

      {/* Schemat przepływu danych */}
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm space-y-6">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Cpu className="h-5 w-5 text-indigo-600" /> Execution Pipeline Overview
        </h3>

        <div className="space-y-4 text-xs text-slate-600">
          <div className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
              1
            </span>
            <div>
              <strong className="text-slate-900 font-semibold">Document Fetch & Parsing:</strong> Raw PDF files are streamed from arXiv mirrors, extracted, and structured into sections (Abstract, Methodology, Results, Discussion).
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
              2
            </span>
            <div>
              <strong className="text-slate-900 font-semibold">Contextual Grounding:</strong> Ingestion engine builds token-optimized chunks to stay within model attention limits while retaining cross-document relationships.
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
              3
            </span>
            <div>
              <strong className="text-slate-900 font-semibold">Server-Sent Events (SSE) Streaming:</strong> Real-time tokens and node execution statuses stream back to the Next.js UI for low-latency visual feedback.
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
              4
            </span>
            <div>
              <strong className="text-slate-900 font-semibold">Audit & Translation:</strong> An autonomous critic agent validates claims, outputs an audit trail with confidence flags, and supports grounded Polish translation without losing citation mappings.
            </div>
          </div>
        </div>
      </div>

      {/* SEKCJA WSPARCIA I FEEDBACKU (Odkomentuj/Zakomentuj w zależności od potrzeb) */}
      <SupportBlock showBuyMeACoffee={false} />

      {/* Tech Stack */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide mb-4">
          Technology Stack
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-slate-400 block text-[10px]">Frontend</span>
            <span className="font-semibold text-slate-800">Next.js 15 & React 19</span>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-slate-400 block text-[10px]">Styling</span>
            <span className="font-semibold text-slate-800">Tailwind CSS</span>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-slate-400 block text-[10px]">Runtime</span>
            <span className="font-semibold text-slate-800">Node.js 22 LTS</span>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-slate-400 block text-[10px]">Deployment</span>
            <span className="font-semibold text-slate-800">Vercel & GitHub Actions</span>
          </div>
        </div>
      </div>
    </div>
  );
}