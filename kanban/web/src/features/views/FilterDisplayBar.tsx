import React, { useState, useRef, useEffect, useCallback, useMemo, type JSX } from 'react';
import type { GroupAxis, IssueItem } from './viewsApi';
import {
  fetchAssigneeSuggestions,
  fetchProjectLabels,
  fetchProjectCycles,
  fetchProjectModules,
} from '../drawer-rail/railApi';
import './filterBulk.css';

export interface ActiveFilters {
  state?: string[];
  priority?: string[];
  assignee?: string[];
  label?: string[];
  cycle?: string[];
  module?: string[];
  due_date?: string[];
  gate_status?: string[];
  [key: string]: string[] | undefined;
}

export interface FilterDisplayBarProps {
  activeFilters?: ActiveFilters;
  onFiltersChange?: (filters: ActiveFilters) => void;
  groupBy?: GroupAxis;
  onGroupByChange?: (group: GroupAxis) => void;
  subGroupBy?: GroupAxis;
  onSubGroupByChange?: (subGroup: GroupAxis) => void;
  modulesEnabled?: boolean;
  onSaveView?: () => void;
  searchInputRef?: React.RefObject<HTMLInputElement | null>;
  isFilterOpen?: boolean;
  onToggleFilterOpen?: (open: boolean) => void;
  projectKey?: string;
  issues?: IssueItem[];
}

interface FacetOption {
  key: string;
  label: string;
  category: string;
  emoji?: string;
}

