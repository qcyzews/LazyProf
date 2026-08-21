import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ArticleCard } from '../ArticleCard';
import { ArticleMetadata } from '@/types';

const mockArticle: ArticleMetadata = {
  arxiv_id: '2401.12345',
  title: 'Advancements in Grounded RAG',
  authors: ['Jan Kowalski', 'Anna Nowak'],
  published: '2024-01-15',
  summary: 'This is a test summary for the paper.',
  pdf_url: 'https://arxiv.org/pdf/2401.12345.pdf',
};

describe('ArticleCard Component', () => {
  it('renders article details correctly', () => {
    render(
      <ArticleCard
        article={mockArticle}
        isSelected={false}
        onToggleSelect={vi.fn()}
      />
    );

    expect(screen.getByText('Advancements in Grounded RAG')).toBeInTheDocument();
    expect(screen.getByText('arXiv:2401.12345')).toBeInTheDocument();
    expect(screen.getByText(/Jan Kowalski, Anna Nowak/)).toBeInTheDocument();
    expect(screen.getByText('This is a test summary for the paper.')).toBeInTheDocument();
    
    const link = screen.getByRole('link', { name: /view arxiv pdf/i });
    expect(link).toHaveAttribute('href', mockArticle.pdf_url);
  });

  it('triggers onToggleSelect when action button is clicked', async () => {
    const user = userEvent.setup();
    const handleToggle = vi.fn();

    const { rerender } = render(
      <ArticleCard
        article={mockArticle}
        isSelected={false}
        onToggleSelect={handleToggle}
      />
    );

    const addButton = screen.getByRole('button', { name: /add to analysis/i });
    await user.click(addButton);

    expect(handleToggle).toHaveBeenCalledTimes(1);
    expect(handleToggle).toHaveBeenCalledWith(mockArticle);

    // Po zaznaczeniu tekst przycisku powinien się zmienić
    rerender(
      <ArticleCard
        article={mockArticle}
        isSelected={true}
        onToggleSelect={handleToggle}
      />
    );
    expect(screen.getByRole('button', { name: /selected/i })).toBeInTheDocument();
  });
});
