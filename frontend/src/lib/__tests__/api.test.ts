import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  searchArticles,
  runGroundedAnalysis,
  analyzeArticlesStream,
  translateReportStream,
  runGroundedAnalysisStream,
  StreamCallbacks,
} from '../api';
import { fetchEventSource } from '@microsoft/fetch-event-source';

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn(),
}));

describe('api.ts test suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  describe('searchArticles', () => {
    it('returns articles on successful search with default maxResults', async () => {
      const mockResponse = {
        original_query: 'RAG',
        expanded_query: 'RAG LLM',
        articles: [
          {
            arxiv_id: '1234.5678',
            title: 'Paper Title',
            authors: ['Author A'],
            published: '2024-01-01',
            summary: 'Summary text',
            pdf_url: 'https://arxiv.org/pdf/1234.5678.pdf',
          },
        ],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as unknown as Response);

      const result = await searchArticles('RAG');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/search'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ query: 'RAG', max_results: 5 }),
        })
      );
      expect(result).toEqual(mockResponse);
    });

    it('throws custom error message from server when response is not ok', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Backend failure' }),
      } as unknown as Response);

      await expect(searchArticles('Test', 2)).rejects.toThrow('Backend failure');
    });

    it('throws default error when server response fails without detail', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      } as unknown as Response);

      await expect(searchArticles('Test')).rejects.toThrow(
        'Nie udało się pobrać artykułów z arXiv.'
      );
    });
  });

  describe('runGroundedAnalysis', () => {
    it('returns grounded analysis payload on success', async () => {
      const mockResult = {
        arxiv_ids: ['1234.5678'],
        total_attempts: 1,
        is_valid: true,
        analysis_markdown: '# Summary',
        audit_trail: ['Step 1'],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      } as unknown as Response);

      const result = await runGroundedAnalysis({
        arxiv_ids: ['1234.5678'],
        user_instruction: 'Focus on methods',
        mode: 'fast',
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/run-grounded-analysis'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            arxiv_ids: ['1234.5678'],
            user_instruction: 'Focus on methods',
            mode: 'fast',
          }),
        })
      );
      expect(result).toEqual(mockResult);
    });

    it('handles errorData.detail on failure', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Detail error message' }),
      } as unknown as Response);

      await expect(
        runGroundedAnalysis({ arxiv_ids: ['invalid'] })
      ).rejects.toThrow('Detail error message');
    });

    it('handles fallback message property on failure', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Validation failed' }),
      } as unknown as Response);

      await expect(
        runGroundedAnalysis({ arxiv_ids: ['invalid'] })
      ).rejects.toThrow('Validation failed');
    });

    it('handles generic status text error on unparseable failure', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        json: async () => {
          throw new Error('JSON error');
        },
      } as unknown as Response);

      await expect(
        runGroundedAnalysis({ arxiv_ids: ['invalid'] })
      ).rejects.toThrow('Błąd API (502): Bad Gateway');
    });
  });

  describe('SSE Handlers and Helpers', () => {
    it('analyzeArticlesStream triggers fetchEventSource with mapped article payloads', async () => {
      const callbacks: StreamCallbacks = {};
      const mockArticles = [
        {
          arxiv_id: '1234.5678',
          title: 'Article 1',
          authors: ['Author'],
          published: '2024-01-01',
          summary: 'Summary',
          pdf_url: 'https://arxiv.org/pdf/1234.5678.pdf',
        },
      ];

      await analyzeArticlesStream(mockArticles, 'Instruction', callbacks);

      expect(fetchEventSource).toHaveBeenCalledWith(
        expect.stringContaining('/analyze-stream'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            articles: [
              {
                title: 'Article 1',
                arxiv_id: '1234.5678',
                pdf_url: 'https://arxiv.org/pdf/1234.5678.pdf',
              },
            ],
            user_instruction: 'Instruction',
            model: 'gemini-3.1-flash-lite',
          }),
        })
      );
    });

    it('translateReportStream respects custom target language or falls back to Polish', async () => {
      const callbacks: StreamCallbacks = {};
      await translateReportStream({ text: 'Hello', target_language: 'German' }, callbacks);

      expect(fetchEventSource).toHaveBeenCalledWith(
        expect.stringContaining('/translate-stream'),
        expect.objectContaining({
          body: JSON.stringify({
            target_language: 'German',
            text: 'Hello',
          }),
        })
      );
    });

    it('runGroundedAnalysisStream sends payload to correct endpoint', async () => {
      const callbacks: StreamCallbacks = {};
      await runGroundedAnalysisStream({ arxiv_ids: ['123'] }, callbacks);

      expect(fetchEventSource).toHaveBeenCalledWith(
        expect.stringContaining('/run-grounded-analysis-stream'),
        expect.objectContaining({
          body: JSON.stringify({ arxiv_ids: ['123'] }),
        })
      );
    });

    it('processes onopen callback correctly for valid and invalid responses', async () => {
      let capturedOnOpen: any;
      vi.mocked(fetchEventSource).mockImplementation(async (_url, options) => {
        capturedOnOpen = options.onopen;
      });

      await analyzeArticlesStream([], '', {});

      // Valid SSE stream response
      await expect(
        capturedOnOpen({
          ok: true,
          headers: { get: (k: string) => (k === 'content-type' ? 'text/event-stream' : null) },
        })
      ).resolves.toBeUndefined();

      // Invalid Content-Type or non-ok response with custom text
      await expect(
        capturedOnOpen({
          ok: false,
          status: 500,
          headers: { get: () => 'application/json' },
          text: async () => 'Server error',
        })
      ).rejects.toThrow('Server error');

      // Invalid response with fallback text when text() fails
      await expect(
        capturedOnOpen({
          ok: false,
          status: 404,
          headers: { get: () => null },
          text: async () => {
            throw new Error();
          },
        })
      ).rejects.toThrow('Błąd połączenia z serwerem (404)');
    });

    it('dispatches all SSE event types and all branch fallbacks via onmessage', async () => {
      const onStatus = vi.fn();
      const onToken = vi.fn();
      const onReport = vi.fn();
      const onComplete = vi.fn();
      const onError = vi.fn();

      let capturedOnMessage: any;
      vi.mocked(fetchEventSource).mockImplementation(async (_url, options) => {
        capturedOnMessage = options.onmessage;
      });

      await analyzeArticlesStream([], '', {
        onStatus,
        onToken,
        onReport,
        onComplete,
        onError,
      });

      // 1. Ignorowanie pustych wiadomości
      capturedOnMessage({ data: '' });

      // 2. Status event - z pełnymi danymi
      capturedOnMessage({
        event: 'status',
        data: JSON.stringify({ message: 'Downloading', step: 'downloading', reset_stream: true }),
      });
      expect(onStatus).toHaveBeenCalledWith({
        step: 'downloading',
        message: 'Downloading',
        progress: undefined,
        resetStream: true,
      });

      // 3. Status event - fallback dla braku step i reset_stream
      capturedOnMessage({
        event: 'status',
        data: JSON.stringify({ message: 'Default step' }),
      });
      expect(onStatus).toHaveBeenCalledWith({
        step: 'downloading',
        message: 'Default step',
        progress: undefined,
        resetStream: false,
      });

      // 4. Token event - raw string
      capturedOnMessage({
        event: 'token',
        data: JSON.stringify('raw string token'),
      });
      expect(onToken).toHaveBeenCalledWith('raw string token', false);

      // 5. Token event - obiekt z resetStream w camelCase
      capturedOnMessage({
        event: 'token',
        data: JSON.stringify({ token: 'Token text', resetStream: true }),
      });
      expect(onToken).toHaveBeenCalledWith('Token text', true);

      // 6. Token event - fallback na pole content
      capturedOnMessage({
        event: 'token',
        data: JSON.stringify({ content: 'Content text' }),
      });
      expect(onToken).toHaveBeenCalledWith('Content text', false);

      // 7. Token event - pusty token (nie powinien wywołać onToken bez resetStream)
      const tokenCallsBefore = onToken.mock.calls.length;
      capturedOnMessage({
        event: 'token',
        data: JSON.stringify({}),
      });
      expect(onToken.mock.calls.length).toBe(tokenCallsBefore);

      // 8. Report event - pełne dane
      capturedOnMessage({
        event: 'report',
        data: JSON.stringify({
          analysis_markdown: '# Report',
          is_valid: true,
          audit_trail: ['audit 1'],
          arxiv_ids: ['123'],
        }),
      });
      expect(onReport).toHaveBeenCalledWith({
        analysis_markdown: '# Report',
        is_valid: true,
        audit_trail: ['audit 1'],
        arxiv_ids: ['123'],
      });

      // 9. Report event - fallbacki na content i puste tablice
      capturedOnMessage({
        event: 'report',
        data: JSON.stringify({
          content: '# Fallback Content',
        }),
      });
      expect(onReport).toHaveBeenCalledWith({
        analysis_markdown: '# Fallback Content',
        is_valid: false,
        audit_trail: [],
        arxiv_ids: [],
      });

      // 10. Complete event
      capturedOnMessage({ event: 'complete', data: JSON.stringify({}) });
      expect(onComplete).toHaveBeenCalled();

      // 11. Error event - z detail zamiast message
      capturedOnMessage({
        event: 'error',
        data: JSON.stringify({ detail: 'Error detail message' }),
      });
      expect(onError).toHaveBeenCalledWith('Error detail message');

      // 12. Error event - fallback na domyślny string
      capturedOnMessage({
        event: 'error',
        data: JSON.stringify({}),
      });
      expect(onError).toHaveBeenCalledWith('Wystąpił błąd podczas przetwarzania.');

      // 13. Błąd parsowania JSON
      capturedOnMessage({ event: 'token', data: 'invalid json {' });
      expect(console.error).toHaveBeenCalled();
    });

    it('handles onerror and exceptions with message fallbacks', async () => {
      const onError = vi.fn();
      let capturedOnError: any;

      vi.mocked(fetchEventSource).mockImplementation(async (_url, options) => {
        capturedOnError = options.onerror;
      });

      await analyzeArticlesStream([], '', { onError });

      // onerror bez pola message
      expect(() => capturedOnError({})).toThrow();
      expect(onError).toHaveBeenCalledWith('Utracono połączenie z serwerem.');

      // Wyjątek bez pola message
      vi.mocked(fetchEventSource).mockRejectedValueOnce({});
      await analyzeArticlesStream([], '', { onError });
      expect(onError).toHaveBeenCalledWith('Wystąpił błąd połączenia.');
    });
  });
});