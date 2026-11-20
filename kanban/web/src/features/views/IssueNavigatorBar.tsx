/**
 * Unified Top Issue Navigator Bar (KAN-52).
 * Replaces double-stacked FilterDisplayBar and ListView Filter & Group bars.
 */

import React, { useMemo, useCallback, type JSX } from 'react';
import type { IssueItem, SavedView, StateSummary } from './viewsApi';
import type { ActiveFilters } from './FilterDisplayBar';
import './IssueNavigatorBar.css';

export interface IssueNavigatorBarProps {
  projectKey: string;
  issues?: IssueItem[];
  projectStates?: StateSummary[];
  modulesEnabled?: boolean;
  activeFilters?: ActiveFilters;
  onFiltersChange?: (filters: ActiveFilters) => void;
  searchQuery?: string;
  onSearchQueryChange?: (q: string) => void;
  queryMode?: 'basic' | 'query';
  onQueryModeChange?: (mode: 'basic' | 'query') => void;
  favoritesOnly?: boolean;
  onToggleFavoritesOnly?: () => void;
  savedViews?: SavedView[];
  activeViewId?: string | null;
  onSelectSavedView?: (viewId: string) => void;
  onSearchSubmit?: () => void;
  className?: string;
}

export function IssueNavigatorBar({
  issues = [],
  projectStates = [],
  modulesEnabled = true,
  activeFilters = {},
  onFiltersChange,
  searchQuery = '',
  onSearchQueryChange,
  queryMode = 'basic',
  onQueryModeChange,
  favoritesOnly = false,
  onToggleFavoritesOnly,
  savedViews = [],
  activeViewId = null,
  onSelectSavedView,
  onSearchSubmit,
  className = '',
}: IssueNavigatorBarProps): JSX.Element {
  // Extract distinct filter values from issues
  const distinctAssignees = useMemo(() => {
    const map = new Map<string, string>();
    for (const issue of issues) {
      for (const asg of issue.assignees ?? []) {
        if (asg.kind === 'principal') {
          map.set(asg.principal.handle, asg.principal.display_name || asg.principal.handle);
        } else {
          map.set(asg.free_text, asg.free_text);
        }
      }
    }
    return Array.from(map.entries()).map(([handle, name]) => ({ handle, name }));
  }, [issues]);

  const distinctLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const issue of issues) {
      for (const lbl of issue.labels ?? []) {
        map.set(lbl.name, lbl.name);
      }
    }
    return Array.from(map.values());
  }, [issues]);

  const distinctCycles = useMemo(() => {
    const map = new Map<string, string>();
    for (const issue of issues) {
      if (issue.cycle_id) {
        map.set(issue.cycle_id, issue.cycle?.name ?? `Cycle ${issue.cycle_id.slice(0, 6)}`);
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [issues]);

  const distinctModules = useMemo(() => {
    const map = new Map<string, string>();
    for (const issue of issues) {
      for (const m of issue.modules ?? []) {
        map.set(m.id, m.name);
      }
      for (const mId of issue.module_ids ?? []) {
        if (!map.has(mId)) {
          map.set(mId, `Module ${mId.slice(0, 6)}`);
        }
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [issues]);

  const handleFilterChange = useCallback(
    (field: keyof ActiveFilters, value: string) => {
      if (!onFiltersChange) return;
      if (value === 'all') {
        const next: ActiveFilters = Object.fromEntries(
          Object.entries(activeFilters).filter(([k]) => k !== field),
        );
        onFiltersChange(next);
        return;
      }
      onFiltersChange({
        ...activeFilters,
        [field]: [value],
      });
    },
    [activeFilters, onFiltersChange],
  );

  const currentState = activeFilters.state?.[0] ?? 'all';
  const currentPriority = activeFilters.priority?.[0] ?? 'all';
  const currentAssignee = activeFilters.assignee?.[0] ?? 'all';
  const currentLabel = activeFilters.label?.[0] ?? 'all';
  const currentCycle = activeFilters.cycle?.[0] ?? 'all';
  const currentModule = activeFilters.module?.[0] ?? 'all';

  return (
    <div
      className={`issue-navigator-bar ${className}`}
      data-testid="issue-navigator-bar"
    >
      {/* Top Search & Mode Row */}
      <div className="navigator-top-row">
        <form
          className="navigator-search-form"
          onSubmit={(e) => {
            e.preventDefault();
            onSearchSubmit?.();
          }}
        >
          {queryMode === 'basic' ? (
            <input
              type="search"
              className="navigator-search-input"
              data-testid="navigator-search-input"
              placeholder="Search issues by summary, key, or details..."
              aria-label="Search issues"
              value={searchQuery}
              onChange={(e) => {
                onSearchQueryChange?.(e.target.value);
              }}
            />
          ) : (
            <input
              type="text"
              className="navigator-query-input"
              data-testid="navigator-query-input"
              placeholder='e.g. project = "KAN" AND status = "Todo" or state:started priority:high "mars"'
              aria-label="Structured query search"
              value={searchQuery}
              onChange={(e) => {
                onSearchQueryChange?.(e.target.value);
              }}
            />
          )}

          <button
            type="submit"
            className="navigator-search-btn"
            data-testid="navigator-search-btn"
            aria-label="Search"
          >
            Search
          </button>
        </form>

        {/* Basic / Query Mode Toggle */}
        <div
          className="navigator-mode-group"
          data-testid="navigator-mode-toggle"
          role="group"
          aria-label="Search mode"
        >
          <button
            type="button"
            className={`navigator-mode-btn ${queryMode === 'basic' ? 'navigator-mode-btn--active' : ''}`}
            data-testid="mode-basic-btn"
            aria-pressed={queryMode === 'basic'}
            onClick={() => {
              onQueryModeChange?.('basic');
            }}
          >
            Basic
          </button>
          <button
            type="button"
            className={`navigator-mode-btn ${queryMode === 'query' ? 'navigator-mode-btn--active' : ''}`}
            data-testid="mode-query-btn"
            aria-pressed={queryMode === 'query'}
            onClick={() => {
              onQueryModeChange?.('query');
            }}
          >
            Query
          </button>
        </div>
      </div>

      {/* Basic Mode Structured Dropdowns & Chips */}
      {queryMode === 'basic' && (
        <div className="navigator-filters-row" data-testid="navigator-filters-row">
          {/* State */}
          <select
            className="navigator-filter-select"
            data-testid="navigator-filter-state"
            aria-label="Filter by state"
            value={currentState}
            onChange={(e) => {
              handleFilterChange('state', e.target.value);
            }}
          >
            <option value="all">All States</option>
            {projectStates.length > 0 ? (
              projectStates.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.name}
                </option>
              ))
            ) : (
              <>
                <option value="backlog">Backlog</option>
                <option value="todo">Todo</option>
                <option value="in-progress">In Progress</option>
                <option value="in-review">In Review</option>
                <option value="done">Done</option>
                <option value="cancelled">Cancelled</option>
              </>
            )}
          </select>

          {/* Priority */}
          <select
            className="navigator-filter-select"
            data-testid="navigator-filter-priority"
            aria-label="Filter by priority"
            value={currentPriority}
            onChange={(e) => {
              handleFilterChange('priority', e.target.value);
            }}
          >
            <option value="all">All Priorities</option>
            <option value="urgent">🔥 Urgent</option>
            <option value="high">⚡ High</option>
            <option value="medium">🔹 Medium</option>
            <option value="low">🔽 Low</option>
            <option value="none">➖ None</option>
          </select>

          {/* Assignee */}
          <select
            className="navigator-filter-select"
            data-testid="navigator-filter-assignee"
            aria-label="Filter by assignee"
            value={currentAssignee}
            onChange={(e) => {
              handleFilterChange('assignee', e.target.value);
            }}
          >
            <option value="all">All Assignees</option>
            <option value="unassigned">Unassigned</option>
            {distinctAssignees.map((asg) => (
              <option key={asg.handle} value={asg.handle}>
                {asg.name}
              </option>
            ))}
          </select>

          {/* Label */}
          <select
            className="navigator-filter-select"
            data-testid="navigator-filter-label"
            aria-label="Filter by label"
            value={currentLabel}
            onChange={(e) => {
              handleFilterChange('label', e.target.value);
            }}
          >
            <option value="all">All Labels</option>
            {distinctLabels.map((lbl) => (
              <option key={lbl} value={lbl}>
                {lbl}
              </option>
            ))}
          </select>

          {/* Cycle */}
          <select
            className="navigator-filter-select"
            data-testid="navigator-filter-cycle"
            aria-label="Filter by cycle"
            value={currentCycle}
            onChange={(e) => {
              handleFilterChange('cycle', e.target.value);
            }}
          >
            <option value="all">All Cycles</option>
            {distinctCycles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>

          {/* Module */}
          {modulesEnabled && (
            <select
              className="navigator-filter-select"
              data-testid="navigator-filter-module"
              aria-label="Filter by module"
              value={currentModule}
              onChange={(e) => {
                handleFilterChange('module', e.target.value);
              }}
            >
              <option value="all">All Modules</option>
              {distinctModules.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          )}

          {/* Favorites Only Toggle */}
          <button
            type="button"
            className={`navigator-fav-toggle ${favoritesOnly ? 'navigator-fav-toggle--active' : ''}`}
            data-testid="filter-favorites-toggle"
            aria-pressed={favoritesOnly}
            onClick={onToggleFavoritesOnly}
          >
            <span>{favoritesOnly ? '⭐ Favorites only' : '☆ Favorites only'}</span>
          </button>
        </div>
      )}

      {/* Saved Views Chip Strip */}
      {savedViews.length > 0 && (
        <div
          className="navigator-saved-views-strip"
          data-testid="navigator-saved-views-strip"
          role="region"
          aria-label="Saved Views"
        >
          <span className="navigator-saved-views-label">Views:</span>
          {savedViews.map((v) => {
            const isActive = activeViewId === v.id;
            return (
              <button
                key={v.id}
                type="button"
                className={`navigator-view-chip ${isActive ? 'navigator-view-chip--active' : ''}`}
                data-testid={`saved-view-chip-${v.id}`}
                aria-pressed={isActive}
                onClick={() => {
                  onSelectSavedView?.(v.id);
                }}
              >
                {v.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
