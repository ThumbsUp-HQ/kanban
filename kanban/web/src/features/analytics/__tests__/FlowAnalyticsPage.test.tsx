import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FlowAnalyticsPage } from '../FlowAnalyticsPage';
import { BoardCard } from '../../board/BoardCard';
import * as clientModule from '../../../api/client';

vi.mock('../../../api/client', () => ({
  apiFetch: vi.fn(),
  apiClient: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  },
}));

const mockFlowData = {
  project_key: 'KAN',
  project_id: 'a0000000-0000-0000-0000-000000000001',
  window_days: 90,
  cfd: {
    states: [
      { id: 's1', name: 'Backlog', state_group: 'backlog', color_hex: '#94a3b8', sort_order: 1 },
      { id: 's2', name: 'In Progress', state_group: 'started', color_hex: '#3b82f6', sort_order: 2 },
      { id: 's3', name: 'Done', state_group: 'completed', color_hex: '#10b981', sort_order: 3 },
    ],
    state_groups: ['backlog', 'unstarted', 'started', 'completed', 'cancelled'],
    points: [
      { date: '2026-11-01', backlog: 5, unstarted: 0, started: 2, completed: 1, cancelled: 0, total: 8 },
      { date: '2026-11-02', backlog: 4, unstarted: 0, started: 3, completed: 2, cancelled: 0, total: 9 },
    ],
  },
  cycle_lead_time: {
    points: [
      {
        issue_id: 'i1',
        issue_key: 'KAN-1',
        title: 'Task 1',
        cycle_time_days: 2.5,
        lead_time_days: 5.0,
        completed_at: '2026-11-02T10:00:00Z',
      },
      {
        issue_id: 'i2',
        issue_key: 'KAN-2',
        title: 'Task 2',
        cycle_time_days: 4.0,
        lead_time_days: 8.0,
        completed_at: '2026-11-05T12:00:00Z',
      },
    ],
    cycle_time_percentiles: { p50: 2.5, p85: 4.0, p95: 4.0 },
    lead_time_percentiles: { p50: 5.0, p85: 8.0, p95: 8.0 },
    total_completed_in_window: 2,
  },
  aging_wip: {
    active_issues: [
      {
        issue_id: 'i3',
        issue_key: 'KAN-3',
        title: 'Active Issue 3',
        state_id: 's2',
        state_name: 'In Progress',
        state_color_hex: '#3b82f6',
        state_entered_at: '2026-11-20T10:00:00Z',
        first_started_at: '2026-11-20T10:00:00Z',
        age_in_current_state_hours: 48.0,
        total_wip_hours: 48.0,
      },
    ],
    column_thresholds: {
      s2: {
        state_id: 's2',
        state_name: 'In Progress',
        state_group: 'started',
        color_hex: '#3b82f6',
        p50_hours: 24.0,
        p85_hours: 40.0,
        p95_hours: 72.0,
        sample_size: 10,
      },
    },
    total_active_wip: 1,
  },
  monte_carlo: {
    trials: 10000,
    historical_daily_throughput: [1, 2, 0, 1, 3],
    average_daily_throughput: 1.4,
    how_many: {
      horizon_days: 14,
      p50: 18,
      p85: 12,
      p95: 9,
      distribution: { '9': 500, '12': 3500, '18': 5000 },
    },
    when: {
      target_items: 20,
      p50_days: 15,
      p50_date: '2026-12-07',
      p85_days: 22,
      p85_date: '2026-12-14',
      p95_days: 28,
      p95_date: '2026-12-20',
      distribution: { '15': 5000, '22': 3500, '28': 1500 },
    },
  },
};

const mockCycles = [
  {
    id: 'c1',
    project_id: 'a0000000-0000-0000-0000-000000000001',
    name: 'Sprint 1',
    status: 'active' as const,
    issue_count: 5,
    completed_count: 2,
  },
];

const mockBurndown = {
  cycle_id: 'c1',
  series: [
    { date: '2026-11-01', scope: 5, remaining: 5 },
    { date: '2026-11-02', scope: 5, remaining: 3 },
  ],
  ideal: [
    { date: '2026-11-01', remaining: 5.0 },
    { date: '2026-11-02', remaining: 2.5 },
  ],
};

