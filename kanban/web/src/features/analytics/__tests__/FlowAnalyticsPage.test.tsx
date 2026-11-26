import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FlowAnalyticsPage } from '../FlowAnalyticsPage';
import { CfdAreaChart } from '../charts/CfdAreaChart';
import { CycleTimeScatterChart } from '../charts/CycleTimeScatterChart';
import { AgingWipChart } from '../charts/AgingWipChart';
import { MonteCarloForecastCard } from '../charts/MonteCarloForecastCard';
import { CycleBurndownChart } from '../charts/CycleBurndownChart';
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

  it('covers chart edge cases, loading/empty states, mode toggles, and fallback branches', () => {
    // 1. CfdAreaChart loading, empty, and single-point states
    const { rerender } = render(<CfdAreaChart points={[]} isLoading={true} />);
    expect(screen.getByTestId('cfd-loading')).toBeDefined();

    rerender(<CfdAreaChart points={[]} isLoading={false} />);
    expect(screen.getByTestId('cfd-empty')).toBeDefined();

    rerender(
      <CfdAreaChart
        points={[
          { date: '2026-11-01', backlog: 2, unstarted: 1, started: 1, completed: 1, cancelled: 0, total: 5 },
        ]}
      />
    );
    expect(screen.getByTestId('cfd-area-chart-card')).toBeDefined();

    // 2. CycleTimeScatterChart loading, empty, single-point, p85 threshold colors, and cycle/lead mode toggle
    const pct = { p50: 2.0, p85: 3.0, p95: 5.0 };
    rerender(
      <CycleTimeScatterChart
        points={[]}
        cycleTimePercentiles={pct}
        leadTimePercentiles={pct}
        totalCompleted={0}
        isLoading={true}
      />
    );
    expect(screen.getByTestId('cycletime-loading')).toBeDefined();

    rerender(
      <CycleTimeScatterChart
        points={[]}
        cycleTimePercentiles={pct}
        leadTimePercentiles={pct}
        totalCompleted={0}
        isLoading={false}
      />
    );
    expect(screen.getByTestId('cycletime-empty')).toBeDefined();

    rerender(
      <CycleTimeScatterChart
        points={[
          {
            issue_id: 'i-single',
            issue_key: 'KAN-10',
            title: 'Single Point',
            cycle_time_days: 4.5,
            lead_time_days: 1.5,
            completed_at: '2026-11-02T10:00:00Z',
          },
        ]}
        cycleTimePercentiles={pct}
        leadTimePercentiles={pct}
        totalCompleted={1}
      />
    );
    const modeBtn = screen.getByTestId('mode-toggle-btn');
    fireEvent.click(modeBtn);
    expect(modeBtn.textContent).toContain('Switch to Cycle Time');
    fireEvent.click(modeBtn);
    expect(modeBtn.textContent).toContain('Switch to Lead Time');

    // 3. AgingWipChart loading, empty, unmapped column, normal (<p85) item, and zero thresholds
    rerender(
      <AgingWipChart activeIssues={[]} columnThresholds={{}} totalActiveWip={0} isLoading={true} />
    );
    expect(screen.getByTestId('aging-wip-loading')).toBeDefined();

    rerender(
      <AgingWipChart activeIssues={[]} columnThresholds={{}} totalActiveWip={0} isLoading={false} />
    );
    expect(screen.getByTestId('aging-wip-empty')).toBeDefined();

    rerender(
      <AgingWipChart
        activeIssues={[
          {
            issue_id: 'i-norm',
            issue_key: 'KAN-11',
            title: 'Normal WIP',
            state_id: 's2',
            state_name: 'In Progress',
            state_color_hex: '#3b82f6',
            state_entered_at: '2026-11-20T10:00:00Z',
            first_started_at: '2026-11-20T10:00:00Z',
            age_in_current_state_hours: 10.0,
            total_wip_hours: 10.0,
          },
          {
            issue_id: 'i-unmapped',
            issue_key: 'KAN-12',
            title: 'Unmapped State',
            state_id: 's-missing',
            state_name: 'Missing',
            state_color_hex: '#94a3b8',
            state_entered_at: '2026-11-20T10:00:00Z',
            first_started_at: '2026-11-20T10:00:00Z',
            age_in_current_state_hours: 5.0,
            total_wip_hours: 5.0,
          },
        ]}
        columnThresholds={{
          s2: {
            state_id: 's2',
            state_name: 'In Progress',
            p50_hours: 20.0,
            p85_hours: 40.0,
            p95_hours: 60.0,
          },
          sZero: {
            state_id: 'sZero',
            state_name: 'Zero Col',
            p50_hours: 0,
            p85_hours: 0,
            p95_hours: 0,
          },
        }}
        totalActiveWip={2}
      />
    );
    fireEvent.click(screen.getByTestId('aging-wip-table-toggle'));
    expect(screen.getAllByText('Normal').length).toBeGreaterThan(0);

    // 4. MonteCarloForecastCard null forecast, null days/dates, and TBD date fallbacks
    rerender(<MonteCarloForecastCard forecast={null} />);
    expect(screen.getByText(/No throughput history available/)).toBeDefined();

    rerender(
      <MonteCarloForecastCard
        forecast={{
          trials: 1000,
          historical_daily_throughput: [0],
          average_daily_throughput: 0,
          how_many: { horizon_days: 14, p50: 0, p85: 0, p95: 0, distribution: {} },
          when: {
            target_items: 10,
            p50_days: null,
            p50_date: null,
            p85_days: null,
            p85_date: null,
            p95_days: null,
            p95_date: null,
            distribution: {},
          },
        }}
      />
    );
    fireEvent.click(screen.getByTestId('monte-carlo-table-toggle'));
    expect(screen.getByTestId('mc-when-p50').textContent).toBe('N/A');

    rerender(
      <MonteCarloForecastCard
        forecast={{
          trials: 1000,
          historical_daily_throughput: [1],
          average_daily_throughput: 1,
          how_many: { horizon_days: 14, p50: 14, p85: 10, p95: 8, distribution: {} },
          when: {
            target_items: 10,
            p50_days: 10,
            p50_date: null,
            p85_days: 14,
            p85_date: null,
            p95_days: 18,
            p95_date: null,
            distribution: {},
          },
        }}
      />
    );
    expect(screen.getByTestId('mc-when-p50').textContent).toContain('TBD');

    // 5. CycleBurndownChart empty, single point without ideal, and >10 points decimation
    rerender(<CycleBurndownChart burndown={null} />);
    expect(screen.getByText(/No burndown data recorded/)).toBeDefined();

    rerender(
      <CycleBurndownChart
        burndown={{
          cycle_id: 'c1',
          series: [{ date: '2026-11-01', scope: 5, remaining: 5 }],
          ideal: [],
        }}
      />
    );
    fireEvent.click(screen.getByTestId('burndown-table-toggle'));
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0);

    const manySeries = Array.from({ length: 12 }, (_, idx) => ({
      date: `2026-11-${String(idx + 1).padStart(2, '0')}`,
      scope: 12,
      remaining: Math.max(0, 12 - idx),
    }));
    rerender(
      <CycleBurndownChart
        burndown={{
          cycle_id: 'c1',
          series: manySeries,
          ideal: manySeries.map((s) => ({ date: s.date, remaining: s.remaining })),
        }}
      />
    );
    expect(screen.getByTestId('cycle-burndown-chart')).toBeDefined();
  });

  it('handles wrapped cycle items response, cycle selection change, empty numeric input fallbacks, and error retry', async () => {
    let failFirst = true;
    vi.mocked(clientModule.apiFetch).mockImplementation((_method, path) => {
      const p = typeof path === 'string' ? path : '';
      if (p.includes('/analytics/flow')) {
        if (failFirst) {
          failFirst = false;
          return Promise.reject(new Error('Temporary failure'));
        }
        return Promise.resolve(mockFlowData);
      }
      if (p.includes('/cycles') && p.includes('/burndown')) {
        return Promise.resolve(mockBurndown);
      }
      if (p.includes('/cycles')) {
        return Promise.resolve({
          items: [
            {
              id: 'c-planned',
              project_id: 'a0000000-0000-0000-0000-000000000001',
              name: 'Sprint Planned',
              status: 'upcoming',
              issue_count: 4,
              completed_count: 0,
            },
            {
              id: 'c-second',
              project_id: 'a0000000-0000-0000-0000-000000000001',
              name: 'Sprint Second',
              status: 'completed',
              issue_count: 6,
              completed_count: 6,
            },
          ],
        });
      }
      return Promise.reject(new Error(`Unhandled: ${p}`));
    });

    renderWithProviders(<FlowAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('flow-error')).toBeDefined();
    });

    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(screen.getByTestId('flow-cycle-select')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('flow-cycle-select'), { target: { value: 'c-second' } });
    fireEvent.change(screen.getByTestId('flow-horizon-input'), { target: { value: '0' } });
    fireEvent.change(screen.getByTestId('flow-target-items-input'), { target: { value: '0' } });

    await waitFor(() => {
      expect(screen.getByTestId<HTMLSelectElement>('flow-cycle-select').value).toBe('c-second');
    });
  });

  it('renders headline KPIs with Monte Carlo trial count collapsed in AdvancedSection (KAN-370)', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    // Headline KPIs are visible and render expected metrics
    await waitFor(() => {
      expect(screen.getByTestId('flow-headline-kpis')).toBeDefined();
    });

    expect(screen.getByTestId('kpi-throughput').textContent).toContain('1.4');
    expect(screen.getByTestId('kpi-throughput').textContent).toContain('issues/day');
    expect(screen.getByTestId('kpi-cycle-time').textContent).toContain('2.5d');
    expect(screen.getByTestId('kpi-cycle-time').textContent).toContain('4d');
    expect(screen.getByTestId('kpi-wip-count').textContent).toContain('1 in progress');

    // Primary CFD chart is visible outside AdvancedSection
    expect(screen.getByTestId('cfd-area-chart-card')).toBeDefined();

    // AdvancedSection is present and collapsed by default
    const advSection = screen.getByTestId('flow-advanced-stats-section');
    expect(advSection).toBeDefined();
    expect(advSection.hasAttribute('open')).toBe(false);

    // Monte Carlo forecast, trials count (10,000), and scatter/aging charts are inside AdvancedSection
    const mcCard = within(advSection).getByTestId('monte-carlo-forecast-card');
    expect(mcCard.textContent).toContain('10,000 trials');
    expect(within(advSection).getByTestId('cycle-time-scatter-card')).toBeDefined();
    expect(within(advSection).getByTestId('aging-wip-card')).toBeDefined();

    // Toggling the AdvancedSection opens and closes it
    const toggleBtn = screen.getByTestId('flow-advanced-stats-section-toggle');
    fireEvent.click(toggleBtn);
    expect(advSection.hasAttribute('open')).toBe(true);

    fireEvent.click(toggleBtn);
    expect(advSection.hasAttribute('open')).toBe(false);
  });

  it('handles missing projectKey param and empty cycles object fallback', () => {
    vi.mocked(clientModule.apiFetch).mockImplementation((_method, path) => {
      const p = typeof path === 'string' ? path : '';
      if (p.includes('/cycles')) {
        return Promise.resolve({});
      }
      return Promise.resolve(mockFlowData);
    });

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/analytics']}>
          <Routes>
            <Route path="/analytics" element={<FlowAnalyticsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText('Flow Telemetry Studio')).toBeDefined();
  });

  it('renders FieldHelpHint and default value indicators for horizon and target batch inputs (KAN-460)', async () => {
    renderWithProviders(<FlowAnalyticsPage />);

    // Invariant: NEVER nest FieldHelpHint inside <label htmlFor> (HTML 4.10.4)
    expect(document.querySelectorAll('label button.field-help-hint').length).toBe(0);

    // Invariant: FieldHelpHint triggers are sibling children of .kb-flow-label-row
    const labelRows = document.querySelectorAll('.kb-flow-label-row');
    expect(labelRows.length).toBeGreaterThanOrEqual(2);
    expect(document.querySelectorAll('.kb-flow-label-row button.field-help-hint').length).toBe(2);

    // Verify Default Value Badges
    expect(screen.getByText('(Default: 14d)')).toBeDefined();
    expect(screen.getByText('(Default: 20)')).toBeDefined();

    // Verify Horizon Help Hint
    const horizonHelpBtn = screen.getByTestId('flow-horizon-help');
    expect(horizonHelpBtn).toBeDefined();
    fireEvent.click(horizonHelpBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
      expect(screen.getByText('Forecast Horizon')).toBeDefined();
      expect(screen.getByText('14 days')).toBeDefined();
    });

    // Dismiss popover
    fireEvent.keyDown(document, { key: 'Escape' });

    // Verify Target Batch Help Hint
    const targetHelpBtn = screen.getByTestId('flow-target-items-help');
    expect(targetHelpBtn).toBeDefined();
    fireEvent.click(targetHelpBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
      expect(screen.getByText('Target Batch Size')).toBeDefined();
      expect(screen.getByText('20 items')).toBeDefined();
    });
  });

  it('renders StudioDocLink in header left and header actions (KAN-461)', () => {
    renderWithProviders(<FlowAnalyticsPage />);

    const docLink = screen.getByTestId('flow-analytics-doc-link');
    expect(docLink).toBeDefined();
    expect(docLink.getAttribute('href')).toBe('/docs/statistical-flow-telemetry-and-lean-analytics');
    expect(docLink.textContent).toContain('Flow Telemetry Guide ->');

    // Verify placement inside .kb-flow-header-left and .kb-flow-header-actions
    const headerLeft = docLink.closest('.kb-flow-header-left');
    expect(headerLeft).not.toBeNull();
    const headerActions = docLink.closest('.kb-flow-header-actions');
    expect(headerActions).not.toBeNull();
    expect(headerLeft?.querySelector('.kb-flow-title-group')).not.toBeNull();
  });
});
