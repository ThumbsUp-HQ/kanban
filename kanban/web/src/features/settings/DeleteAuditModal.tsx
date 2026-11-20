/**
 * Pre-Delete Reverse-Audit and Safe Reassignment Modal (KB-P3-AUDIT-23).
 *
 * Inspects blast radius across Issues, Automation Hooks, Pending Executions,
 * and Saved Views before executing State or Label deletions. Enforces
 * safe replacement selection and blocks unmigrated cascading corruption.
 */

import React, { useEffect, useState, type JSX } from 'react';
import { apiFetch } from '../../api/client';
import './DeleteAuditModal.css';

export interface WorkflowHookSummary {
  id: string;
  name: string;
  from_state_id: string;
  to_state_id: string;
  is_enabled?: boolean;
  enabled?: boolean;
}

export interface SavedViewSummary {
  id: string;
  name: string;
}

export interface StateAuditImpactResponse {
  state_id: string;
  state_name: string;
  issues_count: number;
  sample_issue_keys: string[];
  workflow_hooks: WorkflowHookSummary[];
  pending_executions_count: number;
  historical_executions_count: number;
  saved_views: SavedViewSummary[];
  is_default: boolean;
  blocking_reasons: string[];
  valid_replacement_states: {
    id: string;
    name: string;
    group: string;
    color_hex: string;
  }[];
}

export interface LabelAuditImpactResponse {
  label_id: string;
  label_name: string;
  issues_count: number;
  sample_issue_keys: string[];
  saved_views: SavedViewSummary[];
  blocking_reasons: string[];
  valid_replacement_labels: {
    id: string;
    name: string;
    color_hex: string;
  }[];
}

export interface DeleteAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmedDelete: (replacementId?: string, migrateHooks?: boolean) => Promise<void> | void;
  kind: 'state' | 'label';
  item: { id: string; name: string } | null;
  projectKey: string;
}

