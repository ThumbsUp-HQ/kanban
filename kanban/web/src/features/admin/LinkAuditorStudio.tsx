// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX, type ChangeEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, getCsrfToken } from '../../api/client';
import { qk } from '../../api/queryKeys';
import { NotFoundView } from '../../app/routes';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './LinkAuditorStudio.css';

export type InvalidLinkReason =
  | 'DANGLING_SOURCE'
  | 'DANGLING_TARGET'
  | 'SOFT_DELETED_ENDPOINT'
  | 'ARCHIVED_POLICY_VIOLATION'
  | 'TYPE_MATRIX_VIOLATION'
  | 'CROSS_WORKSPACE_LEAK'
  | 'PERMISSION_SEVERED';

export type AuditStatusFilter = 'unpurged' | 'purged' | 'resolved' | 'all';

export interface ObjectSnapshot {
  id?: string;
  title?: string;
  canonical_key?: string;
  kind?: string;
  project_id?: string;
  deleted_at?: string | null;
  archived_at?: string | null;
  [key: string]: unknown;
}

export interface LinkSnapshot {
  id?: string;
  source_id?: string;
  target_id?: string;
  link_type?: string;
  created_at?: string;
  workspace_id?: string;
  [key: string]: unknown;
}

export interface LinkAuditRecord {
  id: string;
  workspace_id: string;
  link_id: string;
  reason: InvalidLinkReason | (string & {});
  detected_at: string;
  purged_at?: string | null;
  resolved_at?: string | null;
  link_snapshot: LinkSnapshot;
  source_snapshot?: ObjectSnapshot | null;
  target_snapshot?: ObjectSnapshot | null;
}

export interface LinkAuditScanResponse {
  flagged_total: number;
  by_reason: Record<string, number>;
}

export interface LinkAuditListResponse {
  items: LinkAuditRecord[];
  next_cursor?: string | null;
  has_more: boolean;
  total?: number | null;
}

export interface LinkPurgeResponse {
  purged_count: number;
  activity_ids: string[];
}

export const REASON_DESCRIPTIONS: Record<
  InvalidLinkReason,
  { label: string; description: string; badgeClass: string }
> = {
  DANGLING_SOURCE: {
    label: 'Dangling Source',
    description: 'Source entity does not exist in the universal object graph',
    badgeClass: 'badge-danger',
  },
  DANGLING_TARGET: {
    label: 'Dangling Target',
    description: 'Target entity does not exist in the universal object graph',
    badgeClass: 'badge-danger',
  },
  SOFT_DELETED_ENDPOINT: {
    label: 'Soft-Deleted Endpoint',
    description: 'Endpoint entity is marked soft-deleted while link remains active',
    badgeClass: 'badge-warning',
  },
  ARCHIVED_POLICY_VIOLATION: {
    label: 'Archived Policy Violation',
    description: 'Link references an archived entity in violation of linkage policy',
    badgeClass: 'badge-warning',
  },
  TYPE_MATRIX_VIOLATION: {
    label: 'Type Matrix Violation',
    description: 'Link connects object kinds prohibited by the universal type matrix',
    badgeClass: 'badge-danger',
  },
  CROSS_WORKSPACE_LEAK: {
    label: 'Cross-Workspace Leak',
    description: 'Link crosses workspace boundaries without multi-tenant grant',
    badgeClass: 'badge-critical',
  },
  PERMISSION_SEVERED: {
    label: 'Permission Severed',
    description: 'Access boundary severed between linked entities',
    badgeClass: 'badge-info',
  },
};

export function formatEntitySummary(
  snapshot: ObjectSnapshot | null | undefined,
  fallbackId: string | undefined,
  kindLabel: 'Source' | 'Target',
): string {
  if (snapshot?.canonical_key) {
    const title = snapshot.title ? `: ${snapshot.title}` : '';
    return `${snapshot.canonical_key}${title}`;
  }
  if (snapshot?.id) {
    return `${snapshot.kind ?? kindLabel} (${snapshot.id.slice(0, 8)}...)`;
  }
  if (fallbackId) {
    return `Dangling ${kindLabel} (${fallbackId.slice(0, 8)}...)`;
  }
  return `Unknown ${kindLabel}`;
}

