/**
 * Left Master Rail Issue List View (KAN-52 Problem 2).
 * Replaces x/y-flipped Kanban status folding sections with compact 2-line cards,
 * rail header with Order by sorting and refresh, and mobile touch state controls.
 */

import React, { useState, useMemo, useEffect, useCallback, type JSX } from 'react';
import { PriorityIcon } from '../../components/icons/KanbanIcons';
import { StateBadge } from '../../components/state/StateBadge';
import { QuickFieldPopover } from '../views/QuickFieldPopover';
import type { IssueItem, StateSummary } from '../views/viewsApi';
import '../views/listTable.css';

export interface ListViewProps {
  issues: IssueItem[];
  projectKey?: string | undefined;
  projectStates?: StateSummary[] | undefined;
  modulesEnabled?: boolean | undefined;
  selectedIds?: string[] | undefined;
  onToggleSelect?: ((key: string, selected: boolean) => void) | undefined;
  onCreateIssue?: (() => void) | undefined;
  nextCursor?: string | null | undefined;
  onLoadMore?: (() => void) | undefined;
  isLoading?: boolean | undefined;
  focusedKey?: string | null | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  activeKey?: string | null | undefined;
  canManageWorkflows?: boolean | undefined;
  capabilities?: ReadonlySet<string> | readonly string[] | undefined;
  onOpenFieldPopover?: ((field: 'state', issue: IssueItem, rect: DOMRect) => void) | undefined;
  onStateSelect?: ((issueKey: string, stateId: string) => void) | undefined;
  onRefresh?: (() => void) | undefined;
  sortBy?: IssueSortOption | undefined;
  onSortByChange?: ((sortBy: IssueSortOption) => void) | undefined;
  sortDir?: ('asc' | 'desc') | undefined;
  onSortDirChange?: ((sortDir: 'asc' | 'desc') => void) | undefined;
}

export type IssueSortOption =
  | 'updated'
  | 'created'
  | 'priority'
  | 'state'
  | 'key'
  | 'due_date'
  | 'rank';

const PRIORITY_WEIGHTS: Record<string, number> = {
  urgent: 5,
  high: 4,
  medium: 3,
  low: 2,
  none: 1,
};

function parseIssueNumber(key: string): number {
  const parts = key.split('-');
  const num = parseInt(parts[1] ?? '0', 10);
  return isNaN(num) ? 0 : num;
}

