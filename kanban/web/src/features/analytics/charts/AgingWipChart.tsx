import React, { useState, type JSX } from 'react';
import type { components } from '../../../api/schema.gen';

type AgingWipIssue = components['schemas']['AgingWipIssue'];
type ColumnAgingThresholds = components['schemas']['ColumnAgingThresholds'];

export interface AgingWipChartProps {
  activeIssues: AgingWipIssue[];
  columnThresholds: Record<string, ColumnAgingThresholds>;
  totalActiveWip: number;
  isLoading?: boolean;
}

export function AgingWipChart({
  activeIssues,
  columnThresholds,
  totalActiveWip,
  isLoading = false,
}: AgingWipChartProps): JSX.Element {
  const [showTable, setShowTable] = useState(false);

  if (isLoading) {
    return (
      <div className="kb-chart-card" data-testid="aging-wip-loading">
        <p>Loading Aging WIP chart...</p>
      </div>
    );
  }

  const columns = Object.values(columnThresholds);

  if (activeIssues.length === 0 || columns.length === 0) {
    return (
      <div className="kb-chart-card" data-testid="aging-wip-empty">
        <div className="kb-chart-header">
          <h2><span>⌛</span> Aging Work In Progress (WIP)</h2>
        </div>
        <p className="kb-flow-empty">No active work items currently in started workflow states.</p>
      </div>
    );
  }

  const width = 800;
  const height = 300;
  const padLeft = 60;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 40;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const maxHours = Math.max(
    24,
    ...activeIssues.map((i) => i.age_in_current_state_hours),
    ...columns.map((c) => c.p95_hours * 1.2),
  );

  const colWidth = chartW / columns.length;
  const xColMid = (idx: number): number => padLeft + idx * colWidth + colWidth / 2;
  const yCoord = (h: number): number => padTop + chartH - Math.min(chartH, (h / maxHours) * chartH);

  return (
    <div className="kb-chart-card" data-testid="aging-wip-card">
      <div className="kb-chart-header">
        <div>
          <h2>
            <span>⌛</span> Aging Work In Progress (WIP)
          </h2>
          <p className="kb-chart-subtitle">
            Current age of active tickets in progress compared to column historical percentiles (
            {totalActiveWip} active items)
          </p>
        </div>
        <div className="kb-chart-actions">
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="aging-wip-table-toggle"
            onClick={() => { setShowTable(!showTable); }}
            aria-expanded={showTable}
            aria-controls="aging-wip-data-table"
          >
            {showTable ? 'Hide Table' : 'Show Table (A11y)'}
          </button>
        </div>
      </div>

      <div className="kb-chart-svg-container">
        <svg
          className="kb-chart-svg"
          viewBox="0 0 800 300"
          role="img"
          aria-label="Aging WIP column distribution chart"
        >
          <title>Aging Work In Progress</title>
          <desc>
            Chart illustrating active work item ages in current column states against historical p50,
            p85, and p95 thresholds.
          </desc>

          {/* Column dividers and column names */}
          {columns.map((col, idx) => {
            const xLeft = padLeft + idx * colWidth;
            const xMid = xColMid(idx);
            const p50Y = yCoord(col.p50_hours);
            const p85Y = yCoord(col.p85_hours);
            const p95Y = yCoord(col.p95_hours);

            return (
              <g key={col.state_id} data-testid={`aging-col-${col.state_name}`}>
                {/* Column background band */}
                <rect
                  x={xLeft + 4}
                  y={padTop}
                  width={colWidth - 8}
                  height={chartH}
                  fill="var(--bg-canvas, rgba(0,0,0,0.02))"
                  rx={4}
                />

                {/* Threshold lines */}
                {col.p50_hours > 0 && (
                  <line
                    x1={xLeft + 4}
                    y1={p50Y}
                    x2={xLeft + colWidth - 4}
                    y2={p50Y}
                    stroke="rgba(96, 165, 250, 0.7)"
                    strokeDasharray="3 3"
                  />
                )}
                {col.p85_hours > 0 && (
                  <line
                    x1={xLeft + 4}
                    y1={p85Y}
                    x2={xLeft + colWidth - 4}
                    y2={p85Y}
                    stroke="rgba(245, 158, 11, 0.8)"
                    strokeDasharray="4 4"
                  />
                )}
                {col.p95_hours > 0 && (
                  <line
                    x1={xLeft + 4}
                    y1={p95Y}
                    x2={xLeft + colWidth - 4}
                    y2={p95Y}
                    stroke="rgba(239, 68, 68, 0.8)"
                    strokeDasharray="2 2"
                  />
                )}

                {/* Column name header */}
                <text
                  x={xMid}
                  y={height - 12}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight="600"
                  fill="var(--fg-primary, #111827)"
                >
                  {col.state_name}
                </text>
              </g>
            );
          })}

          {/* Active Items */}
          {activeIssues.map((iss) => {
            const colIdx = columns.findIndex((c) => c.state_id === iss.state_id);
            if (colIdx === -1) return null;

            const colMid = xColMid(colIdx);
            const cy = yCoord(iss.age_in_current_state_hours);
            const col = columns[colIdx];
            const isExceeded = col && col.p85_hours > 0 && iss.age_in_current_state_hours > col.p85_hours;

            return (
              <g key={iss.issue_id} data-testid={`aging-item-${iss.issue_key}`}>
                <circle
                  cx={colMid}
                  cy={cy}
                  r={isExceeded ? 7 : 5}
                  fill={isExceeded ? '#dc2626' : '#2563eb'}
                  stroke="var(--bg-surface, #ffffff)"
                  strokeWidth={2}
                >
                  <title>
                    {`${iss.issue_key} (${iss.title}): ${String(iss.age_in_current_state_hours)}h in state${
                      isExceeded ? ' (EXCEEDS p85)' : ''
                    }`}
                  </title>
                </circle>
                <text
                  x={colMid + 10}
                  y={cy + 4}
                  fontSize="9"
                  fontFamily="var(--font-mono, monospace)"
                  fontWeight={isExceeded ? '700' : '400'}
                  fill={isExceeded ? '#dc2626' : 'var(--fg-secondary, #4b5563)'}
                >
                  {iss.issue_key} ({Math.round(iss.age_in_current_state_hours)}h)
                </text>
              </g>
            );
          })}

          {/* Y Axis scale */}
          <text
            x={padLeft - 8}
            y={padTop + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            {Math.round(maxHours)}h
          </text>
          <text
            x={padLeft - 8}
            y={padTop + chartH + 4}
            textAnchor="end"
            fontSize="10"
            fill="var(--fg-secondary, #4b5563)"
          >
            0h
          </text>
        </svg>
      </div>

      {showTable && (
        <div className="kb-analytics-table-wrapper">
          <table
            className="kb-analytics-table"
            id="aging-wip-data-table"
            data-testid="aging-wip-data-table"
            aria-label="Aging WIP Data Table"
          >
            <thead>
              <tr>
                <th>Key</th>
                <th>Title</th>
                <th>State</th>
                <th>Age in Current State</th>
                <th>Total WIP Age</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {activeIssues.map((iss) => {
                const col = columnThresholds[iss.state_id];
                const isExceeded = col && col.p85_hours > 0 && iss.age_in_current_state_hours > col.p85_hours;
                return (
                  <tr key={iss.issue_id}>
                    <td>{iss.issue_key}</td>
                    <td>{iss.title}</td>
                    <td>{iss.state_name}</td>
                    <td>{iss.age_in_current_state_hours} hours</td>
                    <td>{iss.total_wip_hours} hours</td>
                    <td>
                      {isExceeded ? (
                        <span className="kb-aging-warning-badge" data-testid={`aging-exceeded-${iss.issue_key}`}>
                          ⏱️ Exceeds p85
                        </span>
                      ) : (
                        <span>Normal</span>
                      )}
                    </td>
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