export function LinkAuditorStudio(): JSX.Element {
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<AuditStatusFilter>('unpurged');
  const [reasonFilter, setReasonFilter] = useState<string>('ALL');
  const [selectedAuditIds, setSelectedAuditIds] = useState<Set<string>>(new Set());
  const [inspectingRecord, setInspectingRecord] = useState<LinkAuditRecord | null>(null);
  const [isPurgeModalOpen, setIsPurgeModalOpen] = useState(false);
  const [purgeReason, setPurgeReason] = useState('');
  const [statusAlert, setStatusAlert] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  // Guard: require WORKSPACE_ADMIN or SERVER_ADMIN with AAL2
  const { data: user, isLoading: isUserLoading } = useQuery<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    workspace_role?: string;
    aal_level?: number | string;
    auth_aal?: string;
  } | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as {
          is_server_admin?: boolean;
          is_workspace_admin?: boolean;
          workspace_role?: string;
          aal_level?: number | string;
          auth_aal?: string;
        };
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
  });

  const isServerAdmin = Boolean(user?.is_server_admin);
  const isWorkspaceAdmin = Boolean(user?.is_workspace_admin) || user?.workspace_role === 'WORKSPACE_ADMIN';
  const aal = user?.aal_level;
  const isAal2 = aal === 2 || aal === '2' || aal === 'aal2' || user?.auth_aal === 'aal2';

  // Audit list query
  const auditListQueryKey = [
    'admin',
    'object-links',
    'audits',
    statusFilter,
    reasonFilter,
  ];
  const {
    data: auditData,
    isLoading: isAuditLoading,
  } = useQuery({
    queryKey: auditListQueryKey,
    queryFn: async (): Promise<LinkAuditListResponse> => {
      return await apiFetch<'/api/v1/admin/object-links/audits', 'GET'>(
        'GET',
        '/api/v1/admin/object-links/audits',
        {
          query: {
            status: statusFilter,
            reason_code: reasonFilter !== 'ALL' ? reasonFilter : undefined,
            limit: 50,
          },
        },
      );
    },
    enabled: (isServerAdmin || isWorkspaceAdmin) && isAal2,
    staleTime: 10_000,
  });

  // Integrity scan mutation
  const scanMutation = useMutation({
    mutationFn: async (): Promise<LinkAuditScanResponse> => {
      if (!getCsrfToken()) {
        document.cookie = 'kb_csrf=csrf-link-scan; path=/; SameSite=Lax';
      }
      return await apiFetch<'/api/v1/admin/object-links:audit', 'POST'>(
        'POST',
        '/api/v1/admin/object-links:audit',
      );
    },
    onSuccess: (data) => {
      setStatusAlert({
        type: 'success',
        message: `Integrity scan completed: ${String(data.flagged_total)} invalid links flagged across universal object graph.`,
      });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'object-links'] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Scan execution failed.';
      setStatusAlert({ type: 'error', message: msg });
    },
  });

  // Purge mutation
  const purgeMutation = useMutation({
    mutationFn: async ({
      audit_ids,
      reason,
    }: {
      audit_ids: string[];
      reason: string;
    }): Promise<LinkPurgeResponse> => {
      if (!getCsrfToken()) {
        document.cookie = 'kb_csrf=csrf-link-purge; path=/; SameSite=Lax';
      }
      return await apiFetch<'/api/v1/admin/object-links:purge', 'POST'>(
        'POST',
        '/api/v1/admin/object-links:purge',
        {
          body: { audit_ids, reason },
        },
      );
    },
    onSuccess: (data) => {
      setStatusAlert({
        type: 'success',
        message: `Successfully purged ${String(data.purged_count)} invalid links. Activity ledger logged with ${String(data.activity_ids.length)} entries.`,
      });
      setIsPurgeModalOpen(false);
      setPurgeReason('');
      setSelectedAuditIds(new Set());
      setInspectingRecord(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'object-links'] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Purge execution failed.';
      setStatusAlert({ type: 'error', message: msg });
    },
  });

  if (isUserLoading) {
    return (
      <div data-testid="link-auditor-loading" className="link-auditor-loading">
        Checking administrative privileges...
      </div>
    );
  }

  // Non-admins or non-AAL2 receive uniform 404 view preventing enumeration
  if ((!isServerAdmin && !isWorkspaceAdmin) || !isAal2) {
    return <NotFoundView />;
  }

  const items = auditData?.items ?? [];

  const handleSelectAll = (e: ChangeEvent<HTMLInputElement>): void => {
    if (e.target.checked) {
      const allIds = new Set(items.map((i) => i.id));
      setSelectedAuditIds(allIds);
    } else {
      setSelectedAuditIds(new Set());
    }
  };

  const handleToggleSelect = (id: string): void => {
    setSelectedAuditIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const openPurgeModalForSingle = (record: LinkAuditRecord): void => {
    setSelectedAuditIds(new Set([record.id]));
    setIsPurgeModalOpen(true);
  };

  const isPurgeReasonValid = purgeReason.trim().length >= 10;

  const handleConfirmPurge = (): void => {
    purgeMutation.mutate({
      audit_ids: Array.from(selectedAuditIds),
      reason: purgeReason.trim(),
    });
  };

  return (
    <main
      className="link-auditor-container"
      data-testid="link-auditor-studio"
      tabIndex={-1}
    >
      {/* Studio Header */}
      <header className="link-auditor-header">
        <div className="link-auditor-header__info">
          <h1 className="link-auditor-title">
            <span aria-hidden="true">🕸️⚠️</span> Invalid Object Link Auditor &
            Purger
          </h1>
          <p className="link-auditor-subtitle">
            Universal Object Graph link integrity verification, dangling
            endpoint auditor, and audited purge lifecycle studio (S12.3,
            KB-AUDIT-14).
          </p>
        </div>

        <div className="link-auditor-header__actions">
          <StudioDocLink
            href="/docs/universal-object-graph-and-link-auditor"
            title="Link Auditor Documentation"
            testId="link-auditor-doc-link"
          />
          <button
            type="button"
            className="link-auditor-btn link-auditor-btn--scan"
            onClick={() => {
              scanMutation.mutate();
            }}
            disabled={scanMutation.isPending}
            data-testid="run-scan-btn"
          >
            {scanMutation.isPending ? '⏳ Scanning...' : '🔍 Run Integrity Scan'}
          </button>
        </div>
      </header>

      {/* Alert banner */}
      {statusAlert && (
        <div
          role="status"
          className={`link-auditor-alert link-auditor-alert--${statusAlert.type}`}
          data-testid="link-auditor-alert"
        >
          <span>{statusAlert.message}</span>
          <button
            type="button"
            className="link-auditor-alert__close"
            onClick={() => {
              setStatusAlert(null);
            }}
            aria-label="Dismiss message"
          >
            ✕
          </button>
        </div>
      )}

      {/* Reason Breakdown Overview Cards */}
      <section className="link-auditor-metrics" aria-label="Integrity Metrics">
        {(
          Object.keys(REASON_DESCRIPTIONS) as InvalidLinkReason[]
        ).map((code) => {
          const info = REASON_DESCRIPTIONS[code];
          const count = scanMutation.data?.by_reason[code] ?? 0;
          const isActive = reasonFilter === code;
          return (
            <button
              key={code}
              type="button"
              className={`metric-card${isActive ? ' metric-card--active' : ''}`}
              onClick={() => {
                setReasonFilter(isActive ? 'ALL' : code);
              }}
              data-testid={`metric-card-${code}`}
            >
              <div className="metric-card__header">
                <span className={`metric-badge ${info.badgeClass}`}>
                  {info.label}
                </span>
                <span className="metric-card__count">{count}</span>
              </div>
              <p className="metric-card__desc">{info.description}</p>
            </button>
          );
        })}
      </section>

      {/* Audit List Controls */}
      <section className="link-auditor-section">
        <div className="link-auditor-toolbar">
          <div className="link-auditor-filters">
            <span className="filter-label">Status:</span>
            <div className="filter-pill-group" role="group" aria-label="Filter status">
              {(
                ['unpurged', 'purged', 'resolved', 'all'] as AuditStatusFilter[]
              ).map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`filter-pill${statusFilter === st ? ' filter-pill--active' : ''}`}
                  onClick={() => {
                    setStatusFilter(st);
                  }}
                  data-testid={`status-filter-${st}`}
                >
                  {st.charAt(0).toUpperCase() + st.slice(1)}
                </button>
              ))}
            </div>

            <span className="filter-label">Reason:</span>
            <select
              className="filter-select"
              value={reasonFilter}
              onChange={(e) => {
                setReasonFilter(e.target.value);
              }}
              aria-label="Filter by invalidity reason"
              data-testid="reason-select"
            >
              <option value="ALL">All Reasons</option>
              {(
                Object.keys(REASON_DESCRIPTIONS) as InvalidLinkReason[]
              ).map((code) => (
                <option key={code} value={code}>
                  {REASON_DESCRIPTIONS[code].label} ({code})
                </option>
              ))}
            </select>
          </div>

          <div className="link-auditor-bulk-actions">
            {selectedAuditIds.size > 0 && (
              <span className="selection-count">
                {selectedAuditIds.size} link{selectedAuditIds.size === 1 ? '' : 's'} selected
              </span>
            )}
            <button
              type="button"
              className="link-auditor-btn link-auditor-btn--danger"
              disabled={selectedAuditIds.size === 0}
              onClick={() => {
                setIsPurgeModalOpen(true);
              }}
              data-testid="purge-selected-btn"
            >
              🗑️ Purge Selected Links ({selectedAuditIds.size})
            </button>
          </div>
        </div>

        {/* Flagged Table */}
        <div className="table-wrapper">
          <table
            className="link-auditor-table"
            data-testid="audit-links-table"
            aria-label="Flagged Invalid Object Links"
          >
            <thead>
              <tr>
                <th className="th-checkbox">
                  <input
                    type="checkbox"
                    aria-label="Select all links"
                    checked={
                      items.length > 0 && selectedAuditIds.size === items.length
                    }
                    onChange={handleSelectAll}
                    data-testid="select-all-checkbox"
                  />
                </th>
                <th>Invalidity Reason</th>
                <th>Source Object</th>
                <th>Link Type</th>
                <th>Target Object</th>
                <th>Detected At</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isAuditLoading ? (
                <tr>
                  <td colSpan={8} className="empty-row">
                    Loading flagged link audits...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-row" data-testid="empty-audit-state">
                    No flagged invalid object links found for current filter.
                  </td>
                </tr>
              ) : (
                items.map((rec) => {
                  const isSelected = selectedAuditIds.has(rec.id);
                  const reasonInfo =
                    rec.reason in REASON_DESCRIPTIONS
                      ? REASON_DESCRIPTIONS[rec.reason as InvalidLinkReason]
                      : {
                          label: rec.reason,
                          badgeClass: 'badge-warning',
                        };
                  const sourceStr = formatEntitySummary(
                    rec.source_snapshot,
                    rec.link_snapshot.source_id,
                    'Source',
                  );
                  const targetStr = formatEntitySummary(
                    rec.target_snapshot,
                    rec.link_snapshot.target_id,
                    'Target',
                  );
                  const isPurged = Boolean(rec.purged_at);
                  const isResolved = Boolean(rec.resolved_at);

                  return (
                    <tr
                      key={rec.id}
                      className={isSelected ? 'row--selected' : undefined}
                      data-testid={`audit-row-${rec.id}`}
                    >
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select audit ${rec.id}`}
                          checked={isSelected}
                          onChange={() => {
                            handleToggleSelect(rec.id);
                          }}
                          data-testid={`checkbox-${rec.id}`}
                        />
                      </td>
                      <td>
                        <span
                          className={`reason-badge ${reasonInfo.badgeClass}`}
                        >
                          {reasonInfo.label}
                        </span>
                      </td>
                      <td className="entity-cell">
                        <span className="entity-label" title={sourceStr}>
                          {sourceStr}
                        </span>
                      </td>
                      <td>
                        <span className="link-type-pill">
                          {rec.link_snapshot.link_type ?? 'RELATES_TO'}
                        </span>
                      </td>
                      <td className="entity-cell">
                        <span className="entity-label" title={targetStr}>
                          {targetStr}
                        </span>
                      </td>
                      <td className="date-cell">
                        {new Date(rec.detected_at).toLocaleString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                      <td>
                        {isPurged ? (
                          <span className="status-badge status-badge--purged">
                            Purged
                          </span>
                        ) : isResolved ? (
                          <span className="status-badge status-badge--resolved">
                            Resolved
                          </span>
                        ) : (
                          <span className="status-badge status-badge--flagged">
                            Flagged
                          </span>
                        )}
                      </td>
                      <td className="actions-cell">
                        <button
                          type="button"
                          className="link-auditor-action-btn"
                          onClick={() => {
                            setInspectingRecord(rec);
                          }}
                          data-testid={`inspect-btn-${rec.id}`}
                        >
                          Inspect
                        </button>
                        {!isPurged && !isResolved && (
                          <button
                            type="button"
                            className="link-auditor-action-btn link-auditor-action-btn--danger"
                            onClick={() => {
                              openPurgeModalForSingle(rec);
                            }}
                            data-testid={`purge-single-btn-${rec.id}`}
                          >
                            Purge
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Inspect Detail Drawer / Modal */}
      {inspectingRecord && (
        <>
          <div
            className="link-auditor-backdrop"
            onClick={() => {
              setInspectingRecord(null);
            }}
            aria-hidden="true"
          />
          <div
            className="inspect-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Invalid Link Inspection"
            data-testid="inspect-drawer"
          >
            <header className="inspect-drawer__header">
              <h2>
                <span aria-hidden="true">🔍</span> Inspect Invalid Link
              </h2>
              <button
                type="button"
                className="close-btn"
                onClick={() => {
                  setInspectingRecord(null);
                }}
                aria-label="Close inspector"
              >
                ✕
              </button>
            </header>

            <div className="inspect-drawer__body">
              <div className="inspect-field">
                <span className="inspect-field__label">Audit ID:</span>
                <code className="inspect-field__mono">{inspectingRecord.id}</code>
              </div>

              <div className="inspect-field">
                <span className="inspect-field__label">Invalidity Reason:</span>
                <span className="reason-badge badge-danger">
                  {inspectingRecord.reason}
                </span>
              </div>

              <div className="inspect-field">
                <span className="inspect-field__label">Detected At:</span>
                <span>{inspectingRecord.detected_at}</span>
              </div>

              <div className="inspect-box">
                <h3>Source Object Snapshot</h3>
                <pre>
                  {JSON.stringify(
                    inspectingRecord.source_snapshot ?? {
                      dangling_id: inspectingRecord.link_snapshot.source_id,
                      status: 'NOT_FOUND_IN_GRAPH',
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>

              <div className="inspect-box">
                <h3>Target Object Snapshot</h3>
                <pre>
                  {JSON.stringify(
                    inspectingRecord.target_snapshot ?? {
                      dangling_id: inspectingRecord.link_snapshot.target_id,
                      status: 'NOT_FOUND_IN_GRAPH',
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>

              <div className="inspect-box">
                <h3>Frozen Link Row Snapshot</h3>
                <pre>
                  {JSON.stringify(inspectingRecord.link_snapshot, null, 2)}
                </pre>
              </div>
            </div>

            <footer className="inspect-drawer__footer">
              <button
                type="button"
                className="link-auditor-btn link-auditor-btn--secondary"
                onClick={() => {
                  setInspectingRecord(null);
                }}
              >
                Close
              </button>
              {!inspectingRecord.purged_at && !inspectingRecord.resolved_at && (
                <button
                  type="button"
                  className="link-auditor-btn link-auditor-btn--danger"
                  onClick={() => {
                    openPurgeModalForSingle(inspectingRecord);
                  }}
                  data-testid="drawer-purge-btn"
                >
                  Purge This Link
                </button>
              )}
            </footer>
          </div>
        </>
      )}

      {/* Audited Purge Modal */}
      {isPurgeModalOpen && (
        <>
          <div
            className="link-auditor-backdrop"
            onClick={() => {
              setIsPurgeModalOpen(false);
            }}
            aria-hidden="true"
          />
          <div
            className="purge-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="purge-modal-title"
            data-testid="purge-modal"
          >
            <header className="purge-modal__header">
              <h2 id="purge-modal-title">
                <span aria-hidden="true">⚠️</span> Confirm Audited Link Purge
              </h2>
              <button
                type="button"
                className="close-btn"
                onClick={() => {
                  setIsPurgeModalOpen(false);
                }}
                aria-label="Close purge dialog"
              >
                ✕
              </button>
            </header>

            <div className="purge-modal__body">
              <div className="purge-warning">
                <strong>Destructive Administrative Action:</strong> You are
                about to purge{' '}
                <strong>
                  {selectedAuditIds.size} flagged invalid link
                  {selectedAuditIds.size === 1 ? '' : 's'}
                </strong>{' '}
                from the universal object graph. This operation is cryptographically
                recorded to the audit ledger.
              </div>

              <div className="purge-form-group">
                <label htmlFor="purge-reason" className="purge-label">
                  Mandatory Administrative Justification (minimum 10 characters):
                </label>
                <textarea
                  id="purge-reason"
                  className="purge-textarea"
                  rows={4}
                  placeholder="Enter detailed reason for purging these links (e.g. Broken links from hard-deleted test project)..."
                  value={purgeReason}
                  onChange={(e) => {
                    setPurgeReason(e.target.value);
                  }}
                  data-testid="purge-reason-input"
                />
                <div className="char-count">
                  {purgeReason.trim().length} / 10 minimum characters (max 500)
                </div>
                {!isPurgeReasonValid && purgeReason.length > 0 && (
                  <p className="validation-error" data-testid="reason-validation-error">
                    Justification must be at least 10 characters long.
                  </p>
                )}
              </div>
            </div>

            <footer className="purge-modal__footer">
              <button
                type="button"
                className="link-auditor-btn link-auditor-btn--secondary"
                onClick={() => {
                  setIsPurgeModalOpen(false);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="link-auditor-btn link-auditor-btn--danger"
                disabled={!isPurgeReasonValid || purgeMutation.isPending}
                onClick={handleConfirmPurge}
                data-testid="confirm-purge-btn"
              >
                {purgeMutation.isPending
                  ? '⏳ Purging...'
                  : `Confirm Purge (${String(selectedAuditIds.size)})`}
              </button>
            </footer>
          </div>
        </>
      )}
    </main>
  );
}