function renderWithProviders(ui: React.ReactElement, initialPath = '/projects/KAN/analytics') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/projects/:projectKey/analytics" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('FlowAnalyticsPage & Flow Telemetry Studio (KAN-79)', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(clientModule.apiFetch).mockImplementation((_method, path) => {
      const p = typeof path === 'string' ? path : '';
      if (p.includes('/analytics/flow')) {
        return Promise.resolve(mockFlowData);
      }
      if (p.includes('/cycles') && p.includes('/burndown')) {
        return Promise.resolve(mockBurndown);
      }
      if (p.includes('/cycles')) {
        return Promise.resolve(mockCycles);
      }
      return Promise.reject(new Error(`Unhandled apiFetch path: ${p}`));
    });
  });

  it('renders the Flow Telemetry Studio layout and controls', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    expect(screen.getByText('Flow Telemetry Studio')).toBeDefined();
    expect(screen.getByTestId('flow-window-select')).toBeDefined();
    expect(screen.getByTestId('flow-horizon-input')).toBeDefined();
    expect(screen.getByTestId('flow-target-items-input')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByTestId('cfd-area-chart-card')).toBeDefined();
    });
  });

  it('renders CFD area chart and toggles accessible data table', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('cfd-area-chart-card')).toBeDefined();
    });

    const toggleBtn = screen.getByTestId('cfd-table-toggle');
    expect(screen.queryByTestId('cfd-data-table')).toBeNull();

    fireEvent.click(toggleBtn);
    const table = screen.getByTestId('cfd-data-table');
    expect(table).toBeDefined();
    expect(within(table).getByText('2026-11-01')).toBeDefined();

    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('cfd-data-table')).toBeNull();
  });

  it('renders Cycle Time and Lead Time scatterplot with percentiles and table toggle', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('cycle-time-scatter-card')).toBeDefined();
    });

    expect(screen.getByTestId('p50-badge')).toBeDefined();
    expect(screen.getByTestId('p85-badge')).toBeDefined();
    expect(screen.getByTestId('p95-badge')).toBeDefined();

    const toggleBtn = screen.getByTestId('cycletime-table-toggle');
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('cycletime-data-table')).toBeDefined();
    expect(screen.getByText('KAN-1')).toBeDefined();
  });

  it('renders Aging WIP chart with column threshold guide lines and table toggle', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('aging-wip-card')).toBeDefined();
    });

    expect(screen.getByTestId('aging-col-In Progress')).toBeDefined();

    const toggleBtn = screen.getByTestId('aging-wip-table-toggle');
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('aging-wip-data-table')).toBeDefined();
    expect(screen.getByText('KAN-3')).toBeDefined();
  });

  it('renders Monte Carlo forecast cards and confidence percentiles', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('monte-carlo-forecast-card')).toBeDefined();
    });

    expect(screen.getByTestId('mc-how-many-p50').textContent).toContain('18 items');
    expect(screen.getByTestId('mc-how-many-p85').textContent).toContain('12 items');
    expect(screen.getByTestId('mc-how-many-p95').textContent).toContain('9 items');

    expect(screen.getByTestId('mc-when-p50').textContent).toContain('15 days');
    expect(screen.getByTestId('mc-when-p85').textContent).toContain('22 days');
    expect(screen.getByTestId('mc-when-p95').textContent).toContain('28 days');

    const toggleBtn = screen.getByTestId('monte-carlo-table-toggle');
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('monte-carlo-table')).toBeDefined();
  });

  it('renders Sprint Cycle Burndown chart integrated into studio', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('cycle-burndown-chart')).toBeDefined();
    });

    expect(screen.getByTestId('burndown-badge-scope').textContent).toContain('5 items');
    expect(screen.getByTestId('burndown-badge-remaining').textContent).toContain('3 items');

    const toggleBtn = screen.getByTestId('burndown-table-toggle');
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('burndown-table')).toBeDefined();
  });

  it('updates parameters when window, horizon, or target batch controls change', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('flow-window-select')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('flow-window-select'), { target: { value: '30' } });
    fireEvent.change(screen.getByTestId('flow-horizon-input'), { target: { value: '28' } });
    fireEvent.change(screen.getByTestId('flow-target-items-input'), { target: { value: '50' } });

    await waitFor(() => {
      expect(clientModule.apiFetch).toHaveBeenCalledWith(
        'GET',
        expect.stringContaining('/analytics/flow'),
        expect.objectContaining({
          query: expect.objectContaining({
            window_days: 30,
            horizon_days: 28,
            target_items: 50,
          }) as unknown,
        })
      );
    });
  });

  it('renders error banner when apiFetch fails', async () => {
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce(new Error('Network error'));
    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('flow-error')).toBeDefined();
    });
  });

  it('renders aging WIP chip on BoardCard when active card age exceeds column p85', () => {
    const activeIssue = {
      id: 'i-wip-1',
      key: 'KAN-99',
      summary: 'Stalled implementation',
      state_id: 's2',
      board_rank: '0|hzzzzz:',
      age_in_current_state_hours: 50.0,
      column_p85_age_hours: 40.0,
    };

    const { rerender } = render(
      <BoardCard
        issue={activeIssue}
        stateGroup="started"
      />
    );

    const agingBadge = screen.getByTestId('aging-wip-KAN-99');
    expect(agingBadge).toBeDefined();
    expect(agingBadge.textContent).toContain('Aging WIP (50h)');

    // Normal issue below threshold does not display aging chip
    const freshIssue = {
      id: 'i-wip-2',
      key: 'KAN-100',
      summary: 'Fresh task',
      state_id: 's2',
      board_rank: '0|hzzzzz:',
      age_in_current_state_hours: 10.0,
      column_p85_age_hours: 40.0,
    };

    rerender(
      <BoardCard
        issue={freshIssue}
        stateGroup="started"
      />
    );

    expect(screen.queryByTestId('aging-wip-KAN-100')).toBeNull();
  });
});
