import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatusIndicator } from '../StatusIndicator';
import { StreamStatus } from '@/types';

describe('StatusIndicator Component', () => {
  it('returns null when status is null', () => {
    const { container } = render(<StatusIndicator status={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders correctly for "downloading" step', () => {
    const status: StreamStatus = {
      step: 'downloading',
      message: 'Downloading papers...',
    };

    const { container } = render(<StatusIndicator status={status} />);

    expect(screen.getByText('Fetching and processing PDF')).toBeInTheDocument();
    expect(screen.getByText('Downloading papers...')).toBeInTheDocument();
    expect(container.querySelector('.bg-indigo-600')).not.toBeInTheDocument();
  });

  it('renders correctly for "map" step with progress bar', () => {
    const status: StreamStatus = {
      step: 'map',
      message: 'Processing paper 1 of 3...',
      progress: 33,
    };

    const { container } = render(<StatusIndicator status={status} />);

    expect(screen.getByText('Gemini: Article analysis (Map)')).toBeInTheDocument();
    expect(screen.getByText('Processing paper 1 of 3...')).toBeInTheDocument();

    const progressBar = container.querySelector('[style*="width: 33%"]');
    expect(progressBar).toBeInTheDocument();
  });

  it('renders correctly for "reduce" step', () => {
    const status: StreamStatus = {
      step: 'reduce',
      message: 'Synthesizing report...',
      progress: 90,
    };

    render(<StatusIndicator status={status} />);

    expect(screen.getByText('Gemini: Synthesis and report generation')).toBeInTheDocument();
    expect(screen.getByText('Synthesizing report...')).toBeInTheDocument();
  });

  it('renders correctly for "translating" step', () => {
    const status: StreamStatus = {
      step: 'translating',
      message: 'Translating into Polish...',
      progress: 50,
    };

    render(<StatusIndicator status={status} />);

    expect(screen.getByText('Report translation')).toBeInTheDocument();
    expect(screen.getByText('Translating into Polish...')).toBeInTheDocument();
  });

  it('renders fallback for unknown/default step', () => {
    const status = {
      step: 'unknown_step' as unknown as StreamStatus['step'],
      message: 'Working...',
    };

    render(<StatusIndicator status={status} />);

    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByText('Working...')).toBeInTheDocument();
  });

  it('clamps progress bar between 0% and 100%', () => {
    const { container: containerLow } = render(
      <StatusIndicator status={{ step: 'map', message: 'Low', progress: -10 }} />
    );
    expect(containerLow.querySelector('[style*="width: 0%"]')).toBeInTheDocument();

    const { container: containerHigh } = render(
      <StatusIndicator status={{ step: 'map', message: 'High', progress: 150 }} />
    );
    expect(containerHigh.querySelector('[style*="width: 100%"]')).toBeInTheDocument();
  });
});