export function sortIssuesList<T extends IssueItem>(
  issues: readonly T[],
  sortBy: IssueSortOption,
  sortDir: 'asc' | 'desc',
): T[] {
  const sorted = [...issues].sort((a, b) => {
    let cmp = 0;
    switch (sortBy) {
      case 'updated': {
        const aUp = a.updated_at ?? '';
        const bUp = b.updated_at ?? '';
        cmp = aUp.localeCompare(bUp);
        break;
      }
      case 'created': {
        const aCr = a.created_at ?? '';
        const bCr = b.created_at ?? '';
        cmp = aCr.localeCompare(bCr);
        break;
      }
      case 'priority': {
        const wA = PRIORITY_WEIGHTS[a.priority.slug.toLowerCase()] ?? 0;
        const wB = PRIORITY_WEIGHTS[b.priority.slug.toLowerCase()] ?? 0;
        cmp = wA - wB;
        break;
      }
      case 'state': {
        const orderA = a.state.sort_order ?? 999;
        const orderB = b.state.sort_order ?? 999;
        cmp = orderA - orderB;
        if (cmp === 0) {
          cmp = a.state.name.localeCompare(b.state.name);
        }
        break;
      }
      case 'key': {
        cmp = parseIssueNumber(a.key) - parseIssueNumber(b.key);
        break;
      }
      case 'due_date': {
        const dA = a.due_date ?? '';
        const dB = b.due_date ?? '';
        cmp = dA.localeCompare(dB);
        break;
      }
      case 'rank': {
        const rA = a.board_rank ?? '';
        const rB = b.board_rank ?? '';
        cmp = rA.localeCompare(rB);
        break;
      }
      default:
        cmp = 0;
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });
  return sorted;
}

export function ListView({
  issues,
  projectStates = [],
  selectedIds = [],
  onToggleSelect,
  onCreateIssue,
  nextCursor,
  onLoadMore,
  isLoading = false,
  focusedKey,
  capabilities,
  onOpenPeek,
  activeKey,
  onOpenFieldPopover,
  onStateSelect,
  onRefresh,
  sortBy: sortByProp,
  onSortByChange,
  sortDir: sortDirProp,
  onSortDirChange,
}: ListViewProps): JSX.Element {
  const [internalSortBy, setInternalSortBy] = useState<IssueSortOption>('updated');
  const [internalSortDir, setInternalSortDir] = useState<'asc' | 'desc'>('desc');

  const sortBy = sortByProp ?? internalSortBy;
  const sortDir = sortDirProp ?? internalSortDir;

  const handleSortByChange = (val: IssueSortOption): void => {
    setInternalSortBy(val);
    onSortByChange?.(val);
  };

  const handleSortDirToggle = (): void => {
    const next = sortDir === 'asc' ? 'desc' : 'asc';
    setInternalSortDir(next);
    onSortDirChange?.(next);
  };

  // Favorites tracking (persisted in localStorage)
  const [favoriteKeys, setFavoriteKeys] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem('kb_favorite_issues');
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        return new Set(Array.isArray(parsed) ? (parsed as unknown[]).filter((x): x is string => typeof x === 'string') : []);
      }
    } catch {
      // ignore localStorage errors in hermetic tests
    }
    return new Set<string>();
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handleFavChange = (): void => {
      try {
        const stored = localStorage.getItem('kb_favorite_issues');
        if (stored) {
          const parsed: unknown = JSON.parse(stored);
          setFavoriteKeys(new Set(Array.isArray(parsed) ? (parsed as unknown[]).filter((x): x is string => typeof x === 'string') : []));
        }
      } catch {
        // ignore
      }
    };
    window.addEventListener('kb:favorites-changed', handleFavChange);
    return () => {
      window.removeEventListener('kb:favorites-changed', handleFavChange);
    };
  }, []);

  const toggleFavorite = useCallback((key: string) => {
    setFavoriteKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      try {
        localStorage.setItem('kb_favorite_issues', JSON.stringify(Array.from(next)));
        window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  // QuickFieldPopover local fallback state
  const [localPopoverIssue, setLocalPopoverIssue] = useState<IssueItem | null>(null);
  const [localAnchor, setLocalAnchor] = useState<DOMRect | null>(null);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  // Sort issues according to sortBy and sortDir
  const sortedIssues = useMemo(() => {
    return sortIssuesList(issues, sortBy, sortDir);
  }, [issues, sortBy, sortDir]);

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
    <div className="list-view issue-master-rail" data-testid="issue-list-rail">
      {/* Rail Header (Order by + Direction + Refresh) */}
      <div className="issue-rail-header" data-testid="issue-rail-header">
        <div className="issue-rail-sort-group">
          <label htmlFor="issue-order-by" className="issue-rail-sort-label">
            Order by
          </label>
          <select
            id="issue-order-by"
            className="issue-rail-sort-select"
            data-testid="issue-sort-select"
            aria-label="Order by"
            value={sortBy}
            onChange={(e) => {
              handleSortByChange(e.target.value as IssueSortOption);
            }}
          >
            <option value="updated">Updated</option>
            <option value="created">Created</option>
            <option value="priority">Priority</option>
            <option value="state">State</option>
            <option value="key">Key</option>
            <option value="due_date">Due Date</option>
            <option value="rank">Rank</option>
          </select>
        </div>

        <button
          type="button"
          className="issue-sort-dir-btn"
          data-testid="issue-sort-dir-btn"
          aria-label={`Sort direction: ${sortDir === 'asc' ? 'ascending' : 'descending'}`}
          onClick={handleSortDirToggle}
        >
          {sortDir === 'asc' ? '↑' : '↓'}
        </button>

        <button
          type="button"
          className="issue-rail-refresh-btn"
          data-testid="issue-rail-refresh-btn"
          aria-label="Refresh issue list"
          onClick={() => {
            if (onRefresh) {
              onRefresh();
            } else if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('kb:refresh-issues'));
            }
          }}
        >
          ↻
        </button>

        {onCreateIssue && (
          <button
            type="button"
            className="issue-rail-new-btn"
            data-testid="issue-rail-new-btn"
            aria-label="New work item"
            onClick={onCreateIssue}
          >
            +
          </button>
        )}
      </div>

      {/* 2-Line Issue List Cards */}
      <div className="list-table" role="table" aria-label="Work items">
        <div className="issue-card-list list-rows" role="rowgroup">
        {sortedIssues.map((issue) => {
          const isFav = favoriteKeys.has(issue.key);
          const isSelected = selectedSet.has(issue.key);
          const isActive = activeKey === issue.key || focusedKey === issue.key;

          const handleStateClick = (e: React.MouseEvent<HTMLButtonElement>): void => {
            e.stopPropagation();
            const rect = e.currentTarget.getBoundingClientRect();
            if (onOpenFieldPopover) {
              onOpenFieldPopover('state', issue, rect);
            } else {
              setLocalAnchor(rect);
              setLocalPopoverIssue(issue);
            }
          };

          return (
            <div
              key={issue.id || issue.key}
              role="row"
              tabIndex={focusedKey === issue.key ? 0 : -1}
              className={`issue-list-card list-row ${isSelected ? 'list-row--selected' : ''} ${
                isActive ? 'list-row--active' : ''
              }`}
              data-issue-key={issue.key}
              data-testid={`issue-list-card-${issue.key}`}
              onClick={(e) => {
                const target = e.target as HTMLElement;
                if (target.closest('input, button, a')) return;
                onOpenPeek?.(issue.key);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onOpenPeek?.(issue.key);
                }
              }}
            >
              {/* Line 1: Priority Icon, Monospace Key, Right-aligned interactive state pill & Favorite star */}
              <div className="issue-card-line-1" role="cell">
                <div className="issue-card-meta-left">
                  {onToggleSelect && (
                    <input
                      type="checkbox"
                      className="issue-card-checkbox"
                      aria-label={`Select ${issue.key}`}
                      checked={isSelected}
                      onChange={(e) => {
                        e.stopPropagation();
                        onToggleSelect(issue.key, e.target.checked);
                      }}
                    />
                  )}
                  <PriorityIcon
                    priority={issue.priority.slug}
                    size={14}
                    className="list-row-priority-icon"
                  />
                  <span className="mono issue-card-key">{issue.key}</span>
                </div>

                <div className="issue-card-meta-right">
                  {(() => {
                    const rawCaps = issue.capabilities ?? capabilities;
                    let canTransition = true;
                    if (rawCaps !== undefined) {
                      if (Array.isArray(rawCaps)) {
                        canTransition = (rawCaps as readonly unknown[]).some((c) => {
                          const str = typeof c === 'string' ? c.toUpperCase() : '';
                          return str === 'TRANSITION' || str === 'EDIT' || str === 'ADMIN';
                        });
                      } else {
                        const set = rawCaps as ReadonlySet<string>;
                        canTransition =
                          set.has('TRANSITION') ||
                          set.has('EDIT') ||
                          set.has('ADMIN') ||
                          set.has('transition') ||
                          set.has('edit') ||
                          set.has('admin');
                      }
                    }

                    if (!canTransition) {
                      return (
                        <span
                          className="list-row-state-readonly"
                          data-testid={`list-row-state-readonly-${issue.key}`}
                          aria-label={`Status: ${issue.state.name}`}
                          title={`Status: ${issue.state.name}`}
                        >
                          <StateBadge
                            state={issue.state}
                            showLabel={false}
                            className="list-row-state-icon"
                          />
                        </span>
                      );
                    }

                    return (
                      <button
                        type="button"
                        className="list-row-state-btn"
                        data-testid={`list-row-state-btn-${issue.key}`}
                        aria-label={`Status: ${issue.state.name}`}
                        title={`Status: ${issue.state.name}`}
                        onClick={handleStateClick}
                      >
                        <StateBadge
                          state={issue.state}
                          showLabel={false}
                          className="list-row-state-icon"
                        />
                      </button>
                    );
                  })()}

                  <button
                    type="button"
                    className={`issue-card-star-btn ${isFav ? 'issue-card-star-btn--active' : ''}`}
                    data-testid="favorite-issue-toggle"
                    aria-label={isFav ? `Unfavorite ${issue.key}` : `Favorite ${issue.key}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleFavorite(issue.key);
                    }}
                  >
                    {isFav ? '⭐' : '☆'}
                  </button>
                </div>
              </div>

              {/* Line 2: Summary */}
              <div className="issue-card-line-2" role="cell">
                <span className="issue-card-summary">{issue.summary}</span>
              </div>
            </div>
          );
        })}
        </div>
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

      {/* Local State Popover Fallback (preserving KAN-44) */}
      {localPopoverIssue && (
        <QuickFieldPopover
          isOpen={Boolean(localPopoverIssue)}
          field="state"
          anchorRect={localAnchor}
          issue={localPopoverIssue}
          onClose={() => {
            setLocalPopoverIssue(null);
          }}
          onSelect={(field, value) => {
            if (field === 'state' && typeof value === 'string') {
              onStateSelect?.(localPopoverIssue.key, value);
            }
          }}
          states={projectStates}
        />
      )}
    </div>
  );
}
