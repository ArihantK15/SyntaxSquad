import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnalyticsPage } from './AnalyticsPage';
import { api } from '../services/api';

vi.mock('../services/api', () => ({
  api: {
    getDashboardStats: vi.fn(),
  },
}));

describe('AnalyticsPage', () => {
  beforeEach(() => {
    vi.mocked(api.getDashboardStats).mockReset();
  });

  it('shows a retryable error state instead of an eternal spinner when the initial stats fetch fails', async () => {
    vi.mocked(api.getDashboardStats).mockRejectedValue(new Error('Failed to fetch dashboard statistics'));

    render(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText(/failed to fetch dashboard statistics/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/loading analytics engine/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('retry button re-fetches and renders analytics on success', async () => {
    vi.mocked(api.getDashboardStats)
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({
        documents_screened: 10,
        high_risk_cases: 0,
        critical_cases: 0,
        cases_requiring_review: 0,
        cleared_cases: 10,
        avg_processing_time_ms: 2000,
        risk_distribution: { LOW: 10, MEDIUM: 0, HIGH: 0, CRITICAL: 0 },
        latency_breakdown: [{ module: 'OCR', time_ms: 100, sample_count: 10 }],
        document_types: { Passport: 10 },
        top_risk_reasons: [],
        recent_cases: [],
      });

    render(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByText('2.00s')).toBeInTheDocument();
    });
    expect(screen.queryByText(/network error/i)).not.toBeInTheDocument();
    expect(api.getDashboardStats).toHaveBeenCalledTimes(2);
  });
});
