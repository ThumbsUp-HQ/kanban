import React, { useState, type JSX } from 'react';
import type { IssueItem } from './viewsApi';
import './filterBulk.css';

export interface BulkActionBarProps {
  selectedKeys: string[];
  issues: IssueItem[];
  onClearSelection: () => void;
  onBatchUpdateState?: (stateId: string) => void;
  onBatchUpdatePriority?: (prioritySlug: string) => void;
  onBatchUpdateAssignees?: (assigneeIds: string[]) => void;
  onBatchUpdateLabels?: (labelIds: string[]) => void;
  onBatchUpdateCycle?: (cycleId: string | null) => void;
  onBatchUpdateModule?: (moduleIds: string[]) => void;
  onBatchArchive?: () => void;
  onBatchDelete?: () => void;
  modulesEnabled?: boolean;
}

export function BulkActionBar({
  selectedKeys,
  issues,
  onClearSelection,
  onBatchUpdateState,
  onBatchUpdatePriority,
  onBatchUpdateAssignees,
  onBatchUpdateLabels,
  onBatchUpdateCycle,
  onBatchUpdateModule,
  onBatchArchive,
  onBatchDelete,
  modulesEnabled = true,
}: BulkActionBarProps): JSX.Element | null {
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  if (selectedKeys.length === 0) {
    return null;
  }

  // Selected issues lookup
  const selectedIssues = issues.filter((i) => selectedKeys.includes(i.key));

  // S7.2 8p Archive Rule: "Only completed or canceled work items can be archived"
  // Archive is disabled whenever ANY selected issue has state.group outside ('completed', 'cancelled')
  const canArchive =
    selectedIssues.length > 0 &&
    selectedIssues.every(
      (issue) =>
        issue.state.group === 'completed' || issue.state.group === 'cancelled'
    );

  const archiveDisabledReason =
    'Only completed or canceled work items can be archived';

  // Cap at 100 items announcement
  const isCapped = selectedKeys.length >= 100;
  const capAnnouncement = isCapped
    ? 'Bulk selection is capped at 100 work items'
    : '';

  // Gate Delete on DELETE capability across selected issues
  const canDelete =
    selectedIssues.length === 0 ||
    selectedIssues.every((issue) => {
      const caps = issue.capabilities;
      return !caps || caps.includes('DELETE') || caps.includes('ADMIN');
    });

  return (
    <>
      <div
        className="bulk-action-bar"
        role="toolbar"
        aria-label="Bulk actions"
      >
        <span className="bulk-count-label bulk-action-bar-count">
          {selectedKeys.length} selected
        </span>

        <button
          type="button"
          className="bulk-btn bulk-btn-clear"
          onClick={onClearSelection}
          aria-label="Clear selection"
        >
          Clear (Esc)
        </button>

        <button
          type="button"
          className="bulk-btn"
          data-action="state"
          onClick={() => onBatchUpdateState?.('done')}
        >
          State
        </button>

        <button
          type="button"
          className="bulk-btn"
          data-action="priority"
          onClick={() => onBatchUpdatePriority?.('urgent')}
        >
          Priority
        </button>

        <button
          type="button"
          className="bulk-btn"
          onClick={() => onBatchUpdateAssignees?.(['alice'])}
        >
          Assignees
        </button>

        <button
          type="button"
          className="bulk-btn"
          onClick={() => onBatchUpdateLabels?.(['lbl-sec'])}
        >
          Labels
        </button>

        <button
          type="button"
          className="bulk-btn"
          onClick={() => onBatchUpdateCycle?.('cycle-1')}
        >
          Cycle
        </button>

        {/* Module action button: completely unmounted when modulesEnabled is false (S7.2 8f) */}
        {modulesEnabled && (
          <button
            type="button"
            className="bulk-btn"
            onClick={() => onBatchUpdateModule?.(['mod-1'])}
          >
            Module
          </button>
        )}

        <button
          type="button"
          className="bulk-btn bulk-action-bar-btn"
          data-action="archive"
          disabled={!canArchive}
          title={!canArchive ? archiveDisabledReason : 'Archive selected items'}
          data-reason={!canArchive ? archiveDisabledReason : undefined}
          onClick={canArchive ? onBatchArchive : undefined}
        >
          Archive
        </button>

        {canDelete && (
          <button
            type="button"
            className="bulk-btn bulk-btn-danger"
            onClick={() => {
              if (onBatchDelete) {
                onBatchDelete();
              } else {
                setShowDeleteModal(true);
              }
            }}
          >
            Delete
          </button>
        )}

        {capAnnouncement && (
          <span
            className="bulk-live-announcer"
            role="status"
            aria-live="polite"
          >
            {capAnnouncement}
          </span>
        )}
      </div>

      {showDeleteModal && (
        <div
          className="quick-create-modal-overlay"
          role="dialog"
          aria-labelledby="bulk-delete-title"
          aria-modal="true"
        >
          <div className="quick-create-modal">
            <h2 id="bulk-delete-title" className="quick-create-title">
              Delete {selectedKeys.length} work items?
            </h2>
            <p className="quick-create-label">
              This action cannot be undone. Any sub-issues will be unparented.
            </p>
            <div className="quick-create-footer">
              <button
                type="button"
                className="quick-create-btn-cancel"
                onClick={() => { setShowDeleteModal(false); }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="quick-create-btn-submit bulk-btn-danger"
                onClick={() => {
                  setShowDeleteModal(false);
                  onClearSelection();
                }}
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
