import React, { useState, useMemo, type JSX } from 'react';
import { ListRow } from './ListRow';
import type { IssueItem } from '../views/viewsApi';
import '../views/listTable.css';

export interface ListViewProps {
  issues: IssueItem[];
  projectKey: string;
  modulesEnabled?: boolean;
  selectedIds?: string[];
  onToggleSelect?: (key: string, selected: boolean) => void;
  onCreateIssue?: () => void;
  nextCursor?: string | null;
  onLoadMore?: () => void;
  isLoading?: boolean;
}

interface GroupSection {
  id: string;
  name: string;
  sortOrder: number;
  items: IssueItem[];
}

export function ListView({
  issues,
  modulesEnabled = true,
  selectedIds = [],
  onToggleSelect,
  onCreateIssue,
  nextCursor,
  onLoadMore,
  isLoading = false,
}: ListViewProps): JSX.Element {
  // Collapsed state map: key is section name/id, value is boolean (true if collapsed)
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [focusedIndex, setFocusedIndex] = useState<number>(0);

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

  // Group issues by state, preserving known states with 0 items
  const sections = useMemo(() => {
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
    for (const issue of issues) {
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
  }, [issues, defaultStates]);

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
        <button
          type="button"
          className="view-empty-create-btn"
          onClick={onCreateIssue}
        >
          + Create first work item
        </button>
      </div>
    );
  }

  return (
    <div className="list-view" onKeyDown={handleKeyDown}>
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

              <button
                type="button"
                className="list-section-new-btn"
                onClick={onCreateIssue}
                aria-label={`New work item in ${section.name}`}
              >
                + New work item
              </button>
            </div>

            {!isCollapsed && (
              <ul className="list-rows" role="list">
                {section.items.map((issue) => {
                  const itemIndex = visibleIssues.indexOf(issue);
                  return (
                    <ListRow
                      key={issue.id || issue.key}
                      issue={issue}
                      isSelected={selectedSet.has(issue.key)}
                      onToggleSelect={onToggleSelect}
                      modulesEnabled={modulesEnabled}
                      isFocused={itemIndex === focusedIndex}
                    />
                  );
                })}
              </ul>
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
