import React, { useState, useMemo, type JSX } from 'react';
import { ColumnConfigurator } from './ColumnConfigurator';
import {
  type TableColumnId,
  ALL_TABLE_COLUMNS,
  getDefaultColumns,
  parseTableColumns,
} from './tableColumns';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { StateBadge } from '../../components/state/StateBadge';
import {
  parseIssueNumber,
  parseTimestampMs,
  sortIssuesList,
} from '../list/ListView';
import {
  patchProjectIssue,
  type IssueItem,
  type SortDirection,
  type StateSummary,
  normalizeStateKey,
} from '../views/viewsApi';
import '../views/listTable.css';
import './TableView.css';

export interface TableViewProps {
  issues: IssueItem[];
  projectKey: string;
  modulesEnabled?: boolean | undefined;
  selectedIds?: string[] | undefined;
  onToggleSelect?: ((key: string, selected: boolean) => void) | undefined;
  onSelectAll?: ((selected: boolean) => void) | undefined;
  onCreateIssue?: (() => void) | undefined;
  nextCursor?: string | null | undefined;
  onLoadMore?: (() => void) | undefined;
  isLoading?: boolean | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  capabilities?: string[] | undefined;
  currentUserCapabilities?: string[] | undefined;
  projectStates?: StateSummary[] | undefined;
  onUpdateIssue?: ((issueKey: string, patch: Partial<IssueItem>) => Promise<void> | void) | undefined;
  totalProjectIssueCount?: number | undefined;
  hiddenByStateCount?: number | undefined;
  onShowAllStates?: (() => void) | undefined;
  onResetFilters?: (() => void) | undefined;
}

