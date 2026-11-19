// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import {
  validateAgentDefinition,
  type AgentDefinitionResponse,
  type AgentValidationResponse,
} from './agentDefinitionsApi';

interface AgentValidationModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: AgentDefinitionResponse | null;
}

function AgentValidationContent({
  onClose,
  agent,
}: {
  onClose: () => void;
  agent: AgentDefinitionResponse;
}): JSX.Element {
  const [result, setResult] = useState<AgentValidationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function runVal() {
      try {
        const res = await validateAgentDefinition(agent.id);
        if (!active) return;
        setResult(res);
      } catch (err: unknown) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Validation failed');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void runVal();

    return () => {
      active = false;
    };
  }, [agent.id]);

  return (
    <div className="kb-modal-card">
      <div className="kb-modal-header">
        <h2 id="agent-val-title">Test Validation: {agent.display_name}</h2>
        <button
          type="button"
          className="kb-btn kb-btn-secondary"
          onClick={onClose}
          aria-label="Close dialog"
          data-testid="close-validation-modal-btn"
        >
          ✕
        </button>
      </div>

      <p className="kb-agent-studio-subtitle">
        Executing local forensic verification report (<code>kanban-agent validate-echo</code>) for <code>@{agent.slug}</code>.
      </p>

      {error && (
        <div className="kb-form-hint" style={{ color: '#ef4444', margin: '12px 0' }} data-testid="validation-error">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="validation-loading" style={{ margin: '24px 0' }}>
          Running kanban-agent validate-echo...
        </div>
      ) : result ? (
        <>
          <div className="kb-validation-summary-card" data-testid="validation-summary">
            <div>
              <span
                className={`kb-verdict-badge ${
                  result.valid ? 'kb-verdict-badge--success' : 'kb-verdict-badge--error'
                }`}
                data-testid="validation-verdict-badge"
              >
                {result.valid ? '✓ PASS (Valid)' : `✗ FAIL (Exit ${String(result.exit_code)})`}
              </span>
              <div style={{ marginTop: '4px', fontSize: '12px' }}>
                Status: <strong>{result.status}</strong>
              </div>
            </div>

            <div style={{ textAlign: 'right', fontSize: '12px' }}>
              <div>
                Latency: <strong>{result.latency_ms.toFixed(1)} ms</strong>
              </div>
              <div>
                Tokens: <strong>{String(result.tokens_in)} in / {String(result.tokens_out)} out</strong>
              </div>
            </div>
          </div>

          <div className="kb-form-group">
            <label className="kb-form-label">Forensic 4-Section Validation Report</label>
            <pre className="kb-validation-report" data-testid="validation-report-output">
              {result.report_text}
            </pre>
          </div>
        </>
      ) : null}

      <div className="kb-modal-footer">
        <button
          type="button"
          className="kb-btn kb-btn-primary"
          onClick={onClose}
          data-testid="dismiss-validation-btn"
        >
          Done
        </button>
      </div>
    </div>
  );
}

export function AgentValidationModal({
  isOpen,
  onClose,
  agent,
}: AgentValidationModalProps): JSX.Element | null {
  if (!isOpen || !agent) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-val-title"
      className="kb-modal-backdrop"
      data-testid="agent-validation-modal"
    >
      <AgentValidationContent
        key={agent.id}
        onClose={onClose}
        agent={agent}
      />
    </div>
  );
}
