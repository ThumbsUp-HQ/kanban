import React, { useState, useEffect, useRef, useCallback, useMemo, type JSX } from 'react';
import type { IssueItem } from './viewsApi';
import { saveDraft } from '../drafts/draftsStore';
import { useFocusTrap } from '../drawer/useFocusTrap';
import { AdvancedSection } from '../../ui/AdvancedSection';
import './filterBulk.css';

export interface QuickCreateIssueModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (newIssue: Partial<IssueItem>) => Promise<Partial<IssueItem> | undefined> | Partial<IssueItem> | undefined;
  projectKey: string;
  modulesEnabled?: boolean;
  defaultStateId?: string | undefined;
  defaultPrioritySlug?: string;
  defaultModuleIds?: string[];
  defaultDueDate?: string;
  defaultParentKey?: string;
  defaultAdvancedOpen?: boolean;
  states?: { id: string; name: string; group?: string; color_hex?: string | null; is_default?: boolean }[];
  modules?: { id: string; name: string; emoji?: string }[];
  onOpenPeek?: (issueKey: string) => void;
}

interface PostCreateState {
  key: string;
  summary: string;
  isDraft: boolean;
  draftId?: string;
}

export function QuickCreateIssueModal({
  isOpen,
  onClose,
  onCreate,
  projectKey,
  modulesEnabled = true,
  defaultStateId,
  defaultPrioritySlug = 'medium',
  defaultModuleIds = [],
  defaultDueDate,
  defaultParentKey,
  defaultAdvancedOpen,
  states,
  modules,
  onOpenPeek,
}: QuickCreateIssueModalProps): JSX.Element | null {
  const resolvedInitialStateId = useMemo(() => {
    if (defaultStateId) {
      return defaultStateId;
    }
    if (states && states.length > 0) {
      const def = states.find((s) => s.is_default);
      if (def) return def.id;
      const unstarted = states.find((s) => s.group === 'unstarted');
      if (unstarted) return unstarted.id;
      return states[0]?.id ?? 'state-todo';
    }
    return 'state-todo';
  }, [defaultStateId, states]);

  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [prevSyncedDefaultStateId, setPrevSyncedDefaultStateId] = useState(defaultStateId);
  const [prevSyncedIsOpen, setPrevSyncedIsOpen] = useState(isOpen);
  const [stateId, setStateId] = useState(resolvedInitialStateId);

  if (prevSyncedDefaultStateId !== defaultStateId || (!prevSyncedIsOpen && isOpen)) {
    setPrevSyncedDefaultStateId(defaultStateId);
    setPrevSyncedIsOpen(isOpen);
    setStateId(resolvedInitialStateId);
  }
  const [prioritySlug, setPrioritySlug] = useState(defaultPrioritySlug);
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>(
    modulesEnabled ? defaultModuleIds : [],
  );
  const [dueDate, setDueDate] = useState(defaultDueDate ?? '');
  const [parentKey, setParentKey] = useState(defaultParentKey ?? '');
  const [isDraft, setIsDraft] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [postCreateData, setPostCreateData] = useState<PostCreateState | null>(null);

  const activeAdvancedCount =
    (selectedModuleIds.length > 0 ? 1 : 0) +
    (dueDate ? 1 : 0) +
    (parentKey.trim() ? 1 : 0);
  const hasAdvancedContent =
    activeAdvancedCount > 0 || defaultModuleIds.length > 0;

  const summaryInputRef = useRef<HTMLInputElement>(null);
  const modalContainerRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  // Capture triggering opener element upon open
  useEffect(() => {
    if (isOpen) {
      const active = document.activeElement as HTMLElement | null;
      if (active && active !== document.body && !modalContainerRef.current?.contains(active)) {
        openerRef.current = active;
      }
    }
  }, [isOpen]);

  // Enforce cyclic focus trap while open
  useFocusTrap(isOpen, modalContainerRef);

  const handleClose = useCallback((): void => {
    const opener = openerRef.current;
    onClose();
    if (opener && document.contains(opener)) {
      opener.focus();
    }
  }, [onClose]);

  // Restore focus if unmounted while open
  useEffect(() => {
    return () => {
      const opener = openerRef.current;
      if (opener && document.contains(opener)) {
        opener.focus();
      }
    };
  }, []);

  // Restore focus when transitioning from open to closed
  const prevIsOpen = useRef(isOpen);
  useEffect(() => {
    if (prevIsOpen.current && !isOpen) {
      const opener = openerRef.current;
      if (opener && document.contains(opener)) {
        opener.focus();
      }
    }
    prevIsOpen.current = isOpen;
  }, [isOpen]);

  // Focus input on open or when resetting to form
  useEffect(() => {
    if (isOpen && !postCreateData) {
      const timer = setTimeout(() => {
        summaryInputRef.current?.focus();
      }, 50);
      return () => { clearTimeout(timer); };
    }
  }, [isOpen, postCreateData]);

  // Listen for custom event 'kb:create-issue'
  useEffect(() => {
    const handleCustomCreate = (): void => {
      // Triggered by external buttons / CommandPalette
    };
    window.addEventListener('kb:create-issue', handleCustomCreate);
    return () => {
      window.removeEventListener('kb:create-issue', handleCustomCreate);
    };
  }, []);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        setPostCreateData(null);
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, handleClose]);

  if (!isOpen) {
    return null;
  }

  const handleDone = (): void => {
    setSummary('');
    setDescription('');
    setDueDate('');
    setParentKey('');
    setIsDraft(false);
    setPostCreateData(null);
    handleClose();
  };

  const handleCreateAnother = (): void => {
    setSummary('');
    setDescription('');
    setDueDate('');
    setParentKey('');
    setIsDraft(false);
    setPostCreateData(null);
  };

  const handleViewIssue = (): void => {
    if (postCreateData?.isDraft) {
      if (typeof window !== 'undefined') {
        window.location.href = '/drafts';
      }
    } else if (postCreateData?.key) {
      if (onOpenPeek) {
        onOpenPeek(postCreateData.key);
      } else if (typeof window !== 'undefined') {
        const url = new URL(window.location.href);
        url.searchParams.set('peek', postCreateData.key);
        window.history.pushState({}, '', url.toString());
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
    }
    handleDone();
  };

  const handleSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!summary.trim() || isSubmitting) return;

    if (isDraft) {
      const draft = saveDraft({
        projectKey,
        summary: summary.trim(),
        description: description.trim() || undefined,
        stateId,
        prioritySlug,
        moduleIds: modulesEnabled ? selectedModuleIds : undefined,
      });

      setPostCreateData({
        key: 'Draft',
        summary: draft.summary,
        isDraft: true,
        draftId: draft.id,
      });
      return;
    }

    const matchedState = states?.find((s) => s.id === stateId);
    const payload: Partial<IssueItem> = {
      summary: summary.trim(),
      state: matchedState
        ? {
            id: matchedState.id,
            name: matchedState.name,
            group: matchedState.group ?? 'unstarted',
            color_hex: (matchedState as { color_hex?: string | null }).color_hex ?? null,
          }
        : {
            id: stateId,
            name: stateId.includes('review')
              ? 'In Review'
              : stateId.includes('progress')
                ? 'In Progress'
                : stateId.includes('done')
                  ? 'Done'
                  : stateId.includes('cancel')
                    ? 'Cancelled'
                    : stateId.includes('todo')
                      ? 'Todo'
                      : 'Backlog',
            group:
              stateId.includes('review') || stateId.includes('progress')
                ? 'started'
                : stateId.includes('done')
                  ? 'completed'
                  : stateId.includes('cancel')
                    ? 'cancelled'
                    : stateId.includes('todo')
                      ? 'unstarted'
                      : 'backlog',
          },
      priority: {
        slug: prioritySlug,
        label: prioritySlug.charAt(0).toUpperCase() + prioritySlug.slice(1),
        emoji:
          prioritySlug === 'urgent'
            ? '🔥'
            : prioritySlug === 'high'
              ? '⚡'
              : prioritySlug === 'low'
                ? '🔽'
                : prioritySlug === 'none'
                  ? '➖'
                  : '🔹',
      },
    };

    if (description.trim()) {
      payload.description_markdown = description.trim();
    }
    if (modulesEnabled) {
      payload.module_ids = selectedModuleIds;
    }
    if (dueDate) {
      payload.due_date = dueDate;
    }
    if (parentKey.trim()) {
      payload.parent = { key: parentKey.trim(), summary: '' };
    }

    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const maybeResult = onCreate(payload);
      if (maybeResult instanceof Promise) {
        const res = await maybeResult;
        const resolvedKey =
          res && typeof res === 'object' && typeof res.key === 'string'
            ? res.key
            : `${projectKey}-NEW`;

        setPostCreateData({
          key: resolvedKey,
          summary: summary.trim(),
          isDraft: false,
        });
      } else {
        const res = maybeResult;
        const resolvedKey =
          res && typeof res === 'object' && typeof res.key === 'string'
            ? res.key
            : `${projectKey}-NEW`;

        setPostCreateData({
          key: resolvedKey,
          summary: summary.trim(),
          isDraft: false,
        });
      }
    } catch (err: unknown) {
      setSubmitError(
        err instanceof Error
          ? err.message
          : 'Network error: Failed to create issue. Your draft has been preserved.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // --------------------------------------------------------------------------
  // Post-Create "View Issue / Create Another / Done" Dialog
  // --------------------------------------------------------------------------
  if (postCreateData) {
    return (
      <div
        ref={modalContainerRef}
        className="quick-create-modal-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-create-post-title"
        data-testid="quick-create-post-dialog"
      >
        <div className="quick-create-modal quick-create-modal--post">
          <div className="quick-create-header">
            <h2 id="quick-create-post-title" className="quick-create-title">
              {postCreateData.isDraft ? '✍️ Draft Saved' : '🎉 Work Item Created'}
            </h2>
            <button
              type="button"
              className="filter-chip-remove"
              onClick={handleDone}
              aria-label="Close modal"
            >
              ×
            </button>
          </div>

          <div className="quick-create-post-body">
            <div className="quick-create-post-badge">
              <span className="mono quick-create-post-key">{postCreateData.key}</span>
              <span className="quick-create-post-summary">{postCreateData.summary}</span>
            </div>
            <p className="quick-create-post-desc">
              {postCreateData.isDraft
                ? 'Saved in Drafts (/drafts). You can resume or publish it to the board anytime.'
                : `Successfully created ${postCreateData.key} in ${projectKey}.`}
            </p>
          </div>

          <div className="quick-create-footer">
            <button
              type="button"
              className="quick-create-btn-cancel quick-create-btn-view"
              data-testid="post-create-view-btn"
              onClick={handleViewIssue}
            >
              View Issue
            </button>
            <button
              type="button"
              className="quick-create-btn-cancel quick-create-btn-another"
              data-testid="post-create-another-btn"
              onClick={handleCreateAnother}
            >
              Create Another
            </button>
            <button
              type="button"
              className="quick-create-btn-submit"
              data-testid="post-create-done-btn"
              onClick={handleDone}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Main Quick Create Form
  // --------------------------------------------------------------------------
  return (
    <div
      ref={modalContainerRef}
      className="quick-create-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="quick-create-title"
      data-testid="quick-create-modal"
    >
      <div className="quick-create-modal">
        <div className="quick-create-header">
          <h2 id="quick-create-title" className="quick-create-title">
            Create work item in {projectKey}
          </h2>
          <button
            type="button"
            className="filter-chip-remove"
            onClick={handleClose}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        <form
          onSubmit={(e) => {
            void handleSubmit(e);
          }}
          className="quick-create-form"
        >
          <div className="quick-create-input-group">
            <label htmlFor="quick-create-summary" className="quick-create-label">
              Summary
            </label>
            <input
              ref={summaryInputRef}
              id="quick-create-summary"
              type="text"
              className="quick-create-input"
              placeholder="What needs to be done?"
              value={summary}
              onChange={(e) => {
                setSummary(e.target.value);
              }}
              required
              aria-invalid={Boolean(submitError)}
              aria-describedby={submitError ? 'quick-create-error-msg' : undefined}
            />
          </div>

          <div className="quick-create-input-group">
            <label
              htmlFor="quick-create-description"
              className="quick-create-label"
            >
              Description (Markdown)
            </label>
            <textarea
              id="quick-create-description"
              className="quick-create-textarea"
              placeholder="Add details, acceptance criteria, or Mermaid diagrams..."
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
              }}
            />
          </div>

          <div className="quick-create-row-fields">
            <div className="quick-create-input-group quick-create-input-group--flex1">
              <label htmlFor="quick-create-state" className="quick-create-label">
                State
              </label>
              <select
                id="quick-create-state"
                className="quick-create-select"
                value={stateId}
                onChange={(e) => {
                  setStateId(e.target.value);
                }}
              >
                {states && states.length > 0 ? (
                  states.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))
                ) : (
                  <>
                    <option value="state-backlog">Backlog</option>
                    <option value="state-todo">Todo</option>
                    <option value="state-in-progress">In Progress</option>
                    <option value="state-in-review">In Review</option>
                    <option value="state-done">Done</option>
                    <option value="state-canceled">Cancelled</option>
                  </>
                )}
              </select>
            </div>

            <div className="quick-create-input-group quick-create-input-group--flex1">
              <label
                htmlFor="quick-create-priority"
                className="quick-create-label"
              >
                Priority
              </label>
              <select
                id="quick-create-priority"
                className="quick-create-select"
                value={prioritySlug}
                onChange={(e) => {
                  setPrioritySlug(e.target.value);
                }}
              >
                <option value="urgent">🔥 Urgent</option>
                <option value="high">⚡ High</option>
                <option value="medium">🔹 Medium</option>
                <option value="low">🔽 Low</option>
                <option value="none">➖ None</option>
              </select>
            </div>
          </div>

          {/* Advanced Section: Progressive disclosure for secondary metadata (KB-ADVANCED-DISCLOSURE-02, KAN-368) */}
          <AdvancedSection
            title="Advanced Properties"
            summary="Module, parent issue, and schedule dates"
            testId="quick-create-advanced"
            defaultOpen={defaultAdvancedOpen ?? hasAdvancedContent}
            activeOverridesCount={activeAdvancedCount}
            hasErrors={Boolean(submitError)}
          >
            <div className="quick-create-advanced-grid">
              {modulesEnabled && (
                <div className="quick-create-input-group">
                  <label
                    htmlFor="quick-create-module"
                    className="quick-create-label"
                  >
                    Module
                  </label>
                  <select
                    id="quick-create-module"
                    className="quick-create-select"
                    value={selectedModuleIds[0] ?? ''}
                    onChange={(e) => {
                      setSelectedModuleIds(e.target.value ? [e.target.value] : []);
                    }}
                  >
                    <option value="">No Module</option>
                    {(modules ?? []).map((mod) => (
                      <option key={mod.id} value={mod.id}>
                        {`${mod.emoji ?? '🧩'} ${mod.name}`}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="quick-create-row-fields">
                <div className="quick-create-input-group quick-create-input-group--flex1">
                  <label
                    htmlFor="quick-create-due-date"
                    className="quick-create-label"
                  >
                    Due Date
                  </label>
                  <input
                    id="quick-create-due-date"
                    type="date"
                    className="quick-create-input"
                    value={dueDate}
                    onChange={(e) => {
                      setDueDate(e.target.value);
                    }}
                  />
                </div>

                <div className="quick-create-input-group quick-create-input-group--flex1">
                  <label
                    htmlFor="quick-create-parent"
                    className="quick-create-label"
                  >
                    Parent Issue
                  </label>
                  <input
                    id="quick-create-parent"
                    type="text"
                    className="quick-create-input"
                    placeholder="e.g. KAN-100"
                    value={parentKey}
                    onChange={(e) => {
                      setParentKey(e.target.value);
                    }}
                  />
                </div>
              </div>
            </div>
          </AdvancedSection>

          {submitError && (
            <div
              id="quick-create-error-msg"
              className="quick-create-alert quick-create-alert--error"
              role="alert"
              data-testid="quick-create-error"
            >
              <span>⚠️ {submitError}</span>
            </div>
          )}

          {/* ✍️ Keep work-in-progress Draft Checkbox */}
          <div className="quick-create-draft-row">
            <label
              htmlFor="quick-create-draft"
              className="quick-create-draft-label"
              title="This will be saved in Drafts (/drafts) so you can finish and publish it later."
            >
              <input
                id="quick-create-draft"
                type="checkbox"
                className="quick-create-draft-checkbox"
                data-testid="quick-create-draft-checkbox"
                aria-label="Keep work-in-progress"
                checked={isDraft}
                onChange={(e) => {
                  setIsDraft(e.target.checked);
                }}
              />
              <span>✍️ Keep work-in-progress</span>
            </label>
          </div>

          <div className="quick-create-footer">
            <button
              type="button"
              className="quick-create-btn-cancel"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="quick-create-btn-submit"
              data-testid="quick-create-submit-btn"
              disabled={!summary.trim() || isSubmitting}
              aria-busy={isSubmitting}
            >
              {isSubmitting ? 'Creating...' : isDraft ? 'Save Draft' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