export function DeleteAuditModal({
  isOpen,
  onClose,
  onConfirmedDelete,
  kind,
  item,
  projectKey,
}: DeleteAuditModalProps): JSX.Element | null {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auditState, setAuditState] = useState<StateAuditImpactResponse | null>(null);
  const [auditLabel, setAuditLabel] = useState<LabelAuditImpactResponse | null>(null);
  const [selectedReplacementId, setSelectedReplacementId] = useState<string>('');
  const [migrateHooks, setMigrateHooks] = useState<boolean>(true);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  const handleClose = () => {
    setAuditState(null);
    setAuditLabel(null);
    setSelectedReplacementId('');
    setMigrateHooks(true);
    setError(null);
    onClose();
  };

  useEffect(() => {
    const targetItem = item;
    if (!isOpen || !targetItem) {
      return;
    }

    let isMounted = true;

    async function loadAudit(): Promise<void> {
      if (!targetItem) return;
      setLoading(true);
      setError(null);
      try {
        const endpoint =
          kind === 'state'
            ? `/api/v1/projects/${encodeURIComponent(projectKey)}/states/${encodeURIComponent(targetItem.id)}/audit-impact`
            : `/api/v1/projects/${encodeURIComponent(projectKey)}/labels/${encodeURIComponent(targetItem.id)}/audit-impact`;

        if (kind === 'state') {
          const res = (await apiFetch('GET', endpoint as never)) as StateAuditImpactResponse;
          if (isMounted) {
            setAuditState(res);
            const firstReplacement = res.valid_replacement_states[0];
            if (firstReplacement) {
              setSelectedReplacementId(firstReplacement.id);
            }
          }
        } else {
          const res = (await apiFetch('GET', endpoint as never)) as LabelAuditImpactResponse;
          if (isMounted) {
            setAuditLabel(res);
            const firstReplacement = res.valid_replacement_labels[0];
            if (firstReplacement) {
              setSelectedReplacementId(firstReplacement.id);
            }
          }
        }
      } catch (err: unknown) {
        if (isMounted) {
          const errObj = err as { message?: string };
          setError(errObj.message ?? 'Failed to compute reverse audit impact.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    void loadAudit();

    return () => {
      isMounted = false;
    };
  }, [isOpen, item, kind, projectKey]);

  if (!isOpen || !item) return null;

  const rawBlocking = auditState?.blocking_reasons ?? auditLabel?.blocking_reasons;
  const blockingReasons = Array.isArray(rawBlocking) ? rawBlocking : [];
  const issuesCount = auditState?.issues_count ?? auditLabel?.issues_count ?? 0;
  const rawSampleKeys = auditState?.sample_issue_keys ?? auditLabel?.sample_issue_keys;
  const sampleKeys = Array.isArray(rawSampleKeys) ? rawSampleKeys : [];
  const rawSavedViews = auditState?.saved_views ?? auditLabel?.saved_views;
  const savedViews = Array.isArray(rawSavedViews) ? rawSavedViews : [];

  // Determine if deletion is permanently blocked
  const hasHardBlock =
    blockingReasons.includes('DEFAULT_STATE') ||
    blockingReasons.includes('LAST_STATE_IN_GROUP') ||
    blockingReasons.includes('TRANSITION_IN_FLIGHT');

  // Check if replacement is required
  const workflowHooks = Array.isArray(auditState?.workflow_hooks) ? auditState.workflow_hooks : [];
  const isHookActive = (h: WorkflowHookSummary): boolean =>
    h.is_enabled ?? Boolean(h.enabled);
  const enabledHooksCount = workflowHooks.filter(isHookActive).length;
  const historicalExecCount = auditState?.historical_executions_count ?? 0;
  const requiresReplacement =
    issuesCount > 0 || enabledHooksCount > 0 || historicalExecCount > 0;

  const isConfirmDisabled =
    loading ||
    isDeleting ||
    hasHardBlock ||
    (requiresReplacement && !selectedReplacementId);

  const handleConfirm = async () => {
    setIsDeleting(true);
    setError(null);
    try {
      await onConfirmedDelete(
        selectedReplacementId || undefined,
        kind === 'state' ? migrateHooks : undefined
      );
      handleClose();
    } catch (err: unknown) {
      const errObj = err as { message?: string };
      setError(errObj.message ?? 'Failed to delete item.');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="kb-modal-backdrop" role="dialog" aria-modal="true" data-testid="delete-audit-modal">
      <div className="kb-modal-dialog">
        <div className="kb-modal-header">
          <h2 className="kb-modal-title">
            Delete {kind === 'state' ? 'Workflow State' : 'Label'}: {item.name}
          </h2>
          <button
            type="button"
            className="kb-modal-close-btn"
            data-testid="audit-close-x-btn"
            onClick={handleClose}
            disabled={isDeleting}
            aria-label="Close"
          >
            x
          </button>
        </div>

        <div className="kb-modal-body">
          {error && (
            <div className="kb-audit-error-banner" data-testid="audit-error-message">
              {error}
            </div>
          )}

          {loading ? (
            <div className="kb-audit-loading" data-testid="audit-loading">
              Analyzing blast radius and audit dependencies...
            </div>
          ) : (
            <>
              {/* Blocking Reasons Banner */}
              {blockingReasons.length > 0 && (
                <div className="kb-audit-blocking-banner" data-testid="audit-blocking-reasons">
                  <strong>Deletion Blocked:</strong>
                  <ul className="kb-audit-blocking-list">
                    {blockingReasons.map((reason) => {
                      let description = reason;
                      if (reason === 'DEFAULT_STATE') {
                        description = 'Cannot delete the default state. Set another default state first.';
                      } else if (reason === 'LAST_STATE_IN_GROUP') {
                        description = 'Cannot delete the only state in this workflow group.';
                      } else if (reason === 'TRANSITION_IN_FLIGHT') {
                        description = 'Transitions are currently in flight for this state. Wait for executions to finish.';
                      } else if (reason === 'ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE') {
                        description = 'Enabled automation hooks reference this state. Reassignment is required.';
                      }
                      return <li key={reason}>{description}</li>;
                    })}
                  </ul>
                </div>
              )}

              {/* Blast Radius Grid */}
              <div className="kb-audit-grid">
                <div className="kb-audit-card">
                  <span className="kb-audit-card-label">Affected Issues</span>
                  <span className="kb-audit-card-value" data-testid="audit-issues-count">
                    {issuesCount}
                  </span>
                  {sampleKeys.length > 0 && (
                    <span className="kb-audit-sample-keys" data-testid="audit-sample-keys">
                      Samples: {sampleKeys.slice(0, 5).join(', ')}
                    </span>
                  )}
                </div>

                {kind === 'state' && auditState && (
                  <>
                    <div className="kb-audit-card">
                      <span className="kb-audit-card-label">Automation Hooks</span>
                      <span className="kb-audit-card-value" data-testid="audit-hooks-count">
                        {workflowHooks.length}
                      </span>
                      {enabledHooksCount > 0 && (
                        <span className="kb-audit-hook-notice">
                          {enabledHooksCount} active hook(s) require migration
                        </span>
                      )}
                    </div>

                    <div className="kb-audit-card">
                      <span className="kb-audit-card-label">In-Flight Executions</span>
                      <span className="kb-audit-card-value" data-testid="audit-pending-count">
                        {auditState.pending_executions_count}
                      </span>
                    </div>

                    <div className="kb-audit-card">
                      <span className="kb-audit-card-label">Historical Executions</span>
                      <span className="kb-audit-card-value" data-testid="audit-historical-count">
                        {auditState.historical_executions_count}
                      </span>
                    </div>
                  </>
                )}

                <div className="kb-audit-card">
                  <span className="kb-audit-card-label">Saved Views</span>
                  <span className="kb-audit-card-value" data-testid="audit-views-count">
                    {savedViews.length}
                  </span>
                </div>
              </div>

              {/* Active Automation Hooks List */}
              {kind === 'state' && workflowHooks.length > 0 && (
                <div className="kb-audit-section" data-testid="audit-hooks-list">
                  <h4 className="kb-audit-section-title">Associated Automation Hooks:</h4>
                  <ul className="kb-audit-items-list">
                    {workflowHooks.map((h) => (
                      <li key={h.id}>
                        {h.name} {isHookActive(h) ? '(Enabled)' : '(Disabled)'}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Saved Views List */}
              {savedViews.length > 0 && (
                <div className="kb-audit-section" data-testid="audit-views-list">
                  <h4 className="kb-audit-section-title">Filtered Saved Views:</h4>
                  <ul className="kb-audit-items-list">
                    {savedViews.map((v) => (
                      <li key={v.id}>{v.name}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Reassignment Form */}
              <div className="kb-audit-reassign-form">
                <label htmlFor="audit-replacement-select" className="kb-audit-section-title">
                  Reassign affected items to:
                </label>
                <select
                  id="audit-replacement-select"
                  data-testid="audit-replacement-select"
                  className="kb-select"
                  value={selectedReplacementId}
                  onChange={(e) => {
                    setSelectedReplacementId(e.target.value);
                  }}
                  disabled={isDeleting}
                >
                  {!requiresReplacement && (
                    <option value="">None (Delete without reassignment)</option>
                  )}
                  {kind === 'state' &&
                    Array.isArray(auditState?.valid_replacement_states) &&
                    auditState.valid_replacement_states.map((st) => (
                      <option key={st.id} value={st.id}>
                        {st.name} ({st.group})
                      </option>
                    ))}
                  {kind === 'label' &&
                    Array.isArray(auditLabel?.valid_replacement_labels) &&
                    auditLabel.valid_replacement_labels.map((lbl) => (
                      <option key={lbl.id} value={lbl.id}>
                        {lbl.name}
                      </option>
                    ))}
                </select>

                {kind === 'state' && workflowHooks.length > 0 && (
                  <label className="kb-checkbox-label">
                    <input
                      type="checkbox"
                      data-testid="audit-migrate-hooks-checkbox"
                      checked={migrateHooks}
                      onChange={(e) => {
                        setMigrateHooks(e.target.checked);
                      }}
                      disabled={isDeleting}
                    />
                    <span>Migrate workflow automation hooks to selected replacement</span>
                  </label>
                )}
              </div>
            </>
          )}
        </div>

        <div className="kb-modal-footer">
          <button
            type="button"
            className="kb-btn kb-btn-secondary"
            data-testid="audit-cancel-btn"
            onClick={handleClose}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="kb-btn kb-btn-danger"
            data-testid="audit-confirm-delete-btn"
            onClick={() => {
              void handleConfirm();
            }}
            disabled={isConfirmDisabled}
          >
            {isDeleting ? 'Deleting...' : 'Confirm Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