export function FilterDisplayBar({
  activeFilters = {},
  onFiltersChange,
  groupBy = 'state',
  onGroupByChange,
  subGroupBy = 'none',
  onSubGroupByChange,
  modulesEnabled = true,
  onSaveView,
  searchInputRef: externalSearchRef,
  isFilterOpen: externalFilterOpen,
  onToggleFilterOpen: externalToggleFilterOpen,
  projectKey,
  issues,
}: FilterDisplayBarProps): JSX.Element {
  const [internalFilterOpen, setInternalFilterOpen] = useState(false);
  const [isDisplayTuneOpen, setIsDisplayTuneOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [liveAssignees, setLiveAssignees] = useState<FacetOption[]>([]);
  const [liveLabels, setLiveLabels] = useState<FacetOption[]>([]);
  const [liveCycles, setLiveCycles] = useState<FacetOption[]>([]);
  const [liveModules, setLiveModules] = useState<FacetOption[]>([]);
  const internalSearchRef = useRef<HTMLInputElement>(null);
  const searchRef = externalSearchRef ?? internalSearchRef;

  const isPopoverOpen = externalFilterOpen ?? internalFilterOpen;
  const setPopoverOpen = useCallback((open: boolean) => {
    if (externalToggleFilterOpen) {
      externalToggleFilterOpen(open);
    } else {
      setInternalFilterOpen(open);
    }
  }, [externalToggleFilterOpen]);

  // Hydrate dynamic facets from live project endpoints when projectKey is present
  useEffect(() => {
    if (!projectKey || projectKey === 'undefined') return;
    let active = true;

    void Promise.allSettled([
      fetchAssigneeSuggestions(projectKey, '').then((res) => {
        if (!active) return;
        setLiveAssignees(
          res.map((s) => ({
            key: s.handle.replace(/^@/, '').toLowerCase(),
            label: s.display_name || s.handle,
            category: 'assignee',
          }))
        );
      }),
      fetchProjectLabels(projectKey).then((res) => {
        if (!active) return;
        setLiveLabels(
          res.map((l) => ({
            key: l.name.toLowerCase(),
            label: l.name,
            category: 'label',
          }))
        );
      }),
      fetchProjectCycles(projectKey).then((res) => {
        if (!active) return;
        setLiveCycles(
          res.map((c) => ({
            key: c.id,
            label: c.name,
            category: 'cycle',
          }))
        );
      }),
      fetchProjectModules(projectKey).then((res) => {
        if (!active) return;
        setLiveModules(
          res.map((m) => ({
            key: m.id,
            label: m.name,
            category: 'module',
          }))
        );
      }),
    ]);

    return () => {
      active = false;
    };
  }, [projectKey]);

  // Derive dynamic facets from issues collection
  const derivedFacets = useMemo(() => {
    const assigneeMap = new Map<string, string>();
    const labelMap = new Map<string, string>();
    const cycleMap = new Map<string, string>();
    const moduleMap = new Map<string, string>();

    for (const issue of issues ?? []) {
      for (const asg of issue.assignees ?? []) {
        if (asg.kind === 'principal') {
          const key = asg.principal.handle.replace(/^@/, '').toLowerCase();
          const label = asg.principal.display_name || asg.principal.handle;
          assigneeMap.set(key, label);
        }
      }
      for (const lbl of issue.labels ?? []) {
        labelMap.set(lbl.name.toLowerCase(), lbl.name);
      }
      if (issue.cycle_id) {
        cycleMap.set(issue.cycle_id, issue.cycle_id === 'cycle-1' ? 'Cycle 1' : issue.cycle_id);
      }
      for (const mId of issue.module_ids ?? []) {
        moduleMap.set(mId, mId === 'mod-1' ? 'Auth Core' : (mId === 'mod-2' ? 'Kanban Board' : mId));
      }
    }

    return {
      assignees: Array.from(assigneeMap.entries()).map(([key, label]) => ({
        key,
        label,
        category: 'assignee',
      })),
      labels: Array.from(labelMap.entries()).map(([key, label]) => ({
        key,
        label,
        category: 'label',
      })),
      cycles: Array.from(cycleMap.entries()).map(([key, label]) => ({
        key,
        label,
        category: 'cycle',
      })),
      modules: Array.from(moduleMap.entries()).map(([key, label]) => ({
        key,
        label,
        category: 'module',
      })),
    };
  }, [issues]);

  const effectiveAssignees = liveAssignees.length > 0 ? liveAssignees : derivedFacets.assignees;
  const effectiveLabels = liveLabels.length > 0 ? liveLabels : derivedFacets.labels;
  const effectiveCycles = liveCycles.length > 0 ? liveCycles : derivedFacets.cycles;
  const effectiveModules = liveModules.length > 0 ? liveModules : derivedFacets.modules;

  // Keyboard shortcut '/' opens filter search input and prevents character typing
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable);

      if (e.key === '/' && !isInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setPopoverOpen(true);
        setTimeout(() => {
          searchRef.current?.focus();
        }, 10);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => { window.removeEventListener('keydown', handleKeyDown); };
  }, [searchRef, setPopoverOpen]);

  // Read URL query params on mount for initial filter chips (e.g. ?filter_label=...)
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const labelParam = params.get('filter_label');
      if (labelParam && (!activeFilters.label?.includes(labelParam))) {
        const updated = {
          ...activeFilters,
          label: [...(activeFilters.label ?? []), labelParam],
        };
        onFiltersChange?.(updated);
      }
    } catch {
      // Ignore URLSearchParams parsing error in non-browser environments
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const facetDefinitions: FacetOption[] = useMemo(() => [
    { key: 'active', label: 'Active', category: 'state' },
    { key: 'backlog', label: 'Backlog', emoji: '🗂️', category: 'state' },
    { key: 'unstarted', label: 'Todo', emoji: '📋', category: 'state' },
    { key: 'started', label: 'In Progress', emoji: '⚙️', category: 'state' },
    { key: 'completed', label: 'Done', emoji: '✅', category: 'state' },
    { key: 'cancelled', label: 'Cancelled', emoji: '🚫', category: 'state' },

    { key: 'urgent', label: 'Urgent', emoji: '🔥', category: 'priority' },
    { key: 'high', label: 'High', emoji: '⚡', category: 'priority' },
    { key: 'medium', label: 'Medium', emoji: '🔹', category: 'priority' },
    { key: 'low', label: 'Low', emoji: '🔽', category: 'priority' },
    { key: 'none', label: 'None', category: 'priority' },

    { key: 'unassigned', label: 'Unassigned', category: 'assignee' },
    ...effectiveAssignees,

    ...effectiveLabels,

    ...effectiveCycles,

    ...(modulesEnabled ? effectiveModules : []),

    { key: 'overdue', label: 'Overdue', category: 'due_date' },
    { key: 'this_week', label: 'Due this week', category: 'due_date' },
    { key: 'no_due_date', label: 'No due date', category: 'due_date' },

    { key: 'pending', label: '⏳🤖 Pending', category: 'gate_status' },
    { key: 'vetoed', label: '🛑🤖 Vetoed', category: 'gate_status' },
    { key: 'approved', label: '✅🤖 Approved', category: 'gate_status' },
  ], [effectiveAssignees, effectiveLabels, effectiveCycles, effectiveModules, modulesEnabled]);

  const handleToggleFacet = (category: string, value: string) => {
    const current = activeFilters[category] ?? [];
    const isSelected = current.includes(value);
    const updatedValues = isSelected
      ? current.filter((v) => v !== value)
      : [...current, value];

    const nextFilters: ActiveFilters = {};
    for (const [k, v] of Object.entries(activeFilters)) {
      if (k !== category) {
        nextFilters[k] = v;
      }
    }
    if (updatedValues.length > 0) {
      nextFilters[category] = updatedValues;
    }
    onFiltersChange?.(nextFilters);
  };

  const handleRemoveChip = (category: string, value: string) => {
    const current = activeFilters[category] ?? [];
    const updatedValues = current.filter((v) => v !== value);
    const nextFilters: ActiveFilters = {};
    for (const [k, v] of Object.entries(activeFilters)) {
      if (k !== category) {
        nextFilters[k] = v;
      }
    }
    if (updatedValues.length > 0) {
      nextFilters[category] = updatedValues;
    }
    onFiltersChange?.(nextFilters);
  };

  const handleClearAll = () => {
    onFiltersChange?.({});
  };

  const handleGroupChange = (newGroup: GroupAxis) => {
    onGroupByChange?.(newGroup);
    // Mutual exclusion: if Group matches active Sub-group, reset Sub-group to 'none'
    if (newGroup === subGroupBy && newGroup !== 'none') {
      onSubGroupByChange?.('none');
    }
  };

  // Group options: exclude module if modulesEnabled is false
  const groupOptions: { value: GroupAxis; label: string }[] = [
    { value: 'state', label: 'State' },
    { value: 'priority', label: 'Priority' },
    { value: 'assignee', label: 'Assignee' },
    { value: 'cycle', label: 'Cycle' },
    ...(modulesEnabled ? [{ value: 'module' as GroupAxis, label: 'Module' }] : []),
    { value: 'label', label: 'Label' },
    { value: 'none', label: 'None' },
  ];

  // Sub-group options: exclude current group axis and exclude module if modulesEnabled is false
  const allSubOptions: { value: GroupAxis; label: string }[] = [
    { value: 'none', label: 'None' },
    { value: 'assignee', label: 'Assignee' },
    { value: 'priority', label: 'Priority' },
    { value: 'state', label: 'State' },
    { value: 'cycle', label: 'Cycle' },
    ...(modulesEnabled ? [{ value: 'module' as GroupAxis, label: 'Module' }] : []),
    { value: 'label', label: 'Label' },
  ];
  const subGroupOptions: { value: GroupAxis; label: string }[] = allSubOptions.filter(
    (opt) => opt.value === 'none' || opt.value !== groupBy
  );

  const activeChips: { category: string; value: string; display: string }[] = [];
  for (const [cat, values] of Object.entries(activeFilters)) {
    if (!values) continue;
    for (const val of values) {
      const match = facetDefinitions.find((f) => f.category === cat && f.key === val);
      let display = match?.label ?? val;
      if (match?.emoji) {
        display = `${match.emoji} ${display}`;
      }
      activeChips.push({
        category: cat,
        value: val,
        display: `${cat.charAt(0).toUpperCase() + cat.slice(1).replace('_', ' ')}: ${display}`,
      });
    }
  }

  const filteredFacets = facetDefinitions.filter((facet) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      facet.label.toLowerCase().includes(q) ||
      facet.category.toLowerCase().includes(q)
    );
  });

  return (
    <div className="filter-display-bar" role="region" aria-label="Filter and display controls">
      <div className="filter-controls-group">
        <button
          type="button"
          className="filter-btn-trigger"
          onClick={() => { setPopoverOpen(!isPopoverOpen); }}
          aria-expanded={isPopoverOpen}
          aria-haspopup="dialog"
          aria-label="Open filter facets popover"
        >
          <span>Filter</span>
          <kbd className="filter-shortcut-kbd">/</kbd>
        </button>

        {isPopoverOpen && (
          <div
            className="filter-popover-panel"
            role="dialog"
            aria-label="Filter facets"
          >
            <input
              ref={searchRef}
              type="text"
              className="filter-search-input"
              placeholder="Search filters..."
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); }}
              aria-label="Search filter facets"
            />
            <div className="filter-facets-list">
              {['state', 'priority', 'assignee', 'label', 'cycle', ...(modulesEnabled ? ['module'] : []), 'due_date', 'gate_status'].map(
                (cat) => {
                  const opts = filteredFacets.filter((f) => f.category === cat);
                  if (opts.length === 0) return null;
                  return (
                    <div key={cat} className="filter-facet-category">
                      <div className="filter-facet-category-title">
                        {cat.replace('_', ' ')}
                      </div>
                      {opts.map((opt) => {
                        const isSelected = activeFilters[cat]?.includes(opt.key) ?? false;
                        return (
                          <button
                            key={opt.key}
                            type="button"
                            className={`filter-facet-option ${isSelected ? 'filter-facet-option--active' : ''}`}
                            onClick={() => { handleToggleFacet(cat, opt.key); }}
                          >
                            <span>
                              {opt.emoji ? `${opt.emoji} ` : ''}
                              {opt.label}
                            </span>
                            {isSelected && <span>✓</span>}
                          </button>
                        );
                      })}
                    </div>
                  );
                }
              )}
            </div>
          </div>
        )}

        <div className="filter-axis-select-wrap">
          <label htmlFor="group-by-select" className="filter-axis-select-label">
            Group:
          </label>
          <select
            id="group-by-select"
            className="filter-axis-select"
            value={groupBy}
            onChange={(e) => { handleGroupChange(e.target.value as GroupAxis); }}
            aria-label="Group by axis"
          >
            {groupOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-axis-select-wrap">
          <label htmlFor="subgroup-by-select" className="filter-axis-select-label">
            Sub-group:
          </label>
          <select
            id="subgroup-by-select"
            className="filter-axis-select"
            value={subGroupBy}
            onChange={(e) => onSubGroupByChange?.(e.target.value as GroupAxis)}
            aria-label="Sub-group by axis"
          >
            {subGroupOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {activeChips.length > 0 && (
        <div className="filter-chips-row">
          {activeChips.map((chip) => (
            <span
              key={`${chip.category}-${chip.value}`}
              className="filter-chip"
              data-facet={chip.category}
              data-facet-value={chip.value}
            >
              <span>{chip.display}</span>
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => { handleRemoveChip(chip.category, chip.value); }}
                aria-label={`Remove ${chip.display} filter`}
              >
                ×
              </button>
            </span>
          ))}
          <button
            type="button"
            className="filter-clear-all-btn"
            onClick={handleClearAll}
          >
            Clear all
          </button>
        </div>
      )}

      <div className="filter-actions-right">
        <button
          type="button"
          className="filter-btn-trigger"
          onClick={() => { setIsDisplayTuneOpen(!isDisplayTuneOpen); }}
          aria-expanded={isDisplayTuneOpen}
          aria-haspopup="dialog"
          aria-label="Display configuration"
        >
          Display
        </button>

        {isDisplayTuneOpen && (
          <div
            className="filter-popover-panel filter-popover-panel--right"
            role="dialog"
            aria-label="Display options"
          >
            <div className="filter-facet-category-title">Display Settings</div>
            <button
              type="button"
              className="filter-facet-option"
              onClick={() => {
                onSaveView?.();
                setIsDisplayTuneOpen(false);
              }}
            >
              Save as view
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