export function TableView({
  issues,
  projectKey,
  projectStates,
  modulesEnabled = true,
  selectedIds = [],
  onToggleSelect,
  onSelectAll,
  onCreateIssue,
  nextCursor,
  onLoadMore,
  isLoading = false,
  onOpenPeek,
  capabilities,
  currentUserCapabilities,
  onUpdateIssue,
  totalProjectIssueCount = 0,
  hiddenByStateCount = 0,
  onShowAllStates,
  onResetFilters,
}: TableViewProps): JSX.Element {
  const [prevIssues, setPrevIssues] = useState<IssueItem[]>(issues);
  const [localIssues, setLocalIssues] = useState<IssueItem[]>(issues);
  if (issues !== prevIssues) {
    setPrevIssues(issues);
    setLocalIssues(issues);
  }

  const effectiveCaps = capabilities ?? currentUserCapabilities;
  const hasTransitionOrEdit = (caps: string[]): boolean =>
    caps.includes('TRANSITION') || caps.includes('EDIT') || caps.includes('ADMIN');
  const hasEditOrAdmin = (caps: string[]): boolean =>
    caps.includes('EDIT') || caps.includes('ADMIN');
  const isViewerOnly = Boolean(
    effectiveCaps && effectiveCaps.length > 0 && !hasEditOrAdmin(effectiveCaps),
  );

  const canEditIssue = (issue: IssueItem): boolean => {
    if (isViewerOnly) return false;
    if (issue.capabilities && issue.capabilities.length > 0) {
      return hasEditOrAdmin(issue.capabilities);
    }
    return true;
  };

  const canTransitionIssue = (issue: IssueItem): boolean => {
    const caps = issue.capabilities ?? effectiveCaps;
    if (caps && caps.length > 0) {
      return hasTransitionOrEdit(caps);
    }
    return true;
  };

  const handleInlineStateChange = (issue: IssueItem, newStateIdOrName: string) => {
    const previousState = issue.state;
    let resolvedState: StateSummary | undefined;
    if (projectStates && projectStates.length > 0) {
      resolvedState = projectStates.find(
        (s) =>
          s.id === newStateIdOrName ||
          s.name === newStateIdOrName ||
          normalizeStateKey(s.name) === normalizeStateKey(newStateIdOrName)
      );
    }

    if (resolvedState) {
      const patch: Partial<IssueItem> = {
        state: {
          id: resolvedState.id,
          name: resolvedState.name,
          group: resolvedState.group,
          color_hex: resolvedState.color_hex ?? null,
        },
      };
      setLocalIssues((prev) =>
        prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
      );
      void onUpdateIssue?.(issue.key, patch);
      void patchProjectIssue(issue.key, { state_id: resolvedState.id }).catch((err: unknown) => {
        setLocalIssues((prev) =>
          prev.map((i) => (i.key === issue.key ? { ...i, state: previousState } : i)),
        );
        void onUpdateIssue?.(issue.key, { state: previousState });
        const msg = err instanceof Error ? err.message : 'Failed to transition state';
        window.dispatchEvent(
          new CustomEvent('kb:alert', { detail: { type: 'error', message: msg } }),
        );
      });
      window.dispatchEvent(
        new CustomEvent('kb:issue-updated', {
          detail: { issueKey: issue.key, patch },
        }),
      );
      return;
    }

    const isDone = newStateIdOrName === 'Done';
    const isProgress = newStateIdOrName === 'In Progress' || newStateIdOrName === 'In Review';
    const group = isDone
      ? 'completed'
      : newStateIdOrName === 'Cancelled'
        ? 'cancelled'
        : isProgress
          ? 'started'
          : 'unstarted';
    const stateId = `state-${newStateIdOrName.toLowerCase().replace(/\s+/g, '-')}`;
    const patch: Partial<IssueItem> = {
      state: {
        id: stateId,
        name: newStateIdOrName,
        group,
      },
    };
    setLocalIssues((prev) =>
      prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
    );
    void onUpdateIssue?.(issue.key, patch);
    void patchProjectIssue(issue.key, { state_id: stateId }).catch((err: unknown) => {
      setLocalIssues((prev) =>
        prev.map((i) => (i.key === issue.key ? { ...i, state: previousState } : i)),
      );
      void onUpdateIssue?.(issue.key, { state: previousState });
      const msg = err instanceof Error ? err.message : 'Failed to transition state';
      window.dispatchEvent(
        new CustomEvent('kb:alert', { detail: { type: 'error', message: msg } }),
      );
    });
    window.dispatchEvent(
      new CustomEvent('kb:issue-updated', {
        detail: { issueKey: issue.key, patch },
      }),
    );
  };

  const handleInlinePriorityChange = (issue: IssueItem, newPrioritySlug: string) => {
    const label = newPrioritySlug.charAt(0).toUpperCase() + newPrioritySlug.slice(1);
    const patch: Partial<IssueItem> = {
      priority: {
        slug: newPrioritySlug,
        label,
      },
    };
    setLocalIssues((prev) =>
      prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
    );
    void onUpdateIssue?.(issue.key, patch);
    void patchProjectIssue(issue.key, { priority: newPrioritySlug }).catch(() => undefined);
    window.dispatchEvent(
      new CustomEvent('kb:issue-updated', {
        detail: { issueKey: issue.key, patch },
      }),
    );
  };

  const handleInlineDateChange = (
    issue: IssueItem,
    field: 'start_date' | 'due_date',
    val: string,
  ) => {
    const patch: Partial<IssueItem> = {
      [field]: val || null,
    };
    setLocalIssues((prev) =>
      prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
    );
    void onUpdateIssue?.(issue.key, patch);
    void patchProjectIssue(issue.key, { [field]: val || null }).catch(() => undefined);
    window.dispatchEvent(
      new CustomEvent('kb:issue-updated', {
        detail: { issueKey: issue.key, patch },
      }),
    );
  };

  const handleInlineCycleChange = (issue: IssueItem, cycleId: string) => {
    const patch: Partial<IssueItem> = {
      cycle_id: cycleId || null,
      cycle: cycleId ? { id: cycleId, name: cycleId.replace(/^cycle-/, 'Cycle ') } : null,
    };
    setLocalIssues((prev) =>
      prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
    );
    void onUpdateIssue?.(issue.key, patch);
    void patchProjectIssue(issue.key, { cycle_id: cycleId || null }).catch(() => undefined);
    window.dispatchEvent(
      new CustomEvent('kb:issue-updated', {
        detail: { issueKey: issue.key, patch },
      }),
    );
  };

  const handleInlineAssignToggle = (issue: IssueItem) => {
    const currentAssignees = issue.assignees ?? [];
    const isMeAssigned = currentAssignees.some(
      (a) => a.kind === 'principal' && a.principal.handle === 'adam',
    );
    const newAssignees = isMeAssigned
      ? currentAssignees.filter(
          (a) => !(a.kind === 'principal' && a.principal.handle === 'adam'),
        )
      : [
          ...currentAssignees,
          {
            id: 'asg-me',
            kind: 'principal' as const,
            principal: {
              id: 'u-me',
              handle: 'adam',
              display_name: 'Adam Outler',
              type: 'USER',
            },
          },
        ];
    const patch: Partial<IssueItem> = {
      assignees: newAssignees,
    };
    setLocalIssues((prev) =>
      prev.map((i) => (i.key === issue.key ? { ...i, ...patch } : i)),
    );
    void onUpdateIssue?.(issue.key, patch);
    void patchProjectIssue(issue.key, {
      assignee_ids: newAssignees
        .filter((a) => a.kind === 'principal')
        .map((a) => a.principal.id),
    }).catch(() => undefined);
    window.dispatchEvent(
      new CustomEvent('kb:issue-updated', {
        detail: { issueKey: issue.key, patch },
      }),
    );
  };
  // Load saved columns from localStorage
  const [columns, setColumns] = useState<TableColumnId[]>(() => {
    try {
      const stored = localStorage.getItem(`kb.tableCols.${projectKey}`);
      return parseTableColumns(stored, projectKey, modulesEnabled);
    } catch {
      return getDefaultColumns(modulesEnabled);
    }
  });

  // Sorting state
  const [sortField, setSortField] = useState<TableColumnId | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>('none');

  const handleSortClick = (colId: TableColumnId) => {
    if (sortField !== colId) {
      setSortField(colId);
      setSortDir('asc');
    } else if (sortDir === 'asc') {
      setSortDir('desc');
    } else {
      setSortField(null);
      setSortDir('none');
    }
  };

  // Sort issues deterministically (defaulting to updated desc when unsorted per KAN-308 Problem 4)
  const sortedIssues = useMemo(() => {
    if (!sortField || sortDir === 'none') {
      return sortIssuesList(localIssues, 'updated', 'desc');
    }

    return [...localIssues].sort((a, b) => {
      let cmp = 0;
      if (sortField === 'key') {
        cmp = parseIssueNumber(a.key) - parseIssueNumber(b.key);
        if (cmp === 0) {
          cmp = a.key.localeCompare(b.key);
        }
      } else if (sortField === 'summary') {
        cmp = a.summary.localeCompare(b.summary);
      } else if (sortField === 'state') {
        const sA = a.state.name;
        const sB = b.state.name;
        cmp = sA.localeCompare(sB);
      } else if (sortField === 'priority') {
        const pA = a.priority.sort_order ?? 999;
        const pB = b.priority.sort_order ?? 999;
        cmp = pA - pB;
      } else if (sortField === 'due_date') {
        const dA = a.due_date ?? '';
        const dB = b.due_date ?? '';
        cmp = dA.localeCompare(dB);
      } else if (sortField === 'start_date') {
        const dA = a.start_date ?? '';
        const dB = b.start_date ?? '';
        cmp = dA.localeCompare(dB);
      } else if (sortField === 'updated_at') {
        const uA = parseTimestampMs(a.updated_at ?? a.created_at);
        const uB = parseTimestampMs(b.updated_at ?? b.created_at);
        cmp = uA - uB;
      } else if (sortField === 'created_by') {
        const cA = (a.created_by_handle ?? a.created_by_id) ?? '';
        const cB = (b.created_by_handle ?? b.created_by_id) ?? '';
        cmp = cA.localeCompare(cB);
      }

      if (cmp !== 0) {
        return sortDir === 'asc' ? cmp : -cmp;
      }
      // Deterministic tie break on issue number then key
      const numDiff = parseIssueNumber(a.key) - parseIssueNumber(b.key);
      return numDiff !== 0 ? numDiff : a.key.localeCompare(b.key);
    });
  }, [localIssues, sortField, sortDir]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const allSelected = issues.length > 0 && issues.every((i) => selectedSet.has(i.key));

  const colDefMap = useMemo(() => {
    const map = new Map<TableColumnId, (typeof ALL_TABLE_COLUMNS)[number]>();
    for (const c of ALL_TABLE_COLUMNS) {
      map.set(c.id, c);
    }
    return map;
  }, []);

  // Filter columns to active and valid (strictly omitting modules if modulesEnabled is false)
  const activeColumns = useMemo(() => {
    return columns.filter((colId) => {
      if (colId === 'modules' && !modulesEnabled) {
        return false;
      }
      return true;
    });
  }, [columns, modulesEnabled]);

  if (issues.length === 0) {
    if (totalProjectIssueCount > 0 && hiddenByStateCount > 0) {
      return (
        <div className="view-empty-state" data-testid="empty-state-hidden-terminal">
          <h2 className="view-empty-title">No actionable work items</h2>
          <p className="view-empty-desc">
            {hiddenByStateCount} completed or cancelled work item(s) are hidden by your state filter.
          </p>
          <button
            type="button"
            className="view-empty-create-btn"
            data-testid="empty-show-all-states-btn"
            onClick={() => {
              onShowAllStates?.();
            }}
          >
            Show all states
          </button>
        </div>
      );
    }
    if (totalProjectIssueCount > 0) {
      return (
        <div className="view-empty-state" data-testid="empty-state-filtered">
          <h2 className="view-empty-title">No matching work items</h2>
          <p className="view-empty-desc">
            No work items match your active search or filter criteria.
          </p>
          <button
            type="button"
            className="view-empty-create-btn"
            data-testid="empty-reset-filters-btn"
            onClick={() => {
              onResetFilters?.();
            }}
          >
            Reset to default filters
          </button>
        </div>
      );
    }
    return (
      <div className="view-empty-state">
        <h2 className="view-empty-title">No work items found</h2>
        <p className="view-empty-desc">Get started by creating the first work item in this project.</p>
        {onCreateIssue && (
          <button
            type="button"
            className="view-empty-create-btn"
            onClick={onCreateIssue}
          >
            + Create first work item
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="table-view-container" data-testid="table-view">
      <div className="table-toolbar">
        <span className="mono">{issues.length} items</span>
        <ColumnConfigurator
          columns={activeColumns}
          onChange={setColumns}
          projectKey={projectKey}
          modulesEnabled={modulesEnabled}
        />
      </div>

      <div className="table-scroll-wrap">
        <table className="issues-table">
          <thead className="issues-table-head">
            <tr className="table-header-row">
              <th className="sticky-col table-key-header" data-col-header="key">
                <div className="table-key-cell-content">
                  {onSelectAll && (
                    <input
                      type="checkbox"
                      checked={allSelected}
                      aria-label="Select all issues"
                      onChange={(e) => { onSelectAll(e.target.checked); }}
                    />
                  )}
                  <button
                    type="button"
                    className="issues-table-sort-btn"
                    onClick={() => { handleSortClick('key'); }}
                  >
                    <span>Key</span>
                    {sortField === 'key' && (
                      <span className="issues-table-sort-icon">
                        {sortDir === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </button>
                </div>
              </th>

              {activeColumns
                .filter((id) => id !== 'key')
                .map((colId) => {
                  const def = colDefMap.get(colId);
                  if (!def) return null;
                  const label = def.label;
                  const isSortable = def.sortable;
                  const isCurrentSort = sortField === colId;
                  let ariaSort: 'none' | 'ascending' | 'descending' = 'none';
                  if (isCurrentSort) {
                    ariaSort = sortDir === 'asc' ? 'ascending' : 'descending';
                  }

                  return (
                    <th
                      key={colId}
                      data-col-header={colId}
                      className={`table-col-header table-col-header--${colId}`}
                      aria-sort={isSortable ? ariaSort : undefined}
                    >
                      {isSortable ? (
                        <button
                          type="button"
                          className="issues-table-sort-btn"
                          onClick={() => { handleSortClick(colId); }}
                        >
                          <span>{label}</span>
                          {isCurrentSort && (
                            <span className="issues-table-sort-icon">
                              {sortDir === 'asc' ? '▲' : '▼'}
                            </span>
                          )}
                        </button>
                      ) : (
                        <span>{label}</span>
                      )}
                    </th>
                  );
                })}
            </tr>
          </thead>

          <tbody className="issues-table-body">
            {sortedIssues.map((issue) => {
              const isSelected = selectedSet.has(issue.key);
              const canEdit = canEditIssue(issue);

              // Priority mapping
              let priorityKind: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' =
                'priorityMedium';
              const pSlug = issue.priority.slug.toLowerCase();
              if (pSlug === 'urgent') priorityKind = 'priorityUrgent';
              else if (pSlug === 'high') priorityKind = 'priorityHigh';
              else if (pSlug === 'low') priorityKind = 'priorityLow';

              // Overdue check
              const isTerminal =
                issue.state.group === 'completed' || issue.state.group === 'cancelled';
              let isOverdue = false;
              if (issue.due_date && !isTerminal) {
                const today = new Date().toISOString().slice(0, 10);
                if (issue.due_date < today) {
                  isOverdue = true;
                }
              }

              return (
                <tr
                  key={issue.key}
                  data-issue-key={issue.key}
                  className={`table-row ${isSelected ? 'table-row--selected' : ''}`.trim()}
                  onClick={(e) => {
                    const target = e.target as HTMLElement | null;
                    if (
                      target?.closest(
                        'button, input, select, textarea, a, [role="button"]',
                      )
                    ) {
                      return;
                    }
                    onOpenPeek?.(issue.key);
                  }}
                >
                  <td className="sticky-col table-key-cell" data-col="key">
                    <div className="table-key-cell-content">
                      {onToggleSelect && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          aria-label={`Select ${issue.key}`}
                          onChange={(e) => { onToggleSelect(issue.key, e.target.checked); }}
                        />
                      )}
                      <a
                        href={`?layout=table&peek=${encodeURIComponent(issue.key)}`}
                        className="mono table-key-link"
                        onClick={(e) => {
                          if (onOpenPeek) {
                            e.preventDefault();
                            onOpenPeek(issue.key);
                          }
                        }}
                      >
                        {issue.key}
                      </a>
                    </div>
                  </td>

                  {activeColumns
                    .filter((id) => id !== 'key')
                    .map((colId) => {
                      if (colId === 'summary') {
                        return (
                          <td
                            key={colId}
                            className="table-summary-cell"
                            data-col="summary"
                            title={issue.summary}
                          >
                            <span className="table-summary-text">{issue.summary}</span>
                          </td>
                        );
                      }
                      if (colId === 'state') {
                        const canTrans = canTransitionIssue(issue);
                        if (!canTrans) {
                          return (
                            <td key={colId} className="table-state-cell" data-col="state">
                              <StateBadge state={issue.state} className="status-pill" />
                            </td>
                          );
                        }
                        const activeStateVal =
                          projectStates && projectStates.length > 0
                            ? (projectStates.find((s) => s.id === issue.state.id)?.id ??
                              projectStates.find(
                                (s) =>
                                  normalizeStateKey(s.name) ===
                                  normalizeStateKey(issue.state.name),
                              )?.id ??
                              issue.state.id)
                            : issue.state.name;
                        return (
                          <td
                            key={colId}
                            className="table-editable-cell table-state-cell"
                            data-testid={`cell-state-${issue.id}`}
                            data-col="state"
                          >
                            <select
                              className="table-inline-select table-inline-select--state"
                              aria-label={`Edit state for ${issue.key}`}
                              value={activeStateVal}
                              onChange={(e) => {
                                handleInlineStateChange(issue, e.target.value);
                              }}
                            >
                              {projectStates && projectStates.length > 0 ? (
                                projectStates.map((st) => (
                                  <option key={st.id} value={st.id}>
                                    {st.name}
                                  </option>
                                ))
                              ) : (
                                <>
                                  <option value="Backlog">Backlog</option>
                                  <option value="Todo">Todo</option>
                                  <option value="In Progress">In Progress</option>
                                  <option value="In Review">In Review</option>
                                  <option value="Done">Done</option>
                                  <option value="Cancelled">Cancelled</option>
                                </>
                              )}
                            </select>
                          </td>
                        );
                      }
                      if (colId === 'priority') {
                        if (!canEdit) {
                          return (
                            <td key={colId} className="table-priority-cell-wrap" data-col="priority">
                              <span className="table-priority-cell">
                                <EmojiHint kind={priorityKind} testId={`hint-prio-${priorityKind}`} />
                                <span>{issue.priority.label || issue.priority.slug}</span>
                              </span>
                            </td>
                          );
                        }
                        return (
                          <td
                            key={colId}
                            className="table-editable-cell table-priority-cell-wrap"
                            data-testid={`cell-priority-${issue.id}`}
                            data-col="priority"
                          >
                            <span className="table-priority-cell">
                              <EmojiHint kind={priorityKind} testId={`hint-prio-${priorityKind}`} />
                              <select
                                className="table-inline-select table-inline-select--priority"
                                aria-label={`Edit priority for ${issue.key}`}
                                value={issue.priority.slug.toLowerCase()}
                                onChange={(e) => {
                                  handleInlinePriorityChange(issue, e.target.value);
                                }}
                              >
                                <option value="urgent">Urgent</option>
                                <option value="high">High</option>
                                <option value="medium">Medium</option>
                                <option value="low">Low</option>
                                <option value="none">None</option>
                              </select>
                            </span>
                          </td>
                        );
                      }
                      if (colId === 'assignees') {
                        return (
                          <td key={colId} className={canEdit ? 'table-editable-cell' : ''}>
                            <div className="table-chips-wrap">
                              {issue.assignees?.map((a) => (
                                <span
                                  key={a.id}
                                  className={`assignee-chip ${a.kind === 'free_text' ? 'assignee-chip--external' : ''}`}
                                >
                                  {a.kind === 'free_text' && (
                                    <EmojiHint
                                      kind="externalAssignee"
                                      testId="hint-external-assignee"
                                    />
                                  )}
                                  <span>{a.kind === 'free_text' ? a.free_text : (a.principal.display_name || a.principal.handle)}</span>
                                </span>
                              ))}
                              {canEdit && (
                                <button
                                  type="button"
                                  className="table-inline-assign-btn"
                                  aria-label={`Assign issue ${issue.key}`}
                                  onClick={() => {
                                    handleInlineAssignToggle(issue);
                                  }}
                                >
                                  +
                                </button>
                              )}
                            </div>
                          </td>
                        );
                      }
                      if (colId === 'labels') {
                        return (
                          <td key={colId}>
                            <div className="table-chips-wrap">
                              {issue.labels?.map((lbl) => (
                                <span key={lbl.id} className="label-pill">
                                  {lbl.name}
                                </span>
                              ))}
                            </div>
                          </td>
                        );
                      }
                      if (colId === 'cycle') {
                        if (!canEdit) {
                          return (
                            <td key={colId}>
                              {issue.cycle_id ? (
                                <span className="cycle-pill" data-testid="cycle-pill">
                                  🔄 {issue.cycle?.name ?? 'Cycle'}
                                </span>
                              ) : null}
                            </td>
                          );
                        }
                        return (
                          <td key={colId} className="table-editable-cell" data-testid={`cell-cycle-${issue.id}`}>
                            <select
                              className="table-inline-select table-inline-select--cycle"
                              aria-label={`Edit cycle for ${issue.key}`}
                              value={issue.cycle_id ?? ''}
                              onChange={(e) => {
                                handleInlineCycleChange(issue, e.target.value);
                              }}
                            >
                              <option value="">No cycle</option>
                              <option value="cycle-1">Cycle 1</option>
                              <option value="cycle-2">Cycle 2</option>
                              <option value="cycle-3">Cycle 3</option>
                              {issue.cycle_id && !['cycle-1', 'cycle-2', 'cycle-3'].includes(issue.cycle_id) && (
                                <option value={issue.cycle_id}>{issue.cycle?.name ?? issue.cycle_id}</option>
                              )}
                            </select>
                          </td>
                        );
                      }
                      if (colId === 'modules') {
                        return (
                          <td key={colId}>
                            {modulesEnabled && issue.module_ids && issue.module_ids.length > 0 ? (
                              <div className="table-chips-wrap">
                                {issue.modules && issue.modules.length > 0 ? (
                                  issue.modules.map((m) => (
                                    <span key={m.id} className="module-pill" data-testid="module-pill">
                                      📦 {m.name}
                                    </span>
                                  ))
                                ) : (
                                  <span className="module-pill" data-testid="module-pill">
                                    📦 Module
                                  </span>
                                )}
                              </div>
                            ) : null}
                          </td>
                        );
                      }
                      if (colId === 'start_date') {
                        if (!canEdit) {
                          return <td key={colId}>{issue.start_date ?? ''}</td>;
                        }
                        return (
                          <td key={colId} className="table-editable-cell" data-testid={`cell-date-${issue.id}`}>
                            <input
                              type="date"
                              className="table-inline-input table-inline-input--date"
                              aria-label={`Edit start date for ${issue.key}`}
                              value={issue.start_date ?? ''}
                              onChange={(e) => {
                                handleInlineDateChange(issue, 'start_date', e.target.value);
                              }}
                            />
                          </td>
                        );
                      }
                      if (colId === 'due_date') {
                        if (!canEdit) {
                          return (
                            <td key={colId}>
                              {issue.due_date ? (
                                <span className={`due-pill ${isOverdue ? 'due-pill--overdue' : ''}`}>
                                  📅 {issue.due_date}
                                </span>
                              ) : (
                                ''
                              )}
                            </td>
                          );
                        }
                        return (
                          <td key={colId} className={`table-editable-cell ${isOverdue ? 'due-pill--overdue' : ''}`.trim()}>
                            <input
                              type="date"
                              className="table-inline-input table-inline-input--date"
                              aria-label={`Edit due date for ${issue.key}`}
                              value={issue.due_date ?? ''}
                              onChange={(e) => {
                                handleInlineDateChange(issue, 'due_date', e.target.value);
                              }}
                            />
                          </td>
                        );
                      }
                      if (colId === 'updated_at') {
                        const rawUpdated = issue.updated_at ?? issue.created_at ?? '';
                        const displayUpdated = rawUpdated ? rawUpdated.slice(0, 10) : '';
                        return (
                          <td key={colId} data-col="updated_at" title={rawUpdated}>
                            {displayUpdated}
                          </td>
                        );
                      }
                      if (colId === 'created_by') {
                        return <td key={colId}>{issue.created_by_handle ?? issue.created_by_id}</td>;
                      }
                      return (
                        <td key={colId}>
                          {issue.has_explicit_acl && <EmojiHint kind="access" />}
                        </td>
                      );
                    })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {nextCursor && (
        <div className="view-load-more">
          <button
            type="button"
            className="view-load-more-btn"
            disabled={isLoading}
            onClick={onLoadMore}
          >
            {isLoading ? 'Loading...' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}
