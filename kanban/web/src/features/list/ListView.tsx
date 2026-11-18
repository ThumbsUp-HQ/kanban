import React, { useState, useMemo, useEffect, useRef, type JSX } from 'react';
import { ListRow } from './ListRow';
import type { IssueItem } from '../views/viewsApi';
import '../views/listTable.css';

export interface ListViewProps {
  issues: IssueItem[];
  projectKey?: string | undefined;
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
}

interface GroupSection {
  id: string;
  name: string;
  sortOrder: number;
  items: IssueItem[];
}

export function ListView({
  issues,
  projectKey = 'KAN',
  modulesEnabled = true,
  selectedIds = [],
  onToggleSelect,
  onCreateIssue,
  nextCursor,
  onLoadMore,
  isLoading = false,
  focusedKey,
  onOpenPeek,
  activeKey,
  canManageWorkflows = true,
}: ListViewProps): JSX.Element {
  // Collapsed state map: key is section name/id, value is boolean (true if collapsed)
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [focusedIndex, setFocusedIndex] = useState<number>(0);

  // Single-card filter dropdown state (KANBA-174)
  const [filterCardOpen, setFilterCardOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedState, setSelectedState] = useState('all');
  const [selectedPriority, setSelectedPriority] = useState('all');
  const [groupByOption, setGroupByOption] = useState<'state' | 'priority' | 'cycle' | 'module' | 'none'>('state');

  const filterCardRef = useRef<HTMLDivElement>(null);

  // Close filter popover on outside click or Escape
  useEffect(() => {
    if (!filterCardOpen) return;
    const handleOutsideClick = (e: MouseEvent): void => {
      if (
        filterCardRef.current &&
        !filterCardRef.current.contains(e.target as Node)
      ) {
        setFilterCardOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setFilterCardOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [filterCardOpen]);

  // Filter issues based on single-card filter controls
  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      // 1. Text Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesSummary = issue.summary.toLowerCase().includes(q);
        const matchesKey = issue.key.toLowerCase().includes(q);
        if (!matchesSummary && !matchesKey) return false;
      }

      // 2. Workflow State Filter
      if (selectedState !== 'all') {
        const group = issue.state.group.toLowerCase();
        const name = issue.state.name.toLowerCase();
        if (group !== selectedState && name !== selectedState && !name.includes(selectedState)) {
          return false;
        }
      }

      // 3. Priority Filter
      if (selectedPriority !== 'all') {
        const slug = issue.priority.slug.toLowerCase();
        if (slug !== selectedPriority) return false;
      }

      return true;
    });
  }, [issues, searchQuery, selectedState, selectedPriority]);

  // Default workflow state sections order
  const defaultStates: { name: string; sortOrder: number }[] = useMemo(
    () => [
      { name: 'Backlog', sortOrder: 10 },
      { name: 'Todo', sortOrder: 20 },
      { name: 'In Progress', sortOrder: 30 },
      { name: 'In Review', sortOrder: 40 },
      { name: 'Done', sortOrder: 50 },
      { name: 'Cancelled', sortOrder: 60 },
    ],
    []
  );

  // Group issues by state, priority, or none
  const sections = useMemo(() => {
    if (groupByOption === 'priority') {
      const priorityOrder = [
        { name: 'Urgent', slug: 'urgent', sortOrder: 10 },
        { name: 'High', slug: 'high', sortOrder: 20 },
        { name: 'Medium', slug: 'medium', sortOrder: 30 },
        { name: 'Low', slug: 'low', sortOrder: 40 },
        { name: 'None', slug: 'none', sortOrder: 50 },
      ];
      const prioMap = new Map<string, GroupSection>();
      for (const p of priorityOrder) {
        prioMap.set(p.slug, {
          id: `prio-${p.slug}`,
          name: p.name,
          sortOrder: p.sortOrder,
          items: [],
        });
      }
      for (const issue of filteredIssues) {
        const slug = issue.priority.slug.toLowerCase();
        const existing = prioMap.get(slug);
        if (existing) {
          existing.items.push(issue);
        } else {
          prioMap.set(slug, {
            id: `prio-${slug}`,
            name: issue.priority.label || slug,
            sortOrder: 99,
            items: [issue],
          });
        }
      }
      return Array.from(prioMap.values()).filter((s) => s.items.length > 0);
    }

    if (groupByOption === 'cycle') {
      const cycleMap = new Map<string, GroupSection>();
      for (const issue of filteredIssues) {
        const cId = issue.cycle_id ?? 'no-cycle';
        const cName = issue.cycle?.name ?? (cId === 'no-cycle' ? 'No Cycle' : `Cycle ${cId.slice(0, 6)}`);
        const existing = cycleMap.get(cId);
        if (existing) {
          existing.items.push(issue);
        } else {
          cycleMap.set(cId, {
            id: `cycle-${cId}`,
            name: cName,
            sortOrder: cId === 'no-cycle' ? 9999 : 10,
            items: [issue],
          });
        }
      }
      return Array.from(cycleMap.values()).sort((a, b) => a.sortOrder - b.sortOrder);
    }

    if (groupByOption === 'module') {
      const modMap = new Map<string, GroupSection>();
      for (const issue of filteredIssues) {
        const mods =
          issue.modules && issue.modules.length > 0
            ? issue.modules
            : issue.module_ids && issue.module_ids.length > 0
            ? issue.module_ids.map((id) => ({ id, name: `Module ${id.slice(0, 6)}` }))
            : [{ id: 'no-module', name: 'No Module' }];
        for (const m of mods) {
          const existing = modMap.get(m.id);
          if (existing) {
            existing.items.push(issue);
          } else {
            modMap.set(m.id, {
              id: `module-${m.id}`,
              name: m.name,
              sortOrder: m.id === 'no-module' ? 9999 : 10,
              items: [issue],
            });
          }
        }
      }
      return Array.from(modMap.values()).sort((a, b) => a.sortOrder - b.sortOrder);
    }

    if (groupByOption === 'none') {
      return [
        {
          id: 'all-items',
          name: 'All Work Items',
          sortOrder: 1,
          items: filteredIssues,
        },
      ];
    }

    // Default: Group issues by state, preserving known states with 0 items
    const sectionMap = new Map<string, GroupSection>();

    // Seed default sections
    for (const def of defaultStates) {
      sectionMap.set(def.name, {
        id: def.name.toLowerCase().replace(/\s+/g, '-'),
        name: def.name,
        sortOrder: def.sortOrder,
        items: [],
      });
    }

    // Populate issues
    for (const issue of filteredIssues) {
      const stateName = issue.state.name;
      const existing = sectionMap.get(stateName);
      if (existing) {
        existing.items.push(issue);
      } else {
        sectionMap.set(stateName, {
          id: stateName.toLowerCase().replace(/\s+/g, '-'),
          name: stateName,
          sortOrder: issue.state.sort_order ?? 999,
          items: [issue],
        });
      }
    }

    // Convert to sorted array
    return Array.from(sectionMap.values()).sort(
      (a, b) => a.sortOrder - b.sortOrder
    );
  }, [filteredIssues, defaultStates, groupByOption]);

  const toggleSection = (sectionName: string) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionName]: !prev[sectionName],
    }));
  };

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  // Flattened visible items for keyboard navigation
  const visibleIssues = useMemo(() => {
    const list: IssueItem[] = [];
    for (const s of sections) {
      if (!collapsedSections[s.name]) {
        list.push(...s.items);
      }
    }
    return list;
  }, [sections, collapsedSections]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex((prev) => Math.min(prev + 1, visibleIssues.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex((prev) => Math.max(prev - 1, 0));
    }
  };

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
    <div className="list-view" onKeyDown={handleKeyDown}>
      {/* Compact Top Bar with Single Filter Card Dropdown and + New (KANBA-174) */}
      <div className="list-compact-topbar" data-testid="list-compact-topbar">
        <div className="list-filter-card-wrapper" ref={filterCardRef}>
          <button
            type="button"
            className="list-filter-dropdown-btn"
            aria-expanded={filterCardOpen}
            aria-haspopup="dialog"
            aria-label="Filter & Group"
            onClick={() => { setFilterCardOpen((prev) => !prev); }}
          >
            <span>🔍 Filter & Group</span>
            <span aria-hidden="true">▾</span>
          </button>

          {filterCardOpen && (
            <div
              className="list-filter-popover"
              role="dialog"
              aria-label="Filter and Group options"
            >
              <div className="list-filter-popover-header">
                <span className="list-filter-popover-title">Filter & Group Work Items</span>
                <button
                  type="button"
                  className="list-filter-popover-close"
                  aria-label="Close filter popover"
                  onClick={() => { setFilterCardOpen(false); }}
                >
                  ✕
                </button>
              </div>

              {/* Text Search */}
              <div className="list-filter-field">
                <label htmlFor="list-search-input" className="list-filter-label">Search</label>
                <input
                  id="list-search-input"
                  type="search"
                  placeholder="Filter by title or key..."
                  value={searchQuery}
                  onChange={(e) => { setSearchQuery(e.target.value); }}
                  className="list-filter-input"
                />
              </div>

              {/* Workflow State */}
              <div className="list-filter-field">
                <label htmlFor="list-state-select" className="list-filter-label">State</label>
                <select
                  id="list-state-select"
                  value={selectedState}
                  onChange={(e) => { setSelectedState(e.target.value); }}
                  className="list-filter-select"
                >
                  <option value="all">All States</option>
                  <option value="backlog">Backlog</option>
                  <option value="unstarted">Unstarted / Todo</option>
                  <option value="started">Started / In Progress</option>
                  <option value="completed">Completed / Done</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>

              {/* Priority */}
              <div className="list-filter-field">
                <label htmlFor="list-priority-select" className="list-filter-label">Priority</label>
                <select
                  id="list-priority-select"
                  value={selectedPriority}
                  onChange={(e) => { setSelectedPriority(e.target.value); }}
                  className="list-filter-select"
                >
                  <option value="all">All Priorities</option>
                  <option value="urgent">🔥 Urgent</option>
                  <option value="high">⚡ High</option>
                  <option value="medium">🔹 Medium</option>
                  <option value="low">🔽 Low</option>
                  <option value="none">➖ None</option>
                </select>
              </div>

              {/* Group By */}
              <div className="list-filter-field">
                <label htmlFor="list-groupby-select" className="list-filter-label">Group By</label>
                <select
                  id="list-groupby-select"
                  value={groupByOption}
                  onChange={(e) => {
                    setGroupByOption(e.target.value as 'state' | 'priority' | 'cycle' | 'module' | 'none');
                  }}
                  className="list-filter-select"
                >
                  <option value="state">Workflow State</option>
                  <option value="priority">Priority</option>
                  <option value="cycle">Cycle</option>
                  {modulesEnabled && <option value="module">Module</option>}
                  <option value="none">None (Flat list)</option>
                </select>
              </div>

              {(searchQuery || selectedState !== 'all' || selectedPriority !== 'all' || groupByOption !== 'state') && (
                <div className="list-filter-footer">
                  <button
                    type="button"
                    className="list-filter-reset-btn"
                    onClick={() => {
                      setSearchQuery('');
                      setSelectedState('all');
                      setSelectedPriority('all');
                      setGroupByOption('state');
                    }}
                  >
                    Reset filters
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {onCreateIssue && (
          <button
            type="button"
            className="list-new-btn"
            onClick={onCreateIssue}
            aria-label="New work item"
          >
            <span aria-hidden="true">+</span>
            <span>New</span>
          </button>
        )}
      </div>

      {sections.map((section) => {
        const isCollapsed = Boolean(collapsedSections[section.name]);

        return (
          <section
            key={section.id}
            className="list-section"
            data-section-name={section.name}
            aria-labelledby={`heading-${section.id}`}
          >
            <div className="list-section-header">
              <button
                type="button"
                id={`heading-${section.id}`}
                className="list-section-toggle"
                aria-expanded={!isCollapsed}
                onClick={() => { toggleSection(section.name); }}
              >
                <span className="list-section-toggle-icon" aria-hidden="true">
                  ▼
                </span>
                <span>{section.name}</span>
                <span className="list-section-count">{section.items.length}</span>
              </button>

              <div className="list-section-actions">
                {canManageWorkflows && (
                  <button
                    type="button"
                    className="list-section-add-workflow-btn"
                    data-testid={`section-add-workflow-btn-${section.name}`}
                    title={`Attach workflow transition to ${section.name}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (typeof window !== 'undefined') {
                        window.location.assign(
                          `/projects/${projectKey}/settings/workflows?to_state=${encodeURIComponent(section.name)}&attach=1`,
                        );
                      }
                    }}
                  >
                    + Workflow
                  </button>
                )}
                {onCreateIssue && (
                  <button
                    type="button"
                    className="list-section-new-btn"
                    onClick={onCreateIssue}
                    aria-label={`New work item in ${section.name}`}
                  >
                    + New work item
                  </button>
                )}
              </div>
            </div>

            {!isCollapsed && (
              <div
                className="list-table"
                role="table"
                aria-label={`${section.name} work items`}
              >
                <div className="list-rows" role="rowgroup">
                  {section.items.map((issue) => {
                    const itemIndex = visibleIssues.indexOf(issue);
                    return (
                      <ListRow
                        key={issue.id || issue.key}
                        issue={issue}
                        isSelected={selectedSet.has(issue.key)}
                        onToggleSelect={onToggleSelect}
                        modulesEnabled={modulesEnabled}
                        isFocused={itemIndex === focusedIndex || focusedKey === issue.key}
                        onOpenPeek={onOpenPeek}
                        isActive={activeKey === issue.key}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        );
      })}

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
