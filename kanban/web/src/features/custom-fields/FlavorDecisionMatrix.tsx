// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import type { FieldFlavor } from './api';

export interface FlavorInfo {
  flavor: FieldFlavor;
  title: string;
  latency: string;
  engine: string;
  scope: string;
  security: string;
  bestFor: string;
  example: string;
}

export const FLAVOR_DETAILS: FlavorInfo[] = [
  {
    flavor: 'scalar',
    title: 'Scalar Value',
    latency: '<1ms',
    engine: 'Static literal or JSON constant',
    scope: 'Single Issue (Static)',
    security: 'In-memory constant, zero compute overhead',
    bestFor: 'Environment pins, static labels, static SLA categories',
    example: 'scalar: "Verified"',
  },
  {
    flavor: 'formula',
    title: 'Formula Expression',
    latency: '<5ms',
    engine: 'Single-issue AST math on issue.*',
    scope: 'Single Issue',
    security: 'Pure AST sandbox, zero network/filesystem/dunder access',
    bestFor: 'SLA breach calculation, blocker count, completion %, priority multipliers',
    example: 'formula: issue.state === "DONE" ? "Completed" : "Active"',
  },
  {
    flavor: 'wasm',
    title: 'WebAssembly',
    latency: '<25ms',
    engine: 'Compiled bytecode module (Tier A)',
    scope: 'Single Issue',
    security: 'Strict Wasmtime memory and fuel limits, zero network egress',
    bestFor: 'CVSS 3.1 and 4.0 scoring, deterministic algorithms, cryptographic hashes',
    example: '// WebAssembly Tier A Module (Base64)...',
  },
  {
    flavor: 'nsjail',
    title: 'Project Rollup / nsjail',
    latency: '<=3,000ms',
    engine: 'Isolated Linux namespace process (Tier B)',
    scope: 'Cross-issue aggregation via /api/v1/ egress proxy or external PR metadata',
    security: 'Isolated Linux namespaces, cgroups, allowlisted egress',
    bestFor: 'Total project issues rollup, external Git PR status badges, complex aggregation',
    example: '# Tier B nsjail container Python script...',
  },
];

export interface FlavorDecisionMatrixProps {
  selectedFlavor?: FieldFlavor;
  onSelectFlavor?: (flavor: FieldFlavor) => void;
  isOpen?: boolean;
  onToggle?: () => void;
}

/**
 * 4-Flavor Decision Matrix ("Which Flavor Should I Use?") (KAN-15, KB-P3-AUDIT-09).
 * Compares Scalar (<1ms), Formula (<5ms), WebAssembly (<25ms), and nsjail (<=3,000ms).
 */
export function FlavorDecisionMatrix({
  selectedFlavor,
  onSelectFlavor,
  isOpen: controlledIsOpen,
  onToggle,
}: FlavorDecisionMatrixProps): JSX.Element {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = controlledIsOpen ?? internalIsOpen;

  const handleToggle = () => {
    if (onToggle) {
      onToggle();
    } else {
      setInternalIsOpen((prev) => !prev);
    }
  };

  return (
    <section
      className="flavor-matrix-section"
      aria-label="Which Flavor Should I Use?"
      data-testid="flavor-decision-matrix"
    >
      <div className="flavor-matrix-header">
        <div className="flavor-matrix-header-title-row">
          <span className="flavor-matrix-header-icon" aria-hidden="true">
            🧭
          </span>
          <h4 className="flavor-matrix-title">Which Flavor Should I Use?</h4>
          <span className="flavor-matrix-badge-count">4 Flavors Compared</span>
        </div>
        <button
          type="button"
          className="custom-field-btn custom-field-btn--secondary custom-field-btn--sm"
          onClick={handleToggle}
          aria-expanded={isOpen}
          data-testid="toggle-flavor-matrix-btn"
        >
          {isOpen ? 'Hide Matrix' : 'Compare Flavors'}
        </button>
      </div>

      {isOpen && (
        <div className="flavor-matrix-content" data-testid="flavor-matrix-content">
          <p className="flavor-matrix-subtitle">
            Choose the right execution model based on performance budgets, data scope, and isolation requirements.
          </p>

          <div className="flavor-matrix-grid" role="list">
            {FLAVOR_DETAILS.map((item) => {
              const isSelected = selectedFlavor === item.flavor;
              return (
                <div
                  key={item.flavor}
                  className={`flavor-matrix-card ${isSelected ? 'flavor-matrix-card--selected' : ''}`}
                  role="listitem"
                  data-testid={`flavor-card-${item.flavor}`}
                >
                  <div className="flavor-matrix-card-top">
                    <span className="flavor-matrix-card-title">{item.title}</span>
                    <span
                      className={`flavor-matrix-latency-pill flavor-matrix-latency-pill--${item.flavor}`}
                      data-testid={`flavor-latency-${item.flavor}`}
                    >
                      {item.latency}
                    </span>
                  </div>

                  <dl className="flavor-matrix-card-dl">
                    <dt className="flavor-matrix-card-dt">Engine:</dt>
                    <dd className="flavor-matrix-card-dd">{item.engine}</dd>

                    <dt className="flavor-matrix-card-dt">Scope:</dt>
                    <dd className="flavor-matrix-card-dd">{item.scope}</dd>

                    <dt className="flavor-matrix-card-dt">Security:</dt>
                    <dd className="flavor-matrix-card-dd">{item.security}</dd>

                    <dt className="flavor-matrix-card-dt">Best For:</dt>
                    <dd className="flavor-matrix-card-dd flavor-matrix-card-dd--highlight">
                      {item.bestFor}
                    </dd>
                  </dl>

                  <div className="flavor-matrix-example">
                    <span className="flavor-matrix-example-label">Example:</span>
                    <code className="flavor-matrix-example-code mono">{item.example}</code>
                  </div>

                  {onSelectFlavor && (
                    <button
                      type="button"
                      className={`custom-field-btn ${
                        isSelected
                          ? 'custom-field-btn--primary'
                          : 'custom-field-btn--secondary'
                      } custom-field-btn--sm flavor-matrix-select-btn`}
                      onClick={() => {
                        onSelectFlavor(item.flavor);
                      }}
                      data-testid={`select-flavor-btn-${item.flavor}`}
                    >
                      {isSelected ? 'Selected' : `Use ${item.title}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
