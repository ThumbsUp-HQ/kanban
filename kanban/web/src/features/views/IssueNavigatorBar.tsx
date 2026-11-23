/**
 * Unified Top Issue Navigator Bar (KAN-52, KAN-308 Problems 2 & 3).
 * Replaces single-select state dropdown with searchable multi-select StateFilterPopover
 * and renders non-intrusive hidden-completed-banner during search.
 */

import React, { useMemo, useCallback, useState, type JSX } from 'react';
import {
  buildPreferenceFromExplicitStateTokens,
  classifyStateFilterPreset,
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  isIssueStateVisible,
  readProjectStateFilterCookie,
  writeProjectStateFilterCookie,
  type ProjectStateFilterPreference,
} from './issueFilterCookie';
import {
  hasExplicitStatePredicate,
  matchesIssueQuery,
} from './predicateParser';
import {
  StateFilterPopover,
  resolveEffectiveProjectStates,
} from './StateFilterPopover';
import { CsvImportExportModal } from './CsvImportExportModal';
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
  stateFilter?: ProjectStateFilterPreference | undefined;
  onStateFilterChange?: ((pref: ProjectStateFilterPreference) => void) | undefined;
  onStatePopoverOpenChange?: ((open: boolean) => void) | undefined;
  hiddenCompletedCount?: number | undefined;
  hiddenExactMatch?: { key: string; stateName: string } | null | undefined;
  onShowAllStates?: (() => void) | undefined;
  workspaceScope?: string | undefined;
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
  projectKey,
  issues = [],
  projectStates = [],
  modulesEnabled = true,
  activeFilters = {},
  onFiltersChange,
  stateFilter: controlledStateFilter,
  onStateFilterChange,
  onStatePopoverOpenChange,
  hiddenCompletedCount: propHiddenCompletedCount,
  hiddenExactMatch: propHiddenExactMatch,
  onShowAllStates,
  workspaceScope,
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
  const effectiveStates = useMemo(
    () => resolveEffectiveProjectStates(projectStates),
    [projectStates],
  );

  const [internalStateFilter, setInternalStateFilter] = useState<ProjectStateFilterPreference>(() => {
    if (controlledStateFilter) {
      return controlledStateFilter;
    }
    if (activeFilters.state && activeFilters.state.length > 0) {
      return buildPreferenceFromExplicitStateTokens(activeFilters.state, effectiveStates);
    }
    return (
      readProjectStateFilterCookie(projectKey, { workspaceScope }) ??
      createActionableStateFilterPreference()
    );
  });

  const effectiveStateFilter = controlledStateFilter ?? internalStateFilter;

  const handleStateFilterUpdate = useCallback(
    (nextPref: ProjectStateFilterPreference) => {
      setInternalStateFilter(nextPref);
      writeProjectStateFilterCookie(projectKey, nextPref, { workspaceScope });
      onStateFilterChange?.(nextPref);

      if (onFiltersChange) {
        const classification = classifyStateFilterPreset(nextPref, effectiveStates);
        if (classification.preset === 'all') {
          const nextFilters: ActiveFilters = Object.fromEntries(
            Object.entries(activeFilters).filter(([k]) => k !== 'state'),
          );
          onFiltersChange(nextFilters);
        } else if (classification.preset === 'actionable') {
          onFiltersChange({
            ...activeFilters,
            state: ['active'],
          });
        } else {
          onFiltersChange({
            ...activeFilters,
            state: classification.selectedStates.map((s) => s.id),
          });
        }
      }
    },
    [
      projectKey,
      workspaceScope,
      onStateFilterChange,
      onFiltersChange,
      effectiveStates,
      activeFilters,
    ],
  );

  // Compute hidden completed/cancelled matches during search when props are not explicitly provided
  const computedHiddenMatches = useMemo(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      return { count: 0, exactMatch: null as { key: string; stateName: string } | null };
    }
    if (queryMode === 'query' && hasExplicitStatePredicate(trimmed)) {
      return { count: 0, exactMatch: null as { key: string; stateName: string } | null };
    }

    const lowerQuery = trimmed.toLowerCase();
    const hiddenMatching: IssueItem[] = [];

    for (const issue of issues) {
      const iState = (issue as { state?: StateSummary }).state;
      if (isIssueStateVisible(iState, effectiveStateFilter)) {
        continue;
      }

      const matchesSearch =
        queryMode === 'query'
          ? matchesIssueQuery(trimmed, issue, projectKey)
          : issue.key.toLowerCase().includes(lowerQuery) ||
            issue.summary.toLowerCase().includes(lowerQuery) ||
            (issue.description_markdown ?? '').toLowerCase().includes(lowerQuery);

      if (matchesSearch) {
        hiddenMatching.push(issue);
      }
    }

    const exact =
      hiddenMatching.find((i) => i.key.toLowerCase() === lowerQuery) ?? null;

    return {
      count: hiddenMatching.length,
      exactMatch: exact
        ? { key: exact.key, stateName: exact.state.name || exact.state.group }
        : null,
    };
  }, [issues, searchQuery, queryMode, effectiveStateFilter, projectKey]);

  const hiddenCount = propHiddenCompletedCount ?? computedHiddenMatches.count;
  const hiddenExact =
    propHiddenExactMatch !== undefined
      ? propHiddenExactMatch
      : computedHiddenMatches.exactMatch;

  const handleShowAllHidden = useCallback(() => {
    if (onShowAllStates) {
      onShowAllStates();
      return;
    }
    handleStateFilterUpdate(createAllStatesFilterPreference());
  }, [onShowAllStates, handleStateFilterUpdate]);

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

  const currentPriority = activeFilters.priority?.[0] ?? 'all';
  const currentAssignee = activeFilters.assignee?.[0] ?? 'all';
  const currentLabel = activeFilters.label?.[0] ?? 'all';
  const currentCycle = activeFilters.cycle?.[0] ?? 'all';
  const currentModule = activeFilters.module?.[0] ?? 'all';
  const [filtersExpanded, setFiltersExpanded] = React.useState<boolean>(false);
  const [csvModalTab, setCsvModalTab] = useState<'export' | 'import' | null>(null);

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
              placeholder='e.g. project = "KAN" AND status = "Todo" or -state:completed priority:high'
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

        {/* CSV Import & Export Actions */}
        <div className="navigator-csv-actions" role="group" aria-label="CSV actions">
          <button
            type="button"
            className="navigator-csv-btn"
            data-testid="navigator-export-btn"
            aria-label="Export Issues to CSV"
            onClick={() => { setCsvModalTab('export'); }}
          >
            Export
          </button>
          <button
            type="button"
            className="navigator-csv-btn"
            data-testid="navigator-import-btn"
            aria-label="Import Issues from CSV"
            onClick={() => { setCsvModalTab('import'); }}
          >
            Import
          </button>
        </div>

        {/* Mobile / Compact Landscape Filters Toggle */}
        {queryMode === 'basic' && (
          <button
            type="button"
            className={`navigator-filters-toggle ${filtersExpanded ? 'navigator-filters-toggle--active' : ''}`}
            data-testid="navigator-filters-toggle"
            aria-expanded={filtersExpanded}
            onClick={() => {
              setFiltersExpanded((prev) => !prev);
            }}
          >
            <span>Filters</span>
            <span aria-hidden="true">{filtersExpanded ? '▲' : '▼'}</span>
          </button>
        )}
      </div>

      {/* Basic Mode Structured Dropdowns & Chips */}
      {queryMode === 'basic' && (
        <div
          className={`navigator-filters-row ${filtersExpanded ? 'navigator-filters-row--expanded' : ''}`}
          data-testid="navigator-filters-row"
        >
          {/* Multi-Select Searchable State Checkboxes Popover */}
          <StateFilterPopover
            projectStates={projectStates}
            issues={issues}
            value={effectiveStateFilter}
            onChange={handleStateFilterUpdate}
            onOpenChange={onStatePopoverOpenChange}
          />

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

      {/* Hidden Completed / Cancelled Matches Banner */}
      {hiddenCount > 0 && (
        <div
          className="navigator-hidden-banner"
          data-testid="hidden-completed-banner"
          role="status"
          aria-live="polite"
        >
          <span className="navigator-hidden-banner-text">
            {hiddenExact
              ? `${hiddenExact.key} is hidden (${hiddenExact.stateName}) - ${String(hiddenCount)} completed/cancelled issue(s) hidden`
              : `${String(hiddenCount)} completed/cancelled issue(s) hidden`}
          </span>
          <button
            type="button"
            className="navigator-hidden-show-all-btn"
            data-testid="hidden-completed-show-all-btn"
            onClick={handleShowAllHidden}
          >
            Show all
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

      {csvModalTab && (
        <CsvImportExportModal
          isOpen={csvModalTab !== null}
          onClose={() => { setCsvModalTab(null); }}
          projectKey={projectKey}
          workspaceScope={workspaceScope}
          activeFilters={activeFilters}
          searchQuery={searchQuery}
          initialTab={csvModalTab}
        />
      )}
    </div>
  );
}
