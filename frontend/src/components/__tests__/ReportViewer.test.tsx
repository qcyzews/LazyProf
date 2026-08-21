import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ReportViewer } from '../ReportViewer';
import { ArticleMetadata } from '@/types';

const mockArticles: ArticleMetadata[] = [
  {
    arxiv_id: '2401.00001',
    title: 'Test Article 1',
    authors: ['Author 1'],
    published: '2024-01-01',
    summary: 'Summary 1',
    pdf_url: 'https://arxiv.org/pdf/2401.00001.pdf',
  },
];

describe('ReportViewer Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.URL.createObjectURL = vi.fn(() => 'blob:http://localhost/mock-url');
    global.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('displays empty placeholder when markdownText is empty and not streaming', () => {
    render(<ReportViewer markdownText="" isStreaming={false} />);
    expect(screen.getByText('No report generated yet')).toBeInTheDocument();
  });

  it('renders streaming indicator when isStreaming is true', () => {
    const { container } = render(<ReportViewer markdownText="# Stream Test" isStreaming={true} />);
    const pulseBar = container.querySelector('.animate-pulse');
    expect(pulseBar).toBeInTheDocument();
  });

  it('renders complex markdown elements correctly (headings, list, table, blockquote, link)', () => {
    const markdown = `
## Heading 2
### Heading 3
* Bullet item

| Col1 | Col2 |
| --- | --- |
| Val1 | Val2 |

> Important note blockquote

[arXiv Link](https://arxiv.org/abs/2401.00001)
`;
    render(<ReportViewer markdownText={markdown} isStreaming={false} />);

    expect(screen.getByRole('heading', { level: 2, name: 'Heading 2' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Heading 3' })).toBeInTheDocument();
    expect(screen.getByText('Bullet item')).toBeInTheDocument();
    expect(screen.getByText('Col1')).toBeInTheDocument();
    expect(screen.getByText('Val1')).toBeInTheDocument();
    expect(screen.getByText('Important note blockquote')).toBeInTheDocument();

    const link = screen.getByRole('link', { name: 'arXiv Link' });
    expect(link).toHaveAttribute('href', 'https://arxiv.org/abs/2401.00001');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('renders metadata bar with execution mode and selected articles', () => {
    render(
      <ReportViewer
        markdownText="# Report"
        isStreaming={false}
        analysisMode="fast"
        selectedArticles={mockArticles}
      />
    );

    expect(screen.getByText('Execution Mode:')).toBeInTheDocument();
    expect(screen.getByText('fast')).toBeInTheDocument();
    expect(screen.getByText('Grounded Papers (1):')).toBeInTheDocument();
    expect(screen.getByText('[2401.00001]')).toBeInTheDocument();
    expect(screen.getByText('Test Article 1')).toBeInTheDocument();
  });

  it('handles translation button states and action', async () => {
    const user = userEvent.setup();
    const handleTranslate = vi.fn();

    const { rerender } = render(
      <ReportViewer
        markdownText="# Report"
        isStreaming={false}
        onTranslate={handleTranslate}
        isTranslating={false}
      />
    );

    const translateBtn = screen.getByRole('button', { name: /translate to polish/i });
    await user.click(translateBtn);
    expect(handleTranslate).toHaveBeenCalledTimes(1);

    rerender(
      <ReportViewer
        markdownText="# Report"
        isStreaming={false}
        onTranslate={handleTranslate}
        isTranslating={true}
      />
    );
    expect(screen.getByRole('button', { name: /translating\.\.\./i })).toBeDisabled();
  });

  it('copies markdown text to clipboard and resets state after timeout', () => {
    vi.useFakeTimers();
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);

    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextSpy },
      writable: true,
      configurable: true,
    });

    const markdown = '# Sample Report Content';
    render(<ReportViewer markdownText={markdown} isStreaming={false} />);

    const copyBtn = screen.getByRole('button', { name: /copy/i });
    
    // Użycie synchronicznego fireEvent bez konfliktu z Fake Timers
    fireEvent.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith(markdown);

    // Przewinięcie czasu, aby sprawdzić powrót ikony
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
  });

  it('downloads markdown file on Export .MD click', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(<ReportViewer markdownText="# MD Export Test" isStreaming={false} />);

    const exportMdBtn = screen.getByRole('button', { name: /export \.md/i });
    fireEvent.click(exportMdBtn);

    expect(global.URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
  });

  it('downloads PDF file when PDF export succeeds', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['fake pdf content'], { type: 'application/pdf' }),
    } as Response);

    render(<ReportViewer markdownText="# PDF Export Test" isStreaming={false} />);

    const exportPdfBtn = screen.getByRole('button', { name: /export pdf/i });
    fireEvent.click(exportPdfBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/export-pdf'),
        expect.objectContaining({ method: 'POST' })
      );
      expect(clickSpy).toHaveBeenCalled();
    });
  });

  it('triggers alert when PDF export fails', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    render(<ReportViewer markdownText="# PDF Fail Test" isStreaming={false} />);

    const exportPdfBtn = screen.getByRole('button', { name: /export pdf/i });
    fireEvent.click(exportPdfBtn);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        expect.stringContaining('Failed to generate PDF')
      );
    });
  });
});