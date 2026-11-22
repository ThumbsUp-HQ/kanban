import React, { useState, type JSX } from 'react';
import type { components } from '../../../api/schema.gen';

export type MonteCarloForecast = components['schemas']['MonteCarloForecast'];

export interface MonteCarloForecastCardProps {
  forecast?: MonteCarloForecast | null | undefined;
}

/**
 * Monte Carlo Throughput & Delivery Forecast Card (KAN-79, KB-FLOW-METRICS-01).
 * Displays 10,000-trial statistical simulation for "How Many?" items and "When?" target items
 * at p50, p85, and p95 confidence levels.
 */
export function MonteCarloForecastCard({
  forecast,
}: MonteCarloForecastCardProps): JSX.Element {
  const [showTable, setShowTable] = useState(false);

  if (!forecast) {
    return (
      <div className="kb-chart-card" data-testid="monte-carlo-forecast-card">
        <div className="kb-chart-header">
          <div>
            <h2>🎲 Monte Carlo Forecasting</h2>
            <p className="kb-chart-subtitle">Throughput simulation and delivery forecasting</p>
          </div>
        </div>
        <p className="kb-flow-empty">No throughput history available for Monte Carlo simulation.</p>
      </div>
    );
  }

  const { how_many, when, trials, average_daily_throughput } = forecast;

  return (
    <div className="kb-chart-card" data-testid="monte-carlo-forecast-card">
      <div className="kb-chart-header">
        <div>
          <h2>🎲 Monte Carlo Forecasting</h2>
          <p className="kb-chart-subtitle">
            {trials.toLocaleString()} trials replaying empirical velocity (average {average_daily_throughput.toFixed(2)} issues/day)
          </p>
        </div>
        <div className="kb-chart-actions">
          <button
            type="button"
            className="kb-btn-table-toggle"
            data-testid="monte-carlo-table-toggle"
            aria-expanded={showTable}
            onClick={() => { setShowTable((prev) => !prev); }}
          >
            {showTable ? 'Hide Tabular Data' : 'Show Tabular Data'}
          </button>
        </div>
      </div>

      <div className="kb-monte-carlo-cards">
        {/* How Many Forecast Box */}
        <div className="kb-forecast-box" data-testid="monte-carlo-how-many">
          <h3>How Many Issues in {how_many.horizon_days} Days?</h3>
          <div className="kb-forecast-metrics">
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">50% Confidence (Median / p50)</span>
              <span className="kb-forecast-val" data-testid="mc-how-many-p50">{how_many.p50} items</span>
            </div>
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">85% Confidence (High Confidence / p85)</span>
              <span className="kb-forecast-val" data-testid="mc-how-many-p85">{how_many.p85} items</span>
            </div>
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">95% Confidence (Commitment / p95)</span>
              <span className="kb-forecast-val" data-testid="mc-how-many-p95">{how_many.p95} items</span>
            </div>
          </div>
        </div>

        {/* When Forecast Box */}
        <div className="kb-forecast-box" data-testid="monte-carlo-when">
          <h3>When Will {when.target_items} Issues Complete?</h3>
          <div className="kb-forecast-metrics">
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">50% Confidence (p50)</span>
              <span className="kb-forecast-val" data-testid="mc-when-p50">
                {when.p50_days !== null ? `${String(when.p50_days)} days (${when.p50_date ?? 'TBD'})` : 'N/A'}
              </span>
            </div>
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">85% Confidence (p85)</span>
              <span className="kb-forecast-val" data-testid="mc-when-p85">
                {when.p85_days !== null ? `${String(when.p85_days)} days (${when.p85_date ?? 'TBD'})` : 'N/A'}
              </span>
            </div>
            <div className="kb-forecast-row">
              <span className="kb-forecast-label">95% Confidence (p95)</span>
              <span className="kb-forecast-val" data-testid="mc-when-p95">
                {when.p95_days !== null ? `${String(when.p95_days)} days (${when.p95_date ?? 'TBD'})` : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {showTable && (
        <div className="kb-analytics-table-wrapper" data-testid="monte-carlo-table-container">
          <table className="kb-analytics-table" data-testid="monte-carlo-table">
            <caption className="sr-only">Monte Carlo Simulation Confidence Results</caption>
            <thead>
              <tr>
                <th scope="col">Percentile</th>
                <th scope="col">Confidence Level</th>
                <th scope="col">Forecasted Items ({how_many.horizon_days}d)</th>
                <th scope="col">Forecasted Days ({when.target_items} Items)</th>
                <th scope="col">Estimated Completion Date</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>p50</td>
                <td>50% (Median)</td>
                <td>{how_many.p50}</td>
                <td>{when.p50_days ?? 'N/A'}</td>
                <td>{when.p50_date ?? 'N/A'}</td>
              </tr>
              <tr>
                <td>p85</td>
                <td>85% (High Confidence)</td>
                <td>{how_many.p85}</td>
                <td>{when.p85_days ?? 'N/A'}</td>
                <td>{when.p85_date ?? 'N/A'}</td>
              </tr>
              <tr>
                <td>p95</td>
                <td>95% (Commitment)</td>
                <td>{how_many.p95}</td>
                <td>{when.p95_days ?? 'N/A'}</td>
                <td>{when.p95_date ?? 'N/A'}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
