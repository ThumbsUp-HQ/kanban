import React, { useState, useMemo, type ComponentType, type JSX } from 'react';
import { ListView } from '../list/ListView';
import { TableView } from '../table/TableView';
import { FilterDisplayBar, type ActiveFilters } from './FilterDisplayBar';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { BulkActionBar } from './BulkActionBar';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { QuickFieldPopover, type QuickFieldType } from './QuickFieldPopover';
import { useIssueKeyboardMap } from './useIssueKeyboardMap';
import type { IssueItem, GroupAxis } from './viewsApi';
import './filterBulk.css';

// Export all KB-P3-40 components per Scoped Definition of Done
export {
  FilterDisplayBar,
  SwimlaneBoardGrid,
  BulkActionBar,
  QuickCreateIssueModal,
  QuickFieldPopover,
  useIssueKeyboardMap,
};

export interface ViewComponentProps {
  issues: IssueItem[];
  projectKey: string;
  modulesEnabled?: boolean;
  selectedIds?: string[];
  onToggleSelect?: (key: string, selected: boolean) => void;
  onSelectAll?: (selected: boolean) => void;
  onCreateIssue?: () => void;
  nextCursor?: string | null;
  onLoadMore?: () => void;
  isLoading?: boolean;
  focusedKey?: string | null;
}

export type ViewComponent = ComponentType<ViewComponentProps>;

export const VIEW_REGISTRY: Record<string, ViewComponent> = {
  list: ListView as ViewComponent,
  table: TableView as ViewComponent,
  board: SwimlaneBoardGrid,
};

export interface ViewHostProps extends ViewComponentProps {
  layout?: string;
}

/**
 * Shared layout host rendering the appropriate registered view (KB-P3-38, S6.4 item 2).
 */
export function ViewHost({
  layout = 'list',
  ...props
}: ViewHostProps): JSX.Element {
  const normalizedLayout = layout.toLowerCase();
  const Component = VIEW_REGISTRY[normalizedLayout] ?? ListView;

  return <Component {...props} />;
}

export interface IssuesWorkspaceRouteProps {
  projectKey: string;
  modulesEnabled?: boolean;
  initialIssues?: IssueItem[];
}

/**
 * Enhanced route component for /projects/:projectKey/issues (KB-P3-40, S6.3, S6.4).
 * Mounts FilterDisplayBar, 2D SwimlaneBoardGrid when layout === 'board' && subGroupBy !== 'none',
 * floating BulkActionBar, QuickCreateIssueModal, and useIssueKeyboardMap.
 */
export function IssuesWorkspaceRoute({
  projectKey,
  modulesEnabled = true,
  initialIssues = [],
}: IssuesWorkspaceRouteProps): JSX.Element {
  const searchParams = useMemo(() => {
    return new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '');
  }, []);

  const [layout] = useState<string>(() => {
    return searchParams.get('layout') ?? 'list';
  });

  const [groupBy, setGroupBy] = useState<GroupAxis>(() => {
    const p = searchParams.get('group_by');
    if (p && ['state', 'priority', 'assignee', 'cycle', 'module', 'label', 'none'].includes(p)) {
      return p as GroupAxis;
    }
    return 'state';
  });

  const [subGroupBy, setSubGroupBy] = useState<GroupAxis>(() => {
    const p = searchParams.get('sub_group_by');
    if (p && ['none', 'assignee', 'priority', 'state', 'cycle', 'module', 'label'].includes(p)) {
      return p as GroupAxis;
    }
    return 'none';
  });

  const [issues, setIssues] = useState<IssueItem[]>(initialIssues);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>(() => {
    const filters: ActiveFilters = {};
    const stateParam = searchParams.get('filter_state');
    if (stateParam) {
      filters.state = [stateParam];
    }
    const priorityParam = searchParams.get('filter_priority');
    if (priorityParam) {
      filters.priority = [priorityParam];
    }
    const labelParam = searchParams.get('filter_label');
    if (labelParam) {
      filters.label = [labelParam];
    }
    const gateParam = searchParams.get('gate_status');
    if (gateParam) {
      filters.gate_status = [gateParam];
    }
    return filters;
  });

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [popoverState, setPopoverState] = useState<{
    isOpen: boolean;
    field: QuickFieldType | null;
    issue: IssueItem | null;
    anchorRect: DOMRect | null;
  }>({
    isOpen: false,
    field: null,
    issue: null,
    anchorRect: null,
  });

  // Filter issues based on activeFilters
  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      // 1. State filter
      if (activeFilters.state && activeFilters.state.length > 0) {
        const matchesActive =
          activeFilters.state.includes('active') &&
          ['backlog', 'unstarted', 'started'].includes(issue.state.group);
        const matchesSpecific = activeFilters.state.some(
          (s) =>
            s === issue.state.group ||
            s === issue.state.name.toLowerCase() ||
            s === issue.state.id
        );
        if (!matchesActive && !matchesSpecific) return false;
      }

      // 2. Priority filter
      if (activeFilters.priority && activeFilters.priority.length > 0) {
        const pSlug = issue.priority.slug.toLowerCase();
        if (!activeFilters.priority.includes(pSlug)) return false;
      }

      // 3. Assignee filter
      if (activeFilters.assignee && activeFilters.assignee.length > 0) {
        const hasUnassigned = activeFilters.assignee.includes('unassigned');
        const issueAssignees = issue.assignees ?? [];
        const isUnassigned = issueAssignees.length === 0;

        if (hasUnassigned && isUnassigned) {
          // matches unassigned
        } else {
          const matchesPrincipal = issueAssignees.some((asg) => {
            if (asg.kind === 'principal') {
              return activeFilters.assignee?.some(
                (a) =>
                  a === asg.principal.id ||
                  a.toLowerCase() === asg.principal.handle.toLowerCase()
              );
            }
            return false;
          });
          if (!matchesPrincipal) return false;
        }
      }

      // 4. Label filter
      if (activeFilters.label && activeFilters.label.length > 0) {
        const issueLabels = issue.labels ?? [];
        const matchesLabel = issueLabels.some((lbl) =>
          activeFilters.label?.some(
            (l) =>
              l.toLowerCase() === lbl.name.toLowerCase() ||
              l === lbl.id
          )
        );
        if (!matchesLabel) return false;
      }

      // 5. Cycle filter
      if (activeFilters.cycle && activeFilters.cycle.length > 0) {
        if (!issue.cycle_id || !activeFilters.cycle.includes(issue.cycle_id)) {
          return false;
        }
      }

      // 6. Module filter (only if modulesEnabled is true)
      if (modulesEnabled && activeFilters.module && activeFilters.module.length > 0) {
        const issueMods = issue.module_ids ?? [];
        const matchesMod = issueMods.some((m) => activeFilters.module?.includes(m));
        if (!matchesMod) return false;
      }

      // 7. Gate status filter
      if (activeFilters.gate_status && activeFilters.gate_status.length > 0) {
        if (!issue.gate_status || !activeFilters.gate_status.includes(issue.gate_status)) {
          return false;
        }
      }

      // 8. Due date filter
      if (activeFilters.due_date && activeFilters.due_date.length > 0) {
        const today = new Date().toISOString().slice(0, 10);
        const isOverdue =
          issue.due_date &&
          issue.due_date < today &&
          issue.state.group !== 'completed' &&
          issue.state.group !== 'cancelled';
        if (activeFilters.due_date.includes('overdue') && !isOverdue) return false;
        if (activeFilters.due_date.includes('no_due_date') && issue.due_date) return false;
      }

      return true;
    });
  }, [issues, activeFilters, modulesEnabled]);

  // Single-key shortcut map
  const { focusedKey, handleRowClick } = useIssueKeyboardMap({
    issues: filteredIssues,
    layout,
    selectedIds,
    setSelectedIds,
    modulesEnabled,
    onOpenCreateModal: () => { setIsCreateModalOpen(true); },
    onOpenFilter: () => { setIsFilterOpen(true); },
    onOpenFieldPopover: (field, issue, rect) => {
      setPopoverState({
        isOpen: true,
        field,
        issue,
        anchorRect: rect,
      });
    },
    onToggleAssigneeMe: (issue) => {
      // Toggle @adam assignment optimistically
      setIssues((prev) =>
        prev.map((i) => {
          if (i.key !== issue.key) return i;
          const currentAssignees = i.assignees ?? [];
          const hasMe = currentAssignees.some(
            (a) => a.kind === 'principal' && a.principal.handle === 'adam'
          );
          if (hasMe) {
            return {
              ...i,
              assignees: currentAssignees.filter(
                (a) => !(a.kind === 'principal' && a.principal.handle === 'adam')
              ),
            };
          }
          return {
            ...i,
            assignees: [
              ...currentAssignees,
              {
                id: 'asg-me',
                kind: 'principal',
                principal: {
                  id: 'u-me',
                  handle: 'adam',
                  display_name: 'Adam Outler',
                  type: 'USER',
                },
              },
            ],
          };
        })
      );
    },
    isPopoverOrModalOpen: isCreateModalOpen || popoverState.isOpen,
  });

  const handleToggleSelect = (key: string, selected: boolean) => {
    setSelectedIds((prev) => {
      if (selected) {
        if (prev.length >= 100) return prev;
        return [...prev, key];
      }
      return prev.filter((id) => id !== key);
    });
  };

  const handleSelectAll = (selected: boolean) => {
    if (selected) {
      const allKeys = filteredIssues.map((i) => i.key);
      setSelectedIds(allKeys.slice(0, 100));
    } else {
      setSelectedIds([]);
    }
  };

  const handleCreateIssue = (newIssue: Partial<IssueItem>) => {
    const nextNum = issues.length + 140;
    const item: IssueItem = {
      id: `01931234-new-${String(Date.now())}`,
      key: `${projectKey}-${String(nextNum)}`,
      summary: newIssue.summary ?? 'Untitled work item',
      state: newIssue.state ?? { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      priority: newIssue.priority ?? { slug: 'medium', label: 'Medium', emoji: '🔹' },
    };
    if (newIssue.description_markdown) {
      item.description_markdown = newIssue.description_markdown;
    }
    if (newIssue.module_ids) {
      item.module_ids = newIssue.module_ids;
    }
    setIssues((prev) => [item, ...prev]);
  };

  const handleFieldSelect = (field: QuickFieldType, value: unknown) => {
    if (!popoverState.issue) return;
    const targetKey = popoverState.issue.key;

    setIssues((prev) =>
      prev.map((i) => {
        if (i.key !== targetKey) return i;
        if (field === 'priority') {
          const slug = String(value);
          return {
            ...i,
            priority: {
              slug,
              label: slug.charAt(0).toUpperCase() + slug.slice(1),
              emoji: slug === 'urgent' ? '🔥' : slug === 'high' ? '⚡' : slug === 'low' ? '💤' : '🔹',
            },
          };
        }
        if (field === 'state') {
          const sId = String(value);
          return {
            ...i,
            state: {
              id: sId,
              name: sId.includes('progress') ? 'In Progress' : sId.includes('todo') ? 'Todo' : sId.includes('done') ? 'Done' : 'Backlog',
              group: sId.includes('progress') ? 'started' : sId.includes('todo') ? 'unstarted' : sId.includes('done') ? 'completed' : 'backlog',
            },
          };
        }
        return i;
      })
    );
  };

  // 2D Swimlane condition: layout === 'board' && subGroupBy !== 'none'
  const is2DSwimlane = layout === 'board' && subGroupBy !== 'none';

  return (
    <div className="issues-workspace-route" data-testid="issues-workspace">
      {/* 1. Filter and Display Bar */}
      <FilterDisplayBar
        activeFilters={activeFilters}
        onFiltersChange={setActiveFilters}
        groupBy={groupBy}
        onGroupByChange={setGroupBy}
        subGroupBy={subGroupBy}
        onSubGroupByChange={setSubGroupBy}
        modulesEnabled={modulesEnabled}
        isFilterOpen={isFilterOpen}
        onToggleFilterOpen={setIsFilterOpen}
      />

      {/* 2. Main View: 2D Swimlane Board Grid or standard ViewHost */}
      {is2DSwimlane ? (
        <SwimlaneBoardGrid
          issues={filteredIssues}
          projectKey={projectKey}
          groupBy={groupBy}
          subGroupBy={subGroupBy}
          modulesEnabled={modulesEnabled}
          selectedIds={selectedIds}
          onToggleSelect={handleToggleSelect}
          focusedKey={focusedKey}
          onCardClick={handleRowClick}
        />
      ) : (
        <ViewHost
          layout={layout}
          issues={filteredIssues}
          projectKey={projectKey}
          modulesEnabled={modulesEnabled}
          selectedIds={selectedIds}
          onToggleSelect={handleToggleSelect}
          onSelectAll={handleSelectAll}
          focusedKey={focusedKey}
        />
      )}

      {/* 3. Floating Bulk Action Bar */}
      <BulkActionBar
        selectedKeys={selectedIds}
        issues={filteredIssues}
        onClearSelection={() => { setSelectedIds([]); }}
        modulesEnabled={modulesEnabled}
        onBatchArchive={() => {
          setIssues((prev) =>
            prev.map((i) =>
              selectedIds.includes(i.key) ? { ...i, archived_at: new Date().toISOString() } : i
            )
          );
          setSelectedIds([]);
        }}
        onBatchDelete={() => {
          setIssues((prev) => prev.filter((i) => !selectedIds.includes(i.key)));
          setSelectedIds([]);
        }}
      />

      {/* 4. Quick Create Issue Modal */}
      <QuickCreateIssueModal
        isOpen={isCreateModalOpen}
        onClose={() => { setIsCreateModalOpen(false); }}
        onCreate={handleCreateIssue}
        projectKey={projectKey}
        modulesEnabled={modulesEnabled}
      />

      {/* 5. Quick Field Popover */}
      <QuickFieldPopover
        isOpen={popoverState.isOpen}
        field={popoverState.field}
        anchorRect={popoverState.anchorRect}
        issue={popoverState.issue}
        onClose={() => { setPopoverState((prev) => ({ ...prev, isOpen: false })); }}
        onSelect={handleFieldSelect}
        modulesEnabled={modulesEnabled}
      />
    </div>
  );
}
