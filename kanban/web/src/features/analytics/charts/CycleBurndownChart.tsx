import React, { useState, type JSX } from 'react';
import type { components } from '../../../api/schema.gen';

export type BurndownResponse = components['schemas']['BurndownResponse'];
export type BurndownPoint = components['schemas']['BurndownPoint'];
export type BurndownIdealPoint = components['schemas']['BurndownIdealPoint'];

export interface CycleBurndownChartProps {
  burndown?: BurndownResponse | null | undefined;
  cycleName?: string | undefined;
}

/**
 * Accessible SVG Cycle Burndown Chart (KAN-79, KB-FLOW-METRICS-01, S7.2, S11.4).
 * Replays actual remaining issues against ideal linear target trajectory.
 * Fully CSP Section 5.4 compliant with zero inline style attributes.
 */
export function CycleBurndownChart({
  burndown,
  cycleName,
}: CycleBurndownChartProps): JSX.Element {
  const [showTable, setShowTable] = useState(false);

  if (!burndown?.series || burndown.series.length === 0) {
    return (
      <div className="kb-chart-card" data-testid="cycle-burndown-chart">
        <div className="kb-chart-header">
          <div>
            <h2>🔥 Cycle Burndown: {cycleName ?? 'Current Cycle'}</h2>
            <p className="kb-chart-subtitle">Daily scope progression vs ideal linear burndown trajectory</p>
          </div>
        </div>
        <p className="kb-flow-empty">No burndown data recorded for this cycle.</p>
      </div>
    );
  }

  const { series, ideal } = burndown;

  // Calculate bounds
  const maxScope = Math.max(...series.map((p) => p.scope), 1);
  const maxRemaining = Math.max(
    ...series.map((p) => p.remaining),
    ...ideal.map((p) => p.remaining),
    1,
  );
  const maxY = Math.max(maxScope, maxRemaining, 5);

  const width = 800;
  const height = 260;
  const padLeft = 50;
  const padRight = 30;
  const padTop = 20;
  const padBottom = 40;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const totalPoints = Math.max(series.length, ideal.length);
  const xStep = totalPoints > 1 ? plotWidth / (totalPoints - 1) : plotWidth;

  const getX = (index: number) => padLeft + index * xStep;
  const getY = (val: number) => padTop + plotHeight - (Math.max(0, val) / maxY) * plotHeight;

  // Build SVG path strings
  const idealPath = ideal
    .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(1)} ${getY(pt.remaining).toFixed(1)}`)
    .join(' ');

  const remainingPath = series
    .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(1)} ${getY(pt.remaining).toFixed(1)}`)
    .join(' ');

  const latestSeries = series[series.length - 1];
  const latestIdeal = ideal[ideal.length - 1];

  return (
    <div className="kb-chart-card" data-testid="cycle-burndown-chart">
      <div className="kb-chart-header">
        <div>
          <h2>🔥 Cycle Burndown: {cycleName ?? 'Current Cycle'}</h2>
          <p className="kb-chart-subtitle">
            Daily scope progression vs ideal linear burndown trajectory
          </p>
        </div>
        <div className="kb-chart-actions">
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="burndown-table-toggle"
            aria-expanded={showTable}
            onClick={() => { setShowTable((prev) => !prev); }}
          >
            {showTable ? 'Hide Tabular Data' : 'Show Tabular Data'}
          </button>
        </div>
      </div>

      <div className="kb-percentile-badges">
        <span className="kb-badge kb-badge-p50" data-testid="burndown-badge-scope">
          Total Scope: {latestSeries?.scope ?? 0} items
        </span>
        <span className="kb-badge kb-badge-p85" data-testid="burndown-badge-remaining">
          Remaining: {latestSeries?.remaining ?? 0} items
        </span>
        <span className="kb-badge kb-badge-p95" data-testid="burndown-badge-ideal">
          Ideal Target: {Math.round(latestIdeal?.remaining ?? 0)} items
        </span>
      </div>

      <div className="kb-chart-svg-container">
        <svg
          viewBox="0 0 800 260"
          className="kb-chart-svg"
          role="img"
          aria-label={`Cycle burndown chart for ${cycleName ?? 'current cycle'}`}
        >
          {/* Horizontal Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const y = padTop + plotHeight * (1 - pct);
            const val = Math.round(maxY * pct);
            return (
              <g key={pct}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke="var(--border-subtle, #e5e7eb)"
                  strokeDasharray="2 2"
                />
                <text
                  x={padLeft - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--fg-secondary, #6b7280)"
                >
                  {val}
                </text>
              </g>
            );
          })}

          {/* Axes */}
          <line
            x1={padLeft}
            y1={padTop + plotHeight}
            x2={width - padRight}
            y2={padTop + plotHeight}
            stroke="var(--border-strong, #9ca3af)"
          />
          <line
            x1={padLeft}
            y1={padTop}
            x2={padLeft}
            y2={padTop + plotHeight}
            stroke="var(--border-strong, #9ca3af)"
          />

          {/* Ideal line (dashed) */}
          {idealPath && (
            <path
              d={idealPath}
              fill="none"
              stroke="var(--chart-line-2, #94a3b8)"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
          )}

          {/* Remaining line (solid) */}
          {remainingPath && (
            <path
              d={remainingPath}
              fill="none"
              stroke="var(--chart-line-1, #2563eb)"
              strokeWidth="2.5"
            />
          )}

          {/* Data Points on Remaining line */}
          {series.map((pt, idx) => (
            <circle
              key={pt.date}
              cx={getX(idx)}
              cy={getY(pt.remaining)}
              r="4"
              fill="var(--chart-line-1, #2563eb)"
              stroke="var(--bg-surface, #ffffff)"
              strokeWidth="1.5"
            >
              <title>{`${pt.date}: ${String(pt.remaining)} remaining of ${String(pt.scope)} scope`}</title>
            </circle>
          ))}

          {/* X-axis date labels */}
          {series.map((pt, idx) => {
            if (series.length > 10 && idx % Math.ceil(series.length / 8) !== 0 && idx !== series.length - 1) {
              return null;
            }
            return (
              <text
                key={`label-${pt.date}`}
                x={getX(idx)}
                y={padTop + plotHeight + 20}
                textAnchor="middle"
                fontSize="10"
                fill="var(--fg-secondary, #6b7280)"
              >
                {pt.date.slice(5)}
              </text>
            );
          })}
        </svg>
      </div>

      {showTable && (
        <div className="kb-analytics-table-wrapper" data-testid="burndown-table-container">
          <table className="kb-analytics-table" data-testid="burndown-table">
            <caption className="sr-only">Daily cycle burndown progress</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Total Scope</th>
                <th scope="col">Actual Remaining</th>
                <th scope="col">Ideal Trajectory</th>
              </tr>
            </thead>
            <tbody>
              {series.map((pt, idx) => {
                const idealPt = ideal[idx];
                return (
                  <tr key={pt.date}>
                    <td>{pt.date}</td>
                    <td>{pt.scope}</td>
                    <td>{pt.remaining}</td>
                    <td>{idealPt ? idealPt.remaining.toFixed(1) : 'N/A'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
