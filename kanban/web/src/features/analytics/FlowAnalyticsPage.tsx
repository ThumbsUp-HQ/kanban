import React, { useState, type JSX } from 'react';
import { useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import type { components } from '../../api/schema.gen';
import { CfdAreaChart } from './charts/CfdAreaChart';
import { CycleTimeScatterChart } from './charts/CycleTimeScatterChart';
import { AgingWipChart } from './charts/AgingWipChart';
import { MonteCarloForecastCard } from './charts/MonteCarloForecastCard';
import { CycleBurndownChart } from './charts/CycleBurndownChart';
import './FlowAnalyticsPage.css';

export type ProjectFlowMetricsResponse = components['schemas']['ProjectFlowMetricsResponse'];
export type ProjectCycleItem = components['schemas']['CycleResponse'];
export type BurndownResponse = components['schemas']['BurndownResponse'];

/**
 * Flow Telemetry Studio Page (KAN-79, KB-FLOW-METRICS-01).
 * Features Cumulative Flow Diagram (CFD), Aging WIP, Cycle and Lead Time Percentiles,
 * 10,000-trial Monte Carlo throughput forecasting, and Cycle Burndown charts.
 * Fully compliant with CSP Section 5.4 with zero inline styles.
 */
export function FlowAnalyticsPage(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const [windowDays, setWindowDays] = useState<number>(90);
  const [horizonDays, setHorizonDays] = useState<number>(14);
  const [targetItems, setTargetItems] = useState<number>(20);
  const [selectedCycleId, setSelectedCycleId] = useState<string>('');

  const key = projectKey ?? '';

  // Query flow metrics
  const {
    data: flowData,
    isLoading: isFlowLoading,
    error: flowError,
    refetch: refetchFlow,
  } = useQuery<ProjectFlowMetricsResponse>({
    queryKey: ['projects', key, 'analytics', 'flow', { windowDays, horizonDays, targetItems }],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/analytics/flow' as never, {
        params: { project_ref: key },
        query: {
          window_days: windowDays,
          horizon_days: horizonDays,
          target_items: targetItems,
        },
      });
      return res as ProjectFlowMetricsResponse;
    },
    enabled: Boolean(key),
  });

  // Query cycles for cycle burndown integration
  const { data: cycles = [] } = useQuery<ProjectCycleItem[]>({
    queryKey: ['projects', key, 'cycles'],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/cycles' as never, {
        params: { project_ref: key },
      });
      const data = res as { items?: ProjectCycleItem[] } | ProjectCycleItem[];
      return Array.isArray(data) ? data : data.items ?? [];
    },
    enabled: Boolean(key),
  });

  // Choose active or first cycle by default
  const effectiveCycleId =
    (selectedCycleId.length > 0 ? selectedCycleId : undefined) ??
    cycles.find((c) => c.status === 'active')?.id ??
    cycles[0]?.id ??
    '';
  const selectedCycle = cycles.find((c) => c.id === effectiveCycleId);

  // Query burndown for selected cycle
  const {
    data: burndownData,
    isLoading: isBurndownLoading,
  } = useQuery<BurndownResponse>({
    queryKey: ['cycles', effectiveCycleId, 'burndown'],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/cycles/{cycle_id}/burndown' as never, {
        params: { cycle_id: effectiveCycleId },
      });
      return res as BurndownResponse;
    },
    enabled: Boolean(effectiveCycleId),
  });

  return (
    <div className="kb-flow-analytics" data-testid="flow-analytics-page">
      <header className="kb-flow-header">
        <div className="kb-flow-title-group">
          <h1>
            <span role="img" aria-hidden="true">📊</span>
            Flow Telemetry Studio
          </h1>
          <p>
            Statistical flow intelligence: Cumulative Flow, Cycle Time Percentiles, Aging WIP, and Monte Carlo Forecasting
          </p>
        </div>

        <div className="kb-flow-controls">
          <label className="kb-flow-control-group">
            <span>Historical Window:</span>
            <select
              className="kb-flow-select"
              data-testid="flow-window-select"
              value={windowDays}
              onChange={(e) => { setWindowDays(Number(e.target.value)); }}
            >
              <option value={30}>Last 30 Days</option>
              <option value={60}>Last 60 Days</option>
              <option value={90}>Last 90 Days</option>
              <option value={180}>Last 180 Days</option>
              <option value={365}>Last 365 Days</option>
            </select>
          </label>

          <label className="kb-flow-control-group">
            <span>Horizon:</span>
            <input
              type="number"
              className="kb-flow-input"
              data-testid="flow-horizon-input"
              min={1}
              max={366}
              value={horizonDays}
              onChange={(e) => { setHorizonDays(Math.max(1, Math.min(366, Number(e.target.value) || 14))); }}
            />
            <span>days</span>
          </label>

          <label className="kb-flow-control-group">
            <span>Target Batch:</span>
            <input
              type="number"
              className="kb-flow-input"
              data-testid="flow-target-items-input"
              min={1}
              max={10000}
              value={targetItems}
              onChange={(e) => { setTargetItems(Math.max(1, Math.min(10000, Number(e.target.value) || 20))); }}
            />
            <span>items</span>
          </label>
        </div>
      </header>

      {isFlowLoading && (
        <div className="kb-flow-empty" data-testid="flow-loading">
          Loading flow telemetry for project {key}...
        </div>
      )}

      {Boolean(flowError) && !isFlowLoading && (
        <div className="kb-flow-error" data-testid="flow-error" role="alert">
          <p>Failed to load flow telemetry for project {key}.</p>
          <button
            type="button"
            className="kb-btn-table-toggle"
            onClick={() => { void refetchFlow(); }}
          >
            Retry
          </button>
        </div>
      )}

      {!isFlowLoading && flowData && (
        <div className="kb-flow-grid">
          {/* Cumulative Flow Diagram (CFD) */}
          <CfdAreaChart
            points={flowData.cfd.points}
            states={flowData.cfd.states}
          />

          {/* Cycle & Lead Time Scatterplot */}
          <CycleTimeScatterChart
            points={flowData.cycle_lead_time.points}
            cycleTimePercentiles={flowData.cycle_lead_time.cycle_time_percentiles}
            leadTimePercentiles={flowData.cycle_lead_time.lead_time_percentiles}
            totalCompleted={flowData.cycle_lead_time.total_completed_in_window}
          />

          {/* Aging Work in Progress (WIP) */}
          <AgingWipChart
            activeIssues={flowData.aging_wip.active_issues}
            columnThresholds={flowData.aging_wip.column_thresholds}
            totalActiveWip={flowData.aging_wip.total_active_wip}
          />

          {/* Monte Carlo Throughput & Delivery Forecast */}
          <MonteCarloForecastCard
            forecast={flowData.monte_carlo}
          />

          {/* Cycle Burndown Section */}
          <div className="kb-chart-card" data-testid="flow-cycle-burndown-section">
            <div className="kb-chart-header">
              <div>
                <h2>🔥 Sprint Cycle Burndown</h2>
                <p className="kb-chart-subtitle">
                  Inspect linear burndown trajectory against actual daily remaining scope
                </p>
              </div>
              {cycles.length > 0 && (
                <div className="kb-chart-actions">
                  <label className="kb-flow-control-group">
                    <span>Select Cycle:</span>
                    <select
                      className="kb-flow-select"
                      data-testid="flow-cycle-select"
                      value={effectiveCycleId}
                      onChange={(e) => { setSelectedCycleId(e.target.value); }}
                    >
                      {cycles.map((cyc) => (
                        <option key={cyc.id} value={cyc.id}>
                          {cyc.name} ({cyc.status})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>

            {isBurndownLoading && (
              <p className="kb-flow-empty">Loading cycle burndown...</p>
            )}

            {!isBurndownLoading && (
              <CycleBurndownChart
                burndown={burndownData}
                cycleName={selectedCycle?.name}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
export default FlowAnalyticsPage;
