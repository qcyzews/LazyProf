// /frontend/src/types/index.ts
export interface ArticleMetadata {
  arxiv_id: string;
  title: string;
  authors: string[];
  published: string;
  summary: string;
  pdf_url: string;
}

export interface StreamStatus {
  step: 'downloading' | 'map' | 'reduce' | 'translating';
  message: string;
  progress?: number; // np. 0-100% dla etapu przetwarzania artykułów
}

export interface SearchResponse {
  original_query: string;
  expanded_query: string;
  articles: ArticleMetadata[];
}

export type AnalysisMode = 'fast' | 'medium' | 'high';

export interface MultiPaperGroundedRequest {
  arxiv_ids: string[];
  user_instruction: string;
  mode?: AnalysisMode;
}