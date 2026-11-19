/**
 * Save As View Modal Dialog (KANBA-221, S6.4, S3.4).
 * Captures custom layout, group-by, sub-group-by, and filter spec, persisting to POST /api/v1/projects/:key/views.
 */

import React, { useState, useEffect, useRef, type JSX, type SyntheticEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { qk } from '../../api/queryKeys';
import type { ViewLayout } from './viewRegistry';
import type { ActiveFilters } from './FilterDisplayBar';
import './SaveViewModal.css';

export interface SaveViewModalFilterState {
  stateIds?: string[] | undefined;
  priorityIds?: string[] | undefined;
  assigneeIds?: string[] | undefined;
  cycleIds?: string[] | undefined;
  moduleIds?: string[] | undefined;
  searchQuery?: string | null | undefined;
  state?: string[] | undefined;
  priority?: string[] | undefined;
  assignee?: string[] | undefined;
  cycle?: string[] | undefined;
  module?: string[] | undefined;
}

export interface SaveViewModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectKey: string;
  layout: ViewLayout | (string & {});
  groupBy?: string | undefined;
  subGroupBy?: string | undefined;
  activeFilters: SaveViewModalFilterState | ActiveFilters;
  onSaved?: ((viewId: string) => void) | undefined;
}

export function SaveViewModal({
  isOpen,
  onClose,
  projectKey,
  layout,
  groupBy,
  subGroupBy,
  activeFilters,
  onSaved,
}: SaveViewModalProps): JSX.Element | null {
  const [prevIsOpen, setPrevIsOpen] = useState(isOpen);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isShared, setIsShared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  if (isOpen !== prevIsOpen) {
    setPrevIsOpen(isOpen);
    if (isOpen) {
      setName('');
      setDescription('');
      setIsShared(false);
      setError(null);
    }
  }

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isOpen]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: name.trim(),
        description_markdown: description.trim(),
        layout,
        group_by: groupBy && groupBy !== 'none' ? groupBy : null,
        sub_group_by: subGroupBy && subGroupBy !== 'none' ? subGroupBy : null,
        filters: {
          state_ids: activeFilters.stateIds,
          priority_ids: activeFilters.priorityIds,
          assignee_ids: activeFilters.assigneeIds,
          cycle_ids: activeFilters.cycleIds,
          module_ids: activeFilters.moduleIds,
          search_query: typeof activeFilters.searchQuery === 'string' ? activeFilters.searchQuery.trim() : null,
        },
        is_shared: isShared,
      };

      const res = (await apiFetch(
        'POST',
        `/api/v1/projects/${encodeURIComponent(projectKey)}/views` as never,
        { body: payload },
      )) as { id: string };
      return res;
    },
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: qk.savedViews(projectKey) });
      onSaved?.(res.id);
      onClose();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : 'Failed to save view');
    },
  });

  if (!isOpen) return null;

  const handleSubmit = (e: SyntheticEvent): void => {
    e.preventDefault();
    if (!name.trim()) {
      setError('View name is required');
      return;
    }
    saveMutation.mutate();
  };

  return (
    <div
      className="kb-save-view-backdrop"
      data-testid="save-view-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="kb-save-view-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-view-title"
        data-testid="save-view-modal"
      >
        <header className="kb-save-view-header">
          <h2 id="save-view-title" className="kb-save-view-heading">
            Save as view
          </h2>
          <button
            type="button"
            className="kb-save-view-close-btn"
            aria-label="Close"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <form onSubmit={handleSubmit} className="kb-save-view-form">
          <div className="kb-save-view-body">
            {error && (
              <div className="kb-save-view-error" role="alert" data-testid="save-view-error">
                {error}
              </div>
            )}

            <div className="kb-save-view-field">
              <label htmlFor="view-name-input" className="kb-save-view-label">
                Name <span className="kb-required-star">*</span>
              </label>
              <input
                ref={inputRef}
                id="view-name-input"
                type="text"
                className="kb-save-view-input"
                value={name}
                maxLength={120}
                required
                placeholder="e.g. Sprint Backlog, High Priority Defects"
                onChange={(e) => {
                  setName(e.target.value);
                  if (error) setError(null);
                }}
                data-testid="save-view-name-input"
              />
            </div>

            <div className="kb-save-view-field">
              <label htmlFor="view-desc-input" className="kb-save-view-label">
                Description (optional)
              </label>
              <textarea
                id="view-desc-input"
                className="kb-save-view-textarea"
                rows={3}
                value={description}
                maxLength={500}
                placeholder="Purpose or context for this view preset..."
                onChange={(e) => { setDescription(e.target.value); }}
                data-testid="save-view-desc-input"
              />
            </div>

            <div className="kb-save-view-preview-box">
              <span className="kb-save-view-preview-title">Configuration Snapshot:</span>
              <div className="kb-save-view-preview-chips">
                <span className="kb-save-view-chip">Layout: {layout}</span>
                {groupBy && groupBy !== 'none' && (
                  <span className="kb-save-view-chip">Group: {groupBy}</span>
                )}
                {subGroupBy && subGroupBy !== 'none' && (
                  <span className="kb-save-view-chip">Sub-group: {subGroupBy}</span>
                )}
                {activeFilters.searchQuery && (
                  <span className="kb-save-view-chip">Search: "{activeFilters.searchQuery}"</span>
                )}
              </div>
            </div>

            <label className="kb-save-view-checkbox-label">
              <input
                type="checkbox"
                checked={isShared}
                onChange={(e) => { setIsShared(e.target.checked); }}
                data-testid="save-view-shared-checkbox"
              />
              <span>Share view with workspace collaborators</span>
            </label>
          </div>

          <footer className="kb-save-view-footer">
            <button
              type="button"
              className="kb-save-view-cancel-btn"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="kb-save-view-submit-btn"
              disabled={saveMutation.isPending}
              data-testid="save-view-submit-btn"
            >
              {saveMutation.isPending ? 'Saving...' : 'Save view'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
