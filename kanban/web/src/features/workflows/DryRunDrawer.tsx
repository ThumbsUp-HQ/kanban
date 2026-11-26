// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useEffect, useRef, useState, type JSX } from 'react';
import {
  dryRunWorkflowHooks,
  type DryRunPayload,
  type DryRunResponse,
  type DryRunStepResult,
  type DryRunSampleTicket,
} from './api';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';

export interface DryRunDrawerProps {
  isOpen: boolean;
  projectKey: string;
  transition: { from_state: string | null; to_state: string };
  onClose: () => void;
  dryRunRunner?: typeof dryRunWorkflowHooks;
}

const DEFAULT_SAMPLE_TICKET: DryRunSampleTicket = {
  summary: 'Fix RLS policy on issue comments and add audit logging',
  description_markdown:
    '### Implementation Notes\nUpdates `comments` table RLS policy to enforce project member visibility.\n\nVerification: docs/qa/KAN-142/proof.txt',
  priority: 'High',
  labels: ['security', 'backend'],
};

function DryRunDrawerInner({
  projectKey,
  transition,
  onClose,
  dryRunRunner = dryRunWorkflowHooks,
}: Omit<DryRunDrawerProps, 'isOpen'>): JSX.Element {
  const [mode, setMode] = useState<'sample' | 'issue'>('sample');
  const [issueKey, setIssueKey] = useState(`${projectKey}-1`);
  const [summary, setSummary] = useState(DEFAULT_SAMPLE_TICKET.summary);
  const [description, setDescription] = useState(DEFAULT_SAMPLE_TICKET.description_markdown);
  const [priority, setPriority] = useState(DEFAULT_SAMPLE_TICKET.priority);
  const [labelsStr, setLabelsStr] = useState(DEFAULT_SAMPLE_TICKET.labels.join(', '));

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DryRunResponse | null>(null);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleRun = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    const payload: DryRunPayload = {
      from_state: transition.from_state,
      to_state: transition.to_state,
    };

    if (mode === 'issue') {
      const trimmedKey = issueKey.trim();
      if (!trimmedKey) {
        setError('Issue key is required');
        setIsLoading(false);
        return;
      }
      payload.issue_key = trimmedKey;
    } else {
      payload.sample_ticket = {
        summary: summary.trim(),
        description_markdown: description,
        priority: priority.trim(),
        labels: labelsStr
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      };
    }

    try {
      const data = await dryRunRunner(projectKey, payload);
      setResult(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Dry-run request failed.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyCli = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedCmd(cmd);
      /* v8 ignore start */
      if (copyTimeoutRef.current !== null) {
        clearTimeout(copyTimeoutRef.current);
      }
      copyTimeoutRef.current = setTimeout(() => {
        if (typeof window !== 'undefined') {
          setCopiedCmd(null);
        }
      }, 2000);
    } catch {
      // Ignore clipboard fallback
    }
    /* v8 ignore stop */
  };

  const formatDurationMs = (durationUs: number): string => {
    const ms = durationUs / 1000;
    if (ms < 1) return '<1ms';
    return `${ms.toFixed(1)}ms`;
  };

  const renderStepResult = (step: DryRunStepResult) => {
    let resultGlyph = '✅';
    let resultLabel = 'Allowed';

    if (step.result === 'mutated') {
      resultGlyph = '✏️';
      resultLabel = 'Mutated';
    } else if (step.result === 'rejected') {
      resultGlyph = '🛑';
      resultLabel = 'Rejected';
    } else if (step.result === 'error') {
      resultGlyph = '⚠️';
      resultLabel = 'Error';
    } else if (step.result === 'skipped_async') {
      resultGlyph = '🤖';
      resultLabel = 'Skipped Async';
    }

    const defaultCliCmd =
      step.cli_command ??
      `uv run kanban-agent validate-transition --project ${projectKey} --transition "${
        transition.from_state ?? '*'
      } -> ${transition.to_state}" --agent ${step.name}`;

    return (
      <div
        key={step.order}
        className="dry-run-step-row"
        data-testid={`dry-run-step-${String(step.order)}`}
      >
        <div className="dry-run-step-header">
          <div className="dry-run-step-left">
            <span>
              {resultGlyph} {step.order}. <strong>{step.name}</strong>
            </span>
            <span className="hook-metric-pill">[{step.hook_kind}]</span>
            <span className="active-hooks-badge">{resultLabel}</span>
          </div>
          <span className="hook-metric-pill">{formatDurationMs(step.duration_us)}</span>
        </div>

        {/* Reason display (rendered strictly as text node) */}
        {step.reason && (
          <div className="dry-run-step-reason" data-testid={`dry-run-reason-${String(step.order)}`}>
            <strong>Rejection Reason:</strong> {step.reason}
          </div>
        )}

        {/* Field updates for mutated */}
        {step.field_updates && Object.keys(step.field_updates).length > 0 && (
          <div className="workflow-notice dry-run-mutations-box" data-testid={`dry-run-updates-${String(step.order)}`}>
            <strong>Mutations applied:</strong>
            <div className="dry-run-diff-table" data-testid={`dry-run-diff-${String(step.order)}`}>
              <div className="dry-run-diff-header">
                <span>Field</span>
                <span>Before</span>
                <span>After</span>
              </div>
              {Object.entries(step.field_updates).map(([fieldKey, newVal]) => {
                const beforeVal =
                  mode === 'sample'
                    ? (fieldKey === 'priority'
                        ? priority
                        : fieldKey === 'summary'
                        ? summary
                        : '(current)')
                    : '(current)';
                return (
                  <div key={fieldKey} className="dry-run-diff-row">
                    <span className="dry-run-diff-field">{fieldKey}</span>
                    <span className="dry-run-diff-before">{JSON.stringify(beforeVal)}</span>
                    <span className="dry-run-diff-arrow">➔</span>
                    <span className="dry-run-diff-after">{JSON.stringify(newVal)}</span>
                  </div>
                );
              })}
            </div>
            <pre className="dry-run-cli-code">{JSON.stringify(step.field_updates, null, 2)}</pre>
          </div>
        )}

        {/* Async CLI command */}
        {step.result === 'skipped_async' && (
          <div className="dry-run-copyable-cli" data-testid={`dry-run-cli-${String(step.order)}`}>
            <span>🤖 Async gate - copy CLI command:</span>
            <code className="dry-run-cli-code">{defaultCliCmd}</code>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-sm"
              onClick={() => {
                void handleCopyCli(defaultCliCmd);
              }}
              aria-label={`Copy CLI command for ${step.name}`}
            >
              {copiedCmd === defaultCliCmd ? 'Copied!' : 'Copy CLI Command'}
            </button>
          </div>
        )}
      </div>
    );
  };

  const fromLabel = transition.from_state ?? '* Any State';
  const toLabel = transition.to_state;

  return (
    <div className="workflow-modal-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="dry-run-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dry-run-drawer-title"
        onClick={(e) => { e.stopPropagation(); }}
      >
        <div className="dry-run-header">
          <h3 id="dry-run-drawer-title">
            ▶ Dry-Run: [{fromLabel}] ➔ [{toLabel}]
          </h3>
          <div className="dry-run-header-actions">
            <StudioDocLink
              href="/docs/scripted-workflows-and-transition-helpers#dry-run-simulation"
              title="Workflow Dry-Run Documentation"
              testId="dry-run-doc-link"
            />
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-sm"
              onClick={onClose}
              aria-label="Close Dry-Run Drawer"
            >
              ✕ Close
            </button>
          </div>
        </div>

        <div
          className="dry-run-simulation-banner"
          data-testid="dry-run-simulation-banner"
          role="status"
        >
          <span className="dry-run-simulation-icon">🧪</span>
          <strong>DRY-RUN SIMULATION: No database changes were committed.</strong>
        </div>

        {/* Mode switcher tabs */}
        <div className="dry-run-mode-tabs" role="tablist" aria-label="Dry-Run Source">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'sample'}
            className={`dry-run-mode-btn ${mode === 'sample' ? 'is-active' : ''}`}
            onClick={() => { setMode('sample'); }}
          >
            Sample ticket
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'issue'}
            className={`dry-run-mode-btn ${mode === 'issue' ? 'is-active' : ''}`}
            onClick={() => { setMode('issue'); }}
          >
            Pick existing issue
          </button>
        </div>

        {error && (
          <div className="workflow-alert workflow-alert-danger" role="alert">
            {error}
          </div>
        )}

        <form
          onSubmit={(e) => {
            void handleRun(e);
          }}
          className="workflow-dialog-form"
        >
          {mode === 'issue' ? (
            <div className="workflow-form-group">
              <div className="dry-run-label-row">
                <label htmlFor="dry-run-issue-key" className="workflow-form-label">
                  Issue Key
                </label>
                <FieldHelpHint
                  title="Issue Key"
                  summary="Simulates workflow transition execution against an existing issue's live state without committing changes to the database, whereas sample ticket mode executes against an ephemeral synthetic payload."
                  example="KAN-142"
                  docHref="/docs/scripted-workflows-and-transition-helpers#dry-run-simulation"
                  testId="dry-run-issue-key-help"
                />
              </div>
              <input
                id="dry-run-issue-key"
                type="text"
                className="workflow-form-control"
                placeholder="e.g. KAN-142"
                value={issueKey}
                onChange={(e) => { setIssueKey(e.target.value); }}
                required
              />
            </div>
          ) : (
            <>
              <div className="workflow-form-group">
                <label htmlFor="dry-run-summary" className="workflow-form-label">
                  Summary
                </label>
                <input
                  id="dry-run-summary"
                  type="text"
                  className="workflow-form-control"
                  value={summary}
                  onChange={(e) => { setSummary(e.target.value); }}
                  required
                />
              </div>

              <div className="workflow-form-group">
                <label htmlFor="dry-run-desc" className="workflow-form-label">
                  Description Markdown
                </label>
                <textarea
                  id="dry-run-desc"
                  rows={4}
                  className="workflow-form-control"
                  value={description}
                  onChange={(e) => { setDescription(e.target.value); }}
                  required
                />
              </div>

              <div className="workflow-form-group">
                <label htmlFor="dry-run-priority" className="workflow-form-label">
                  Priority
                </label>
                <input
                  id="dry-run-priority"
                  type="text"
                  className="workflow-form-control"
                  value={priority}
                  onChange={(e) => { setPriority(e.target.value); }}
                  required
                />
              </div>

              <div className="workflow-form-group">
                <label htmlFor="dry-run-labels" className="workflow-form-label">
                  Labels (comma-separated)
                </label>
                <input
                  id="dry-run-labels"
                  type="text"
                  className="workflow-form-control"
                  value={labelsStr}
                  onChange={(e) => { setLabelsStr(e.target.value); }}
                />
              </div>
            </>
          )}

          <button
            type="submit"
            className="workflow-btn workflow-btn-primary"
            disabled={isLoading}
          >
            {isLoading ? 'Running Dry-Run...' : '▶ Run Dry-Run'}
          </button>
        </form>

        {/* Results section */}
        {result && (
          <div className="dry-run-results-container" data-testid="dry-run-results">
            {/* would_commit summary banner */}
            <div
              className={`dry-run-summary-banner ${
                result.would_commit ? 'would-commit' : 'blocked'
              }`}
              data-testid="would-commit-banner"
            >
              <span>{result.would_commit ? '✅' : '🛑'}</span>
              <span>
                {result.would_commit
                  ? 'Transition Allowed: Changes would commit'
                  : 'Transition Blocked: Changes would not commit (would_commit: false)'}
              </span>
            </div>

            {/* Ordered steps */}
            {result.steps.map((step) => renderStepResult(step))}
          </div>
        )}
      </aside>
    </div>
  );
}

export function DryRunDrawer({
  isOpen,
  ...innerProps
}: DryRunDrawerProps): JSX.Element | null {
  if (!isOpen) return null;
  return (
    <DryRunDrawerInner
      key={`${innerProps.transition.from_state ?? 'any'}-${innerProps.transition.to_state}`}
      {...innerProps}
    />
  );
}
