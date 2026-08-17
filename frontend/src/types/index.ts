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