// /frontend/src/app/__tests__/page.test.tsx
import { vi, describe, it, expect, beforeEach, type Mock } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import Home from '@/app/page';
import * as api from '@/lib/api';
import { ArticleMetadata } from '@/types';

vi.mock('@/lib/api', () => ({
  searchArticles: vi.fn(),
  runGroundedAnalysisStream: vi.fn(),
  translateReportStream: vi.fn(),
}));

vi.mock('@/components/ArticleCard', () => ({
  ArticleCard: ({ article, isSelected, onToggleSelect }: any) => (
    <div data-testid={`article-card-${article.arxiv_id}`}>
      <span>{article.title}</span>
      <button onClick={() => onToggleSelect(article)}>
        {isSelected ? 'Deselect' : 'Select'}
      </button>
    </div>
  ),
}));

vi.mock('@/components/StatusIndicator', () => ({
  StatusIndicator: ({ status }: any) =>
    status ? <div data-testid="status-indicator">{status.message}</div> : null,
}));

vi.mock('@/components/ReportViewer', () => ({
  ReportViewer: ({ markdownText, isStreaming, onTranslate, isTranslating }: any) => (
    <div data-testid="report-viewer">
      <div data-testid="markdown-content">{markdownText}</div>
      <button onClick={onTranslate} disabled={isStreaming || isTranslating}>
        Translate
      </button>
    </div>
  ),
}));

describe('Home Page (page.tsx) - Full Branch Coverage', () => {
  const mockArticles: ArticleMetadata[] = [
    {
      arxiv_id: '2301.00001',
      title: 'Retrieval Augmented Generation Overview',
      authors: ['John Doe'],
      summary: 'Summary 1',
      published: '2023-01-01',
      pdf_url: 'https://arxiv.org/abs/2301.00001',
    },
    {
      arxiv_id: '2301.00002',
      title: 'Advanced RAG Pipelines',
      authors: ['Jane Smith'],
      summary: 'Summary 2',
      published: '2023-01-02',
      pdf_url: 'https://arxiv.org/abs/2301.00002',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    window.alert = vi.fn();
  });

  it('renders initial view and handles empty search submission', () => {
    render(<Home />);
    expect(screen.getByText('LazyProf AI')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText('Enter keywords...');
    fireEvent.change(searchInput, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    expect(api.searchArticles).not.toHaveBeenCalled();
  });

  it('handles search responses without articles or expanded_query', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce(null);

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    await waitFor(() => {
      expect(screen.getByText('No articles found. Try adjusting your search query.')).toBeInTheDocument();
      expect(screen.queryByText('Expanded Query / Keywords:')).not.toBeInTheDocument();
    });
  });

  it('handles search error fallbacks when err.message is undefined', async () => {
    (api.searchArticles as Mock).mockRejectedValueOnce({});

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    await waitFor(() => {
      expect(screen.getByText('Failed to search articles.')).toBeInTheDocument();
    });
  });

  it('handles selecting, deselecting and clearing paper list', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce({
      articles: mockArticles,
      expanded_query: 'RAG',
    });

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    await waitFor(() => {
      expect(screen.getByText('Retrieval Augmented Generation Overview')).toBeInTheDocument();
    });

    const selectButtons = screen.getAllByRole('button', { name: 'Select' });
    fireEvent.click(selectButtons[0]);
    fireEvent.click(selectButtons[1]);
    expect(screen.getByText('Selected Papers (2)')).toBeInTheDocument();

    const deselectButtons = screen.getAllByRole('button', { name: 'Deselect' });
    fireEvent.click(deselectButtons[0]);
    expect(screen.getByText('Selected Papers (1)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByText('No papers selected yet.')).toBeInTheDocument();
  });

  it('navigates between tabs and blocks report configuration when no papers selected', () => {
    render(<Home />);

    fireEvent.click(screen.getByRole('button', { name: /2\. Synthesis Report/i }));
    expect(screen.getByText('No papers selected for analysis')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Back to Search/i }));
    expect(screen.getByText('No articles found. Try adjusting your search query.')).toBeInTheDocument();
  });

  it('covers mode switching (Fast, Medium, High) and custom prompt changes', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce({ articles: mockArticles });

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await waitFor(() => fireEvent.click(screen.getAllByRole('button', { name: 'Select' })[0]));
    fireEvent.click(screen.getByRole('button', { name: /Configure & Generate Report/i }));

    // Przełączanie wszystkich trybów
    fireEvent.click(screen.getByRole('button', { name: /Fast Mode/i }));
    fireEvent.click(screen.getByRole('button', { name: /High Depth Mode/i }));
    fireEvent.click(screen.getByRole('button', { name: /Medium Mode/i }));

    const textarea = screen.getByDisplayValue(/Compare the RAG architectures/i);
    fireEvent.change(textarea, { target: { value: 'New Custom Instruction' } });
    expect(textarea).toHaveValue('New Custom Instruction');
  });

  it('covers full analysis stream lifecycle and partial report callbacks', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce({ articles: mockArticles });

    let streamCallbacks: any;
    (api.runGroundedAnalysisStream as Mock).mockImplementation((_payload, callbacks) => {
      streamCallbacks = callbacks;
      return Promise.resolve();
    });

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await waitFor(() => fireEvent.click(screen.getAllByRole('button', { name: 'Select' })[0]));
    fireEvent.click(screen.getByRole('button', { name: /Configure & Generate Report/i }));

    fireEvent.click(screen.getByRole('button', { name: /Generate Report/i }));

    // Tokeny (resetStream: false i true)
    act(() => {
      streamCallbacks.onStatus({ step: 'analyzing', message: 'Analyzing papers...' });
      streamCallbacks.onToken('Initial chunk', false);
      streamCallbacks.onToken(' + More chunk', false);
    });
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Initial chunk + More chunk');

    // Raport cząstkowy (bez audit_trail i is_valid)
    act(() => {
      streamCallbacks.onReport({ analysis_markdown: 'Markdown only' });
    });
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Markdown only');

    // Pełny raport
    act(() => {
      streamCallbacks.onReport({
        analysis_markdown: 'Final Report text',
        audit_trail: [{ step: 'validation', passed: true }],
        is_valid: true,
      });
      streamCallbacks.onComplete();
    });

    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Final Report text');
    expect(screen.queryByTestId('status-indicator')).not.toBeInTheDocument();
  });

  it('covers analysis error handling including fallback error string and AbortError', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce({ articles: mockArticles });

    let streamCallbacks: any;
    (api.runGroundedAnalysisStream as Mock).mockImplementation((_payload, callbacks) => {
      streamCallbacks = callbacks;
      return Promise.resolve();
    });

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await waitFor(() => fireEvent.click(screen.getAllByRole('button', { name: 'Select' })[0]));
    fireEvent.click(screen.getByRole('button', { name: /Configure & Generate Report/i }));

    fireEvent.click(screen.getByRole('button', { name: /Generate Report/i }));

    // onError callback
    act(() => {
      streamCallbacks.onError('Explicit stream error');
    });
    expect(screen.getByText('Explicit stream error')).toBeInTheDocument();

    // Exception w try/catch bez .message
    (api.runGroundedAnalysisStream as Mock).mockRejectedValueOnce({});
    fireEvent.click(screen.getByRole('button', { name: /Generate Report/i }));
    await waitFor(() => {
      expect(screen.getByText('An error occurred during analysis.')).toBeInTheDocument();
    });

    // AbortError
    const abortErr = new Error('Aborted');
    abortErr.name = 'AbortError';
    (api.runGroundedAnalysisStream as Mock).mockRejectedValueOnce(abortErr);
    fireEvent.click(screen.getByRole('button', { name: /Generate Report/i }));
    await waitFor(() => {
      expect(screen.queryByText('Aborted')).not.toBeInTheDocument();
    });
  });

  it('covers full translation lifecycle, status reset, token appends and error branches', async () => {
    (api.searchArticles as Mock).mockResolvedValueOnce({ articles: mockArticles });

    let analysisCallbacks: any;
    (api.runGroundedAnalysisStream as Mock).mockImplementation((_payload, callbacks) => {
      analysisCallbacks = callbacks;
      return Promise.resolve();
    });

    let translateCallbacks: any;
    (api.translateReportStream as Mock).mockImplementation((_payload, callbacks) => {
      translateCallbacks = callbacks;
      return Promise.resolve();
    });

    render(<Home />);
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await waitFor(() => fireEvent.click(screen.getAllByRole('button', { name: 'Select' })[0]));
    fireEvent.click(screen.getByRole('button', { name: /Configure & Generate Report/i }));

    // Brak tekstu raportu
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));
    expect(api.translateReportStream).not.toHaveBeenCalled();

    // Generujemy raport bazowy
    fireEvent.click(screen.getByRole('button', { name: /Generate Report/i }));
    act(() => {
      analysisCallbacks.onReport({ analysis_markdown: 'English Source' });
      analysisCallbacks.onComplete();
    });

    // Start tłumaczenia
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));

    // onStatus bez flagi resetStream
    act(() => {
      translateCallbacks.onStatus({ step: 'translating', message: 'Working...' });
    });
    expect(screen.getByTestId('status-indicator')).toHaveTextContent('Working...');

    // onStatus z resetStream
    act(() => {
      translateCallbacks.onStatus({ step: 'translating', message: 'Resetting...', resetStream: true });
    });
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('');

    // onToken z resetStream: false
    act(() => {
      translateCallbacks.onToken('Polski ', false);
      translateCallbacks.onToken('tekst', false);
    });
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Polski tekst');

    // onReport bez pól opcjonalnych
    act(() => {
      translateCallbacks.onReport({});
    });

    // onReport z polami
    act(() => {
      translateCallbacks.onReport({
        analysis_markdown: 'Gotowy polski raport',
        audit_trail: [{ step: 'polish' }],
        is_valid: true,
      });
      translateCallbacks.onComplete();
    });
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Gotowy polski raport');

    // onError callback
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));
    act(() => {
      translateCallbacks.onError('Translation API error');
    });
    expect(screen.getByText('Translation API error')).toBeInTheDocument();

    // Exception try/catch bez .message
    (api.translateReportStream as Mock).mockRejectedValueOnce({});
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));
    await waitFor(() => {
      expect(screen.getByText('An error occurred during translation.')).toBeInTheDocument();
    });

    // AbortError w tłumaczeniu
    const abortErr = new Error('Abort Translation');
    abortErr.name = 'AbortError';
    (api.translateReportStream as Mock).mockRejectedValueOnce(abortErr);
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));
    await waitFor(() => {
      expect(screen.queryByText('Abort Translation')).not.toBeInTheDocument();
    });
  });
  it('covers remaining edge cases: alerts with zero papers and badge counter rendering', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    (api.searchArticles as Mock).mockResolvedValueOnce({
      articles: mockArticles,
      expanded_query: null,
    });

    render(<Home />);

    // 1. Wyszukanie i zaznaczenie artykułu
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Select' })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Select' })[0]);

    // Badging i lista w panelu bocznym (obsługa wielu wystąpień tekstu)
    expect(screen.getByRole('button', { name: /1\.\s*Search Papers\s*1/i })).toBeInTheDocument();
    expect(screen.getAllByText('Retrieval Augmented Generation Overview')).toHaveLength(2);

    // 2. Wyczyszczenie zaznaczeń
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));

    // 3. Wymuszenie wywołania onClick przycisku mimo zablokowanego stanu
    const configBtn = screen.getByRole('button', { name: /Configure & Generate Report/i });
    
    // Pobranie wewnętrznego handlera Reacta ze struktury DOM obiektu (__reactProps$...)
    const reactPropsKey = Object.keys(configBtn).find((key) => key.startsWith('__reactProps$'));
    if (reactPropsKey && (configBtn as any)[reactPropsKey]?.onClick) {
      (configBtn as any)[reactPropsKey].onClick({ preventDefault: () => {}, stopPropagation: () => {} });
    } else {
      fireEvent.click(configBtn);
    }

    expect(alertSpy).toHaveBeenCalledWith('Please select at least one paper first.');

    // 4. Przejście do widoku pustego raportu
    fireEvent.click(screen.getByRole('button', { name: /2\. Synthesis Report/i }));
    expect(screen.getByText('No papers selected for analysis')).toBeInTheDocument();

    alertSpy.mockRestore();
  });
});

