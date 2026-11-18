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
import type { IssueItem, SortDirection } from '../views/viewsApi';
import '../views/listTable.css';

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
}

export function TableView({
  issues,
  projectKey,
  modulesEnabled = true,
  selectedIds = [],
  onToggleSelect,
  onSelectAll,
  onCreateIssue,
  nextCursor,
  onLoadMore,
  isLoading = false,
  onOpenPeek,
}: TableViewProps): JSX.Element {
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

  // Sort issues deterministically
  const sortedIssues = useMemo(() => {
    if (!sortField || sortDir === 'none') {
      return issues;
    }

    return [...issues].sort((a, b) => {
      let cmp = 0;
      if (sortField === 'key') {
        cmp = a.key.localeCompare(b.key);
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
      } else if (sortField === 'created_by') {
        const cA = (a.created_by_handle ?? a.created_by_id) ?? '';
        const cB = (b.created_by_handle ?? b.created_by_id) ?? '';
        cmp = cA.localeCompare(cB);
      }

      if (cmp !== 0) {
        return sortDir === 'asc' ? cmp : -cmp;
      }
      // Tie break on key
      return a.key.localeCompare(b.key);
    });
  }, [issues, sortField, sortDir]);

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
    <div className="table-view-container">
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
                  const label = def?.label ?? colId;
                  const isSortable = def?.sortable;
                  const isCurrentSort = sortField === colId;
                  let ariaSort: 'none' | 'ascending' | 'descending' = 'none';
                  if (isCurrentSort) {
                    ariaSort = sortDir === 'asc' ? 'ascending' : 'descending';
                  }

                  return (
                    <th
                      key={colId}
                      data-col-header={colId}
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
                  key={issue.id || issue.key}
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
                  <td className="sticky-col">
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
                        return <td key={colId}>{issue.summary}</td>;
                      }
                      if (colId === 'state') {
                        return (
                          <td key={colId}>
                            <StateBadge state={issue.state} className="status-pill" />
                          </td>
                        );
                      }
                      if (colId === 'priority') {
                        return (
                          <td key={colId}>
                            <span className="table-priority-cell">
                              <EmojiHint kind={priorityKind} testId={`hint-prio-${priorityKind}`} />
                              <span>{issue.priority.label ? issue.priority.label : issue.priority.slug}</span>
                            </span>
                          </td>
                        );
                      }
                      if (colId === 'assignees') {
                        return (
                          <td key={colId}>
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
                                  <span>{a.kind === 'free_text' ? a.free_text : (a.principal.display_name ? a.principal.display_name : a.principal.handle)}</span>
                                </span>
                              ))}
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
                        return (
                          <td key={colId}>
                            {issue.cycle_id ? <span className="cycle-pill">Cycle</span> : null}
                          </td>
                        );
                      }
                      if (colId === 'modules') {
                        return (
                          <td key={colId}>
                            {issue.module_ids && issue.module_ids.length > 0 ? (
                              <span className="module-pill">Modules</span>
                            ) : null}
                          </td>
                        );
                      }
                      if (colId === 'start_date') {
                        return <td key={colId}>{issue.start_date ?? ''}</td>;
                      }
                      if (colId === 'due_date') {
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
