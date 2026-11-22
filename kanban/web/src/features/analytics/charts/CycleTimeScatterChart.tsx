import React, { useState, type JSX } from 'react';
import type { components } from '../../../api/schema.gen';

type CycleLeadTimePoint = components['schemas']['CycleLeadTimePoint'];
type PercentileValues = components['schemas']['PercentileValues'];

export interface CycleTimeScatterChartProps {
  points: CycleLeadTimePoint[];
  cycleTimePercentiles: PercentileValues;
  leadTimePercentiles: PercentileValues;
  totalCompleted: number;
  isLoading?: boolean;
}

export function CycleTimeScatterChart({
  points,
  cycleTimePercentiles,
  leadTimePercentiles,
  totalCompleted,
  isLoading = false,
}: CycleTimeScatterChartProps): JSX.Element {
  const [showTable, setShowTable] = useState(false);
  const [metricMode, setMetricMode] = useState<'cycle' | 'lead'>('cycle');

  if (isLoading) {
    return (
      <div className="kb-chart-card" data-testid="cycletime-loading">
        <p>Loading Cycle Time scatterplot...</p>
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <div className="kb-chart-card" data-testid="cycletime-empty">
        <div className="kb-chart-header">
          <h2><span>⏱️</span> Cycle Time & Lead Time Scatterplot</h2>
        </div>
        <p className="kb-flow-empty">No work items were completed in this time window.</p>
      </div>
    );
  }

  const width = 800;
  const height = 300;
  const padLeft = 45;
  const padRight = 30;
  const padTop = 20;
  const padBottom = 40;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const currentPercentiles = metricMode === 'cycle' ? cycleTimePercentiles : leadTimePercentiles;
  const maxDay = Math.max(
    1,
    currentPercentiles.p95 * 1.25,
    ...points.map((p) => (metricMode === 'cycle' ? p.cycle_time_days : p.lead_time_days)),
  );

  const xCoord = (idx: number): number => {
    const n = points.length;
    return padLeft + (n > 1 ? (idx / (n - 1)) * chartW : chartW / 2);
  };
  const yCoord = (days: number): number => padTop + chartH - Math.min(chartH, (days / maxDay) * chartH);

  const yP50 = yCoord(currentPercentiles.p50);
  const yP85 = yCoord(currentPercentiles.p85);
  const yP95 = yCoord(currentPercentiles.p95);

  return (
    <div className="kb-chart-card" data-testid="cycle-time-scatter-card">
      <div className="kb-chart-header">
        <div>
          <h2>
            <span>⏱️</span> {metricMode === 'cycle' ? 'Cycle Time' : 'Lead Time'} Scatterplot
          </h2>
          <p className="kb-chart-subtitle">
            {metricMode === 'cycle'
              ? 'Duration from first starting work to completion'
              : 'Duration from ticket creation to completion'}{' '}
            ({totalCompleted} items completed)
          </p>
        </div>
        <div className="kb-chart-actions">
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="mode-toggle-btn"
            onClick={() => { setMetricMode(metricMode === 'cycle' ? 'lead' : 'cycle'); }}
          >
            Switch to {metricMode === 'cycle' ? 'Lead Time' : 'Cycle Time'}
          </button>
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="cycletime-table-toggle"
            onClick={() => { setShowTable(!showTable); }}
            aria-expanded={showTable}
            aria-controls="cycletime-data-table"
          >
            {showTable ? 'Hide Table' : 'Show Table (A11y)'}
          </button>
        </div>
      </div>

      <div className="kb-percentile-badges">
        <span className="kb-badge kb-badge-p50" data-testid="p50-badge">
          p50 (50% confidence): {currentPercentiles.p50} days
        </span>
        <span className="kb-badge kb-badge-p85" data-testid="p85-badge">
          p85 (85% confidence): {currentPercentiles.p85} days
        </span>
        <span className="kb-badge kb-badge-p95" data-testid="p95-badge">
          p95 (95% confidence): {currentPercentiles.p95} days
        </span>
      </div>

      <div className="kb-chart-svg-container">
        <svg
          className="kb-chart-svg"
          viewBox="0 0 800 300"
          role="img"
          aria-label={`${metricMode === 'cycle' ? 'Cycle Time' : 'Lead Time'} scatterplot`}
        >
          <title>{metricMode === 'cycle' ? 'Cycle Time' : 'Lead Time'} Scatterplot</title>
          <desc>
            Scatterplot displaying duration for each completed ticket with p50, p85, and p95 confidence lines.
          </desc>

          {/* Axes & Grid */}
          <line
            x1={padLeft}
            y1={padTop + chartH}
            x2={width - padRight}
            y2={padTop + chartH}
            stroke="var(--border-strong, #d1d5db)"
          />

          {/* Percentile Threshold Lines */}
          <line
            x1={padLeft}
            y1={yP50}
            x2={width - padRight}
            y2={yP50}
            stroke="rgba(96, 165, 250, 0.9)"
            strokeDasharray="4 4"
            data-testid="p50-line"
          />
          <text
            x={width - padRight}
            y={yP50 - 4}
            textAnchor="end"
            fontSize="10"
            fill="rgba(96, 165, 250, 1)"
          >
            p50 ({currentPercentiles.p50}d)
          </text>

          <line
            x1={padLeft}
            y1={yP85}
            x2={width - padRight}
            y2={yP85}
            stroke="rgba(245, 158, 11, 0.9)"
            strokeDasharray="6 4"
            data-testid="p85-line"
          />
          <text
            x={width - padRight}
            y={yP85 - 4}
            textAnchor="end"
            fontSize="10"
            fill="rgba(245, 158, 11, 1)"
          >
            p85 ({currentPercentiles.p85}d)
          </text>

          <line
            x1={padLeft}
            y1={yP95}
            x2={width - padRight}
            y2={yP95}
            stroke="rgba(16, 185, 129, 0.9)"
            strokeDasharray="2 2"
            data-testid="p95-line"
          />
          <text
            x={width - padRight}
            y={yP95 - 4}
            textAnchor="end"
            fontSize="10"
            fill="rgba(16, 185, 129, 1)"
          >
            p95 ({currentPercentiles.p95}d)
          </text>

          {/* Scatter Points */}
          {points.map((pt, idx) => {
            const val = metricMode === 'cycle' ? pt.cycle_time_days : pt.lead_time_days;
            const cx = xCoord(idx);
            const cy = yCoord(val);
            return (
              <circle
                key={pt.issue_id}
                cx={cx}
                cy={cy}
                r={5}
                fill={
                  val > currentPercentiles.p85
                    ? 'rgba(239, 68, 68, 0.9)'
                    : 'rgba(37, 99, 235, 0.8)'
                }
                stroke="var(--bg-surface, #ffffff)"
                strokeWidth={1.5}
                data-testid={`scatter-dot-${pt.issue_key}`}
              >
                <title>{`${pt.issue_key} - ${pt.title}: ${String(val)} days`}</title>
              </circle>
            );
          })}

          {/* Y Axis Labels */}
          <text
            x={padLeft - 8}
            y={yCoord(maxDay) + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            {Math.round(maxDay)}d
          </text>
          <text
            x={padLeft - 8}
            y={padTop + chartH + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            0d
          </text>
        </svg>
      </div>

      {showTable && (
        <div className="kb-analytics-table-wrapper">
          <table
            className="kb-analytics-table"
            id="cycletime-data-table"
            data-testid="cycletime-data-table"
            aria-label="Cycle Time Data Table"
          >
            <thead>
              <tr>
                <th>Key</th>
                <th>Title</th>
                <th>Completed At</th>
                <th>Cycle Time (days)</th>
                <th>Lead Time (days)</th>
              </tr>
            </thead>
            <tbody>
              {points.map((pt) => (
                <tr key={pt.issue_id}>
                  <td>{pt.issue_key}</td>
                  <td>{pt.title}</td>
                  <td>{new Date(pt.completed_at).toLocaleDateString()}</td>
                  <td>{pt.cycle_time_days}</td>
                  <td>{pt.lead_time_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
