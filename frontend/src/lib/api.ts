// /frontend/src/lib/api.ts
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { ArticleMetadata, StreamStatus, SearchResponse, ModeStatus, StatusResponse } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// --- INTERFEJSY ---

export interface StreamCallbacks {
  onStatus?: (status: StreamStatus & { resetStream?: boolean }) => void;
  /**
   * @param token Przekazywany fragment tekstu
   * @param resetStream Jeśli true, sygnalizuje konieczność wyczyszczenia dotychczasowego bufora tekstu w UI
   */
  onToken?: (token: string, resetStream?: boolean) => void;
  onReport?: (report: {
    analysis_markdown: string;
    is_valid: boolean;
    audit_trail: string[];
    arxiv_ids: string[];
  }) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export interface GroundedAnalysisRequest {
  arxiv_ids: string[];
  user_instruction?: string;
  mode?: 'fast' | 'medium' | 'high';
}

export interface GroundedAnalysisResponse {
  arxiv_ids: string[];
  total_attempts: number;
  is_valid: boolean;
  analysis_markdown: string;
  audit_trail: string[];
}

export interface TranslatePayload {
  text: string;
  target_language?: string;
  audit_trail?: any[];
  arxiv_ids?: string[];
  is_valid?: boolean;
}



// --- METODY REST ---

/**
 * Wyszukuje artykuły w serwisie arXiv na podstawie zapytania.
 */
export async function searchArticles(
  query: string,
  maxResults: number = 5
): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, max_results: maxResults }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Nie udało się pobrać artykułów z arXiv.');
  }

  return response.json();
}

/**
 * Wykonuje grounded analysis w trybie synchronicznym (REST request/response).
 */
export async function runGroundedAnalysis(
  payload: GroundedAnalysisRequest
): Promise<GroundedAnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/run-grounded-analysis`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || errorData.message || `Błąd API (${response.status}): ${response.statusText}`
    );
  }

  return response.json();
}

/**
 * Pobiera ogólny status systemu oraz limity RPD dla poszczególnych trybów.
 */
export async function getSystemStatus(): Promise<StatusResponse> {
  const response = await fetch(`${API_BASE_URL}/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Nie udało się pobrać statusu systemu.');
  }

  return response.json();
}

// --- METODY SSE (STRUMIENIOWANIE) ---

/**
 * Strumieniowa analiza artykułów (SSE).
 */
export async function analyzeArticlesStream(
  articles: ArticleMetadata[],
  userInstruction: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  model: string = 'gemini-3.1-flash-lite'
): Promise<void> {
  const payload = {
    articles: articles.map((art) => ({
      title: art.title,
      arxiv_id: art.arxiv_id,
      pdf_url: art.pdf_url,
    })),
    user_instruction: userInstruction,
    model,
  };

  await handleSSEStream(`${API_BASE_URL}/analyze-stream`, payload, callbacks, signal);
}

/**
 * Strumieniowe tłumaczenie raportu (SSE).
 */


export async function translateReportStream(
  payload: TranslatePayload,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  // Domyślny język, jeśli nie podano
  const requestBody = {
    target_language: 'Polish',
    ...payload,
  };

  await handleSSEStream(`${API_BASE_URL}/translate-stream`, requestBody, callbacks, signal);
}

/**
 * Strumieniowa wersja Grounded Analysis (LangGraph SSE).
 */
export async function runGroundedAnalysisStream(
  payload: GroundedAnalysisRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  await handleSSEStream(`${API_BASE_URL}/run-grounded-analysis-stream`, payload, callbacks, signal);
}

// --- HELPER STRUMIENIOWANIA ---

/**
 * Uniwersalna funkcja do obsługi połączeń SSE via fetchEventSource.
 */
async function handleSSEStream(
  endpoint: string,
  payload: unknown,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  try {
    await fetchEventSource(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
      openWhenHidden: true,

      async onopen(response) {
        const contentType = response.headers.get('content-type');
        if (response.ok && contentType?.includes('text/event-stream')) {
          return;
        }
        const errText = await response.text().catch(() => '');
        throw new Error(errText || `Błąd połączenia z serwerem (${response.status})`);
      },

      onmessage(msg) {
        //console.log('🔍 [RAW SSE MSG]:', {
        //  event: msg.event,
        //  data: msg.data
        //});
        if (!msg.data) return;

        try {
          const data = JSON.parse(msg.data);
          //console.log('🔍 [Parsed SSE Data]:', data);
          // 1. Wykrywanie typu zdarzenia (sprawdzamy nagłówek SSE oraz wnętrze obiektu JSON)
          const eventType = msg.event

          // Log pomocniczy do weryfikacji w konsoli przeglądarki
          //console.log(`📡 [SSE Raw Message]: event='${eventType}'`, data);

          switch (msg.event) {
            case 'status': {
              const shouldReset = Boolean(data.reset_stream);

              callbacks.onStatus?.({
                step: data.step || 'downloading',
                message: data.message,
                progress: data.progress,
                resetStream: shouldReset,
              });
              break;
            }

            case 'token': {
              // Safe-fallback: sprawdzamy 'token', 'content' oraz surowy string
              const tokenContent = 
                typeof data === 'string' ? data :
                (data.token ?? data.content ?? '');

              const shouldReset = Boolean(data.resetStream || data.reset_stream);

              if (tokenContent || shouldReset) {
                callbacks.onToken?.(tokenContent, shouldReset);
              }
              break;
            }

            case 'report': {
              callbacks.onReport?.({
                analysis_markdown: data.analysis_markdown || data.content || '',
                is_valid: Boolean(data.is_valid),
                audit_trail: data.audit_trail || [],
                arxiv_ids: data.arxiv_ids || [],
              });
              break;
            }

            case 'complete':
              callbacks.onComplete?.();
              break;

            case 'error':
              callbacks.onError?.(data.message || data.detail || 'Wystąpił błąd podczas przetwarzania.');
              break;
          }
        } catch (e) {
          console.error('Błąd parsowania zdarzenia SSE:', e);
          //console.log('📝 [RAW TEXT DATA]:', msg.data);
        }
      },

      onerror(err) {
        console.error(`Błąd połączenia SSE (${endpoint}):`, err);
        callbacks.onError?.(err?.message || 'Utracono połączenie z serwerem.');
        throw err;
      },
    });
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      callbacks.onError?.(error.message || 'Wystąpił błąd połączenia.');
    }
  }
}