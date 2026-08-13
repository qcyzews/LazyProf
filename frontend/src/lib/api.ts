import { fetchEventSource } from '@microsoft/fetch-event-source';
import { ArticleMetadata, StreamStatus } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

/**
 * Przeszukuje bazy arXiv poprzez backend FastAPI.
 */
export async function searchArticles(query: string, maxResults: number = 5): Promise<ArticleMetadata[]> {
  const response = await fetch(`${API_BASE_URL}/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      max_results: maxResults,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch articles from arXiv.');
  }

  return response.json();
}

export interface StreamCallbacks {
  onStatus?: (status: StreamStatus) => void;
  onToken?: (token: string) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

/**
 * Nawiązuje połączenie SSE z endpointem /analyze-stream i przekazuje zdarzenia do callbacków.
 */
export async function analyzeArticlesStream(
  articles: ArticleMetadata[],
  userInstruction: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const payload = {
    articles: articles.map((art) => ({
      title: art.title,
      arxiv_id: art.arxiv_id,
      pdf_url: art.pdf_url,
    })),
    user_instruction: userInstruction,
  };

  try {
    await fetchEventSource(`${API_BASE_URL}/analyze-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal,
      openWhenHidden: true, // Kontynuuj strumieniowanie nawet po przełączeniu karty w przeglądarce

      async onopen(response) {
        if (!response.ok) {
          throw new Error(`Failed to initialize analysis stream: ${response.statusText}`);
        }
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
              callbacks.onError?.(data.message || data.detail || 'An unexpected error occurred.');
              break;

            default:
              break;
          }
        } catch (e) {
          console.error('Error parsing SSE event data:', e);
        }
      },

      onerror(err) {
        console.error('SSE Connection Error:', err);
        callbacks.onError?.(err?.message || 'Connection lost during analysis stream.');
        throw err; // Zapobiega automatycznym ponownym próbom w przypadku błędu
      },
    });
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      callbacks.onError?.(error.message || 'Error executing stream.');
    }
  }
}

/**
 * Nawiązuje połączenie SSE z endpointem /translate-stream i przekazuje przetłumaczone tokeny na żywo.
 */
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
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal,
      openWhenHidden: true,

      async onopen(response) {
        if (!response.ok) {
          throw new Error(`Failed to initialize translation stream: ${response.statusText}`);
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
              callbacks.onError?.(data.message || data.detail || 'An unexpected translation error occurred.');
              break;

            default:
              break;
          }
        } catch (e) {
          console.error('Error parsing translation SSE data:', e);
        }
      },

      onerror(err) {
        console.error('SSE Translation Error:', err);
        callbacks.onError?.(err?.message || 'Connection lost during translation stream.');
        throw err;
      },
    });
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      callbacks.onError?.(error.message || 'Error executing translation stream.');
    }
  }
}