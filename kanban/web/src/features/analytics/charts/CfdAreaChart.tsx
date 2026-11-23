import React, { useState, type JSX } from 'react';
import type { components } from '../../../api/schema.gen';

type CfdPoint = components['schemas']['CfdPoint'];
type CfdStateMeta = components['schemas']['CfdStateMeta'];

export interface CfdAreaChartProps {
  points: CfdPoint[];
  states?: CfdStateMeta[];
  isLoading?: boolean;
}

export function CfdAreaChart({
  points,
  isLoading = false,
}: CfdAreaChartProps): JSX.Element {
  const [showTable, setShowTable] = useState(false);

  if (isLoading) {
    return (
      <div className="kb-chart-card" data-testid="cfd-loading">
        <p>Loading Cumulative Flow Diagram...</p>
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <div className="kb-chart-card" data-testid="cfd-empty">
        <p className="kb-flow-empty">No flow telemetry data in this time window.</p>
      </div>
    );
  }

  const width = 800;
  const height = 300;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 40;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const maxTotal = Math.max(1, ...points.map((p) => p.total));
  const n = points.length;

  // Build coordinate stacks for each point
  // Layers from bottom to top: completed, started, unstarted, backlog, cancelled
  const xCoord = (idx: number): number => padLeft + (n > 1 ? (idx / (n - 1)) * chartW : chartW / 2);
  const yCoord = (val: number): number => padTop + chartH - (val / maxTotal) * chartH;

  const stackCompleted: { x: number; y0: number; y1: number }[] = [];
  const stackStarted: { x: number; y0: number; y1: number }[] = [];
  const stackUnstarted: { x: number; y0: number; y1: number }[] = [];
  const stackBacklog: { x: number; y0: number; y1: number }[] = [];

  points.forEach((p, idx) => {
    const x = xCoord(idx);
    const c = p.completed;
    const s = p.started;
    const u = p.unstarted;
    const b = p.backlog;

    const yBase = yCoord(0);
    const yC = yCoord(c);
    const yS = yCoord(c + s);
    const yU = yCoord(c + s + u);
    const yB = yCoord(c + s + u + b);

    stackCompleted.push({ x, y0: yBase, y1: yC });
    stackStarted.push({ x, y0: yC, y1: yS });
    stackUnstarted.push({ x, y0: yS, y1: yU });
    stackBacklog.push({ x, y0: yU, y1: yB });
  });

  const makeAreaPath = (stack: { x: number; y0: number; y1: number }[]): string => {
    if (stack.length === 0) return '';
    const topPoints = stack.map((s) => `${String(s.x)},${String(s.y1)}`).join(' L ');
    const bottomPoints = [...stack].reverse().map((s) => `${String(s.x)},${String(s.y0)}`).join(' L ');
    return `M ${topPoints} L ${bottomPoints} Z`;
  };

  const pathCompleted = makeAreaPath(stackCompleted);
  const pathStarted = makeAreaPath(stackStarted);
  const pathUnstarted = makeAreaPath(stackUnstarted);
  const pathBacklog = makeAreaPath(stackBacklog);

  return (
    <div className="kb-chart-card" data-testid="cfd-area-chart-card">
      <div className="kb-chart-header">
        <div>
          <h2>
            <span>📈</span> Cumulative Flow Diagram (CFD)
          </h2>
          <p className="kb-chart-subtitle">
            Daily distribution of work item states replayed across the analysis window
          </p>
        </div>
        <div className="kb-chart-actions">
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="cfd-table-toggle"
            onClick={() => { setShowTable(!showTable); }}
            aria-expanded={showTable}
            aria-controls="cfd-data-table"
          >
            {showTable ? 'Hide Table' : 'Show Table (A11y)'}
          </button>
        </div>
      </div>

      <div className="kb-percentile-badges">
        <span className="kb-badge kb-badge-p95">
          <span>●</span> Completed: {points[points.length - 1]?.completed ?? 0}
        </span>
        <span className="kb-badge kb-badge-p85">
          <span>●</span> In Progress (Started): {points[points.length - 1]?.started ?? 0}
        </span>
        <span className="kb-badge kb-badge-p50">
          <span>●</span> Unstarted: {points[points.length - 1]?.unstarted ?? 0}
        </span>
        <span className="kb-badge">
          <span>●</span> Backlog: {points[points.length - 1]?.backlog ?? 0}
        </span>
      </div>

      <div className="kb-chart-svg-container">
        <svg
          className="kb-chart-svg"
          viewBox="0 0 800 300"
          role="img"
          aria-label="Cumulative Flow Diagram stacked area chart"
        >
          <title>Cumulative Flow Diagram</title>
          <desc>Stacked area chart showing completed, started, unstarted, and backlog counts over time.</desc>

          {/* Grid lines */}
          <line
            x1={padLeft}
            y1={yCoord(maxTotal)}
            x2={width - padRight}
            y2={yCoord(maxTotal)}
            stroke="var(--border-subtle, #e5e7eb)"
            strokeDasharray="4 4"
          />
          <line
            x1={padLeft}
            y1={yCoord(maxTotal / 2)}
            x2={width - padRight}
            y2={yCoord(maxTotal / 2)}
            stroke="var(--border-subtle, #e5e7eb)"
            strokeDasharray="4 4"
          />
          <line
            x1={padLeft}
            y1={padTop + chartH}
            x2={width - padRight}
            y2={padTop + chartH}
            stroke="var(--border-strong, #d1d5db)"
          />

          {/* Stacked Areas */}
          <path d={pathBacklog} fill="var(--state-backlog-fg, #94a3b8)" fillOpacity="0.5" data-testid="cfd-area-backlog" />
          <path d={pathUnstarted} fill="var(--state-unstarted-fg, #60a5fa)" fillOpacity="0.6" data-testid="cfd-area-unstarted" />
          <path d={pathStarted} fill="var(--state-started-fg, #f59e0b)" fillOpacity="0.7" data-testid="cfd-area-started" />
          <path d={pathCompleted} fill="var(--state-completed-fg, #10b981)" fillOpacity="0.8" data-testid="cfd-area-completed" />

          {/* Axis labels */}
          <text
            x={padLeft - 8}
            y={yCoord(maxTotal) + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            {maxTotal}
          </text>
          <text
            x={padLeft - 8}
            y={padTop + chartH + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            0
          </text>

          {/* Date labels */}
          {points.length > 0 && points[0] && (
            <text
              x={padLeft}
              y={height - 10}
              textAnchor="start"
              fontSize="10"
              fill="var(--fg-secondary, #4b5563)"
            >
              {points[0].date}
            </text>
          )}
          {points.length > 1 && points[points.length - 1] && (
            <text
              x={width - padRight}
              y={height - 10}
              textAnchor="end"
              fontSize="10"
              fill="var(--fg-secondary, #4b5563)"
            >
              {points[points.length - 1]?.date ?? ''}
            </text>
          )}
        </svg>
      </div>

      {showTable && (
        <div className="kb-analytics-table-wrapper">
          <table
            className="kb-analytics-table"
            id="cfd-data-table"
            data-testid="cfd-data-table"
            aria-label="CFD Data Table"
          >
            <thead>
              <tr>
                <th>Date</th>
                <th>Completed</th>
                <th>In Progress (Started)</th>
                <th>Unstarted</th>
                <th>Backlog</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.date}>
                  <td>{p.date}</td>
                  <td>{p.completed}</td>
                  <td>{p.started}</td>
                  <td>{p.unstarted}</td>
                  <td>{p.backlog}</td>
                  <td>{p.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
