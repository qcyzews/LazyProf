import { fetchEventSource } from '@microsoft/fetch-event-source';
import { ArticleMetadata, StreamStatus } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export async function searchArticles(
  query: string,
  maxResults: number = 5
): Promise<ArticleMetadata[]> {
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

export interface StreamCallbacks {
  onStatus?: (status: StreamStatus) => void;
  onToken?: (token: string) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export async function analyzeArticlesStream(
  articles: ArticleMetadata[],
  userInstruction: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  model: string = 'gemini-1.5-pro'
): Promise<void> {
  const payload = {
    articles: articles.map((art) => ({
      title: art.title,
      arxiv_id: art.arxiv_id,
      pdf_url: art.pdf_url,
    })),
    user_instruction: userInstruction,
    model: model,
  };

  try {
    await fetchEventSource(`${API_BASE_URL}/analyze-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
      openWhenHidden: true,

      async onopen(response) {
        const contentType = response.headers.get('content-type');

        // Sprawdzamy czy odpowiedź jest poprawna oraz czy serwer zwrócił strumień SSE
        if (response.ok && contentType?.includes('text/event-stream')) {
          return; // Wszystko gra, zaczynamy odbierać strumień
        }

        // Jeśli serwer zwrócił błąd (np. 400, 422, 500), odczytujemy komunikat z JSON/tekstu
        const errText = await response.text().catch(() => '');
        throw new Error(errText || `Błąd serwera (${response.status}): ${response.statusText}`);
      },

      onmessage(msg) {
        if (!msg.data) return;

        try {
          const data = JSON.parse(msg.data);

          switch (msg.event) {
            case 'status':
              callbacks.onStatus?.({
                step: data.step,
                message: data.message,
                progress: data.progress,
              });
              break;

            case 'token':
              if (data.content) {
                callbacks.onToken?.(data.content);
              }
              break;

            case 'complete':
              callbacks.onComplete?.();
              break;

            case 'error':
              callbacks.onError?.(data.message || data.detail || 'Błąd przetwarzania Gemini.');
              break;
          }
        } catch (e) {
          console.error('Błąd parsowania zdarzenia SSE:', e);
        }
      },

      onerror(err) {
        console.error('Błąd połączenia SSE:', err);
        callbacks.onError?.(err?.message || 'Utracono połączenie podczas analizy Gemini.');
    
        // Rzucenie błędu zapobiega zapętleniu ponownych prób (retry loop) przez fetchEventSource
        throw err; 
      },
    });
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      callbacks.onError?.(error.message || 'Wystąpił błąd podczas strumieniowania.');
    }
  }
}

export async function translateReportStream(
  text: string,
  targetLanguage: string = 'Polish',
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const payload = {
    text,
    target_language: targetLanguage,
  };

  try {
    await fetchEventSource(`${API_BASE_URL}/translate-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
      openWhenHidden: true,

      async onopen(response) {
        if (!response.ok) {
          throw new Error(`Błąd inicjalizacji tłumaczenia: ${response.statusText}`);
        }
      },

      onmessage(msg) {
        if (!msg.data) return;

        try {
          const data = JSON.parse(msg.data);

          switch (msg.event) {
            case 'status':
              callbacks.onStatus?.({
                step: 'translating',
                message: data.message,
              });
              break;

            case 'token':
              if (data.content) {
                callbacks.onToken?.(data.content);
              }
              break;

            case 'complete':
              callbacks.onComplete?.();
              break;

            case 'error':
              callbacks.onError?.(data.message || 'Wystąpił błąd podczas tłumaczenia.');
              break;
          }
        } catch (e) {
          console.error('Błąd parsowania zdarzenia tłumaczenia SSE:', e);
        }
      },

      onerror(err) {
        console.error('Błąd połączenia SSE (tłumaczenie):', err);
        callbacks.onError?.(err?.message || 'Utracono połączenie podczas tłumaczenia.');
        throw err;
      },
    });
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      callbacks.onError?.(error.message || 'Wystąpił błąd podczas tłumaczenia.');
    }
  }
}