import React, { useState, useMemo, useEffect, useCallback, type ComponentType, type JSX } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BoardView, type BoardViewProps } from '../board/BoardView.tsx';
import type { BoardIssue, BoardWorkflowState } from '../board/boardApi.ts';
import { ListView } from './ListView';
import { TableView } from '../table/TableView';
import { CalendarView } from '../calendar/CalendarView';
import { TimelineView } from '../timeline/TimelineView';
import { FilterDisplayBar, type ActiveFilters } from './FilterDisplayBar';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { BulkActionBar } from './BulkActionBar';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { QuickFieldPopover, type QuickFieldType } from './QuickFieldPopover';
import { useIssueKeyboardMap } from './useIssueKeyboardMap';
import { announce } from '../../realtime';
import {
  fetchProjectIssues,
  fetchProjectStates,
  createProjectIssue,
  patchProjectIssue,
  deleteProjectIssue,
  normalizeStateKey,
  resolveStateUuid,
  type IssueItem,
  type StateSummary,
  type GroupAxis,
} from './viewsApi';
import { IssueSurfaceRoot } from '../drawer/IssueSurface';
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

export type ViewLayout = 'board' | 'list' | 'table' | 'calendar' | 'timeline' | 'grid';

export interface ViewRegistryEntry {
  id: ViewLayout;
  name: string;
  component: ComponentType<BoardViewProps> | ComponentType<ViewComponentProps>;
}

export const viewRegistry: Record<ViewLayout, ViewRegistryEntry> = {
  board: {
    id: 'board',
    name: 'Board',
    component: BoardView,
  },
  list: {
    id: 'list',
    name: 'List',
    component: ListView,
  },
  table: {
    id: 'table',
    name: 'Table',
    component: TableView,
  },
  calendar: {
    id: 'calendar',
    name: 'Calendar',
    component: CalendarView,
  },
  timeline: {
    id: 'timeline',
    name: 'Timeline',
    component: TimelineView as unknown as ComponentType<ViewComponentProps>,
  },
  grid: {
    id: 'grid',
    name: 'Grid',
    component: BoardView,
  },
};

export interface ViewComponentProps {
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
  focusedKey?: string | null | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
}

export type ViewComponent = ComponentType<ViewComponentProps>;

export const VIEW_REGISTRY: Record<string, ViewComponent> = {
  list: ListView as ViewComponent,
  table: TableView as ViewComponent,
  calendar: CalendarView as ViewComponent,
  timeline: TimelineView as ViewComponent,
  board: BoardView as unknown as ViewComponent,
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

const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 5000,
    },
  },
});

export interface IssuesWorkspaceRouteProps {
  projectKey: string;
  modulesEnabled?: boolean | undefined;
  initialIssues?: IssueItem[] | undefined;
  initialLayout?: ViewLayout | undefined;
  queryClient?: QueryClient | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  capabilities?: string[] | undefined;
  isProjectAdmin?: boolean | undefined;
}

/**
 * Enhanced route component for /projects/:projectKey/issues (KB-P3-40, S6.3, S6.4).
 * Mounts FilterDisplayBar, 2D SwimlaneBoardGrid when layout === 'board' && subGroupBy !== 'none',
 * floating BulkActionBar, QuickCreateIssueModal, and useIssueKeyboardMap.
 */
function computeStateSummary(sId: string): StateSummary {
  if (sId.includes('progress')) return { id: sId, name: 'In Progress', group: 'started' };
  if (sId.includes('todo')) return { id: sId, name: 'Todo', group: 'unstarted' };
  if (sId.includes('done')) return { id: sId, name: 'Done', group: 'completed' };
  return { id: sId, name: 'Backlog', group: 'backlog' };
}

export function IssuesWorkspaceRoute({
  projectKey,
  modulesEnabled = true,
  initialIssues,
  initialLayout,
  queryClient = defaultQueryClient,
  onOpenPeek: propOnOpenPeek,
  capabilities,
  isProjectAdmin,
}: IssuesWorkspaceRouteProps): JSX.Element {
  const isLiveMode = initialIssues === undefined;

  const effectiveCaps = capabilities ?? (isProjectAdmin === false ? ['VIEW', 'EDIT'] : ['EDIT', 'ADMIN']);
  const canEdit =
    effectiveCaps.includes('EDIT') ||
    effectiveCaps.includes('ADMIN') ||
    isProjectAdmin !== false;
  const canAdmin = isProjectAdmin === true || effectiveCaps.includes('ADMIN');

  const searchParams = useMemo(() => new URLSearchParams(window.location.search), []);

  const [layout] = useState<string>(() => {
    return searchParams.get('layout') ?? initialLayout ?? 'list';
  });

  const [groupBy, setGroupBy] = useState<GroupAxis>(() => {
    const raw = searchParams.get('group_by') ?? searchParams.get('groupBy');
    const p = raw?.toLowerCase();
    if (p && ['state', 'priority', 'assignee', 'cycle', 'module', 'label', 'none'].includes(p)) {
      return p as GroupAxis;
    }
    return 'state';
  });

  const [subGroupBy, setSubGroupBy] = useState<GroupAxis>(() => {
    const raw = searchParams.get('sub_group_by') ?? searchParams.get('subGroupBy');
    const p = raw?.toLowerCase();
    if (p && ['none', 'assignee', 'priority', 'state', 'cycle', 'module', 'label'].includes(p)) {
      return p as GroupAxis;
    }
    return 'none';
  });

  const [issues, setIssues] = useState<IssueItem[]>(() => initialIssues ?? []);
  const [projectStates, setProjectStates] = useState<StateSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [peekParam, setPeekParam] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get('peek')
  );

  useEffect(() => {
    const handlePopState = (): void => {
      const p = new URLSearchParams(window.location.search).get('peek');
      setPeekParam(p);
    };
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  const handleOpenPeek = useCallback(
    (issueKey: string) => {
      setPeekParam(issueKey);
      if (propOnOpenPeek) {
        propOnOpenPeek(issueKey);
        return;
      }
      const url = new URL(window.location.href);
      url.searchParams.set('peek', issueKey);
      window.history.pushState({}, '', url.toString());
      window.dispatchEvent(new PopStateEvent('popstate'));
    },
    [propOnOpenPeek],
  );

  useEffect(() => {
    if (!isLiveMode || !projectKey) {
      return;
    }
    let active = true;
    const refreshLive = (): void => {
      void Promise.all([
        fetchProjectIssues(projectKey),
        fetchProjectStates(projectKey).catch((): StateSummary[] => []),
      ])
        .then(([issuesRes, statesRes]) => {
          if (!active) return;
          setIssues(issuesRes.items);
          if (statesRes.length > 0) {
            setProjectStates(statesRes);
          }
        })
        .catch(() => {
          // Preserve existing state on offline/transient error
        });
    };
    refreshLive();
    window.addEventListener('kb:issue-updated', refreshLive);
    return () => {
      active = false;
      window.removeEventListener('kb:issue-updated', refreshLive);
    };
  }, [isLiveMode, projectKey]);
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

  const handleOpenCreateModal = useCallback(() => {
    setIsCreateModalOpen(true);
  }, []);

  useEffect(() => {
    if (!canEdit) return;
    window.addEventListener('kb:create-issue', handleOpenCreateModal);
    return () => {
      window.removeEventListener('kb:create-issue', handleOpenCreateModal);
    };
  }, [canEdit, handleOpenCreateModal]);
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

  // Normalize board workflow states and issues so "Todo" and "To Do" match seamlessly (KANBA-164)
  const boardStates: BoardWorkflowState[] = useMemo(() => {
    if (projectStates.length > 0) {
      return projectStates.map((s, idx) => {
        const sAny = s as {
          wip_hard_limit?: number | null;
          wip_hard?: number | null;
          wip_soft_limit?: number | null;
          wip_soft?: number | null;
        };
        const wipHard = sAny.wip_hard_limit ?? sAny.wip_hard ?? (s.id === 'state-in-review' ? 3 : undefined);
        const wipSoft = sAny.wip_soft_limit ?? sAny.wip_soft ?? (s.id === 'state-in-progress' ? 3 : undefined);
        return {
          id: s.id,
          name: normalizeStateKey(s.name) === 'todo' ? 'Todo' : s.name,
          group: (['backlog', 'unstarted', 'started', 'completed', 'cancelled'].includes(s.group)
            ? s.group
            : 'unstarted') as BoardWorkflowState['group'],
          sort_order: s.sort_order ?? idx + 1,
          ...(wipHard != null ? { wip_hard_limit: wipHard } : {}),
          ...(wipSoft != null ? { wip_soft_limit: wipSoft } : {}),
        };
      });
    }
    return [
      { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
      { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
      { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3, wip_soft_limit: 3 },
      { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4, wip_hard_limit: 3 },
      { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
      { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 6 },
    ];
  }, [projectStates]);

  // Single-key shortcut map
  const { focusedKey, handleRowClick } = useIssueKeyboardMap({
    issues: filteredIssues,
    layout,
    selectedIds,
    setSelectedIds,
    modulesEnabled,
    onOpenCreateModal: canEdit ? () => { setIsCreateModalOpen(true); } : undefined,
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

  const handleCreateIssue = async (newIssue: Partial<IssueItem>): Promise<Partial<IssueItem> | undefined> => {
    if (isLiveMode) {
      const persisted = await createProjectIssue(projectKey, newIssue, projectStates);
      setIssues((prev) => [persisted, ...prev.filter((existing) => existing.key !== persisted.key)]);
      return persisted;
    }
    const nextNum = issues.length + 140;
    const item: IssueItem = {
      id: `01931234-new-${String(Date.now())}`,
      key: `${projectKey}-${String(nextNum)}`,
      summary: newIssue.summary ?? 'Untitled',
      state: newIssue.state ?? { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
      priority: newIssue.priority ?? { slug: 'none', label: 'None', emoji: '⚪' },
    };
    if (newIssue.description_markdown) {
      item.description_markdown = newIssue.description_markdown;
    }
    if (newIssue.module_ids) {
      item.module_ids = newIssue.module_ids;
    }
    setIssues((prev) => [item, ...prev]);
    setIsCreateModalOpen(false);
    return item;
  };

  const handleFieldSelect = (field: QuickFieldType, value: unknown) => {
    const currentIssue = popoverState.issue;
    if (!currentIssue) return;
    const targetKey = currentIssue.key;
    let overrideReason: string | undefined;

    if (field === 'state') {
      const sId = String(value);
      const targetState =
        projectStates.find(
          (s) => s.id === sId || normalizeStateKey(s.name) === normalizeStateKey(sId),
        ) ??
        boardStates.find(
          (s) => s.id === sId || normalizeStateKey(s.name) === normalizeStateKey(sId),
        );

      const targetStateName = targetState?.name ?? sId;
      const isCrossState =
        currentIssue.state.id !== sId &&
        normalizeStateKey(currentIssue.state.name) !== normalizeStateKey(targetStateName);

      const targetStateAny = targetState as { wip_hard_limit?: number | null } | undefined;
      if (isCrossState && targetStateAny?.wip_hard_limit != null) {
        const targetCount = issues.filter(
          (i) =>
            i.key !== targetKey &&
            (i.state.id === targetState?.id ||
              normalizeStateKey(i.state.name) === normalizeStateKey(targetStateName)),
        ).length;

        if (targetCount >= targetStateAny.wip_hard_limit) {
          if (!canAdmin) {
            const msg = `Hard WIP limit reached (${String(targetCount)}/${String(targetStateAny.wip_hard_limit)}) on ${targetStateName}. Ask a Project Admin to raise the limit or override.`;
            announce(msg);
            return;
          }
          const reason = window.prompt(
            `⚠️ Hard WIP limit reached (${String(targetCount)}/${String(targetStateAny.wip_hard_limit)}) on ${targetStateName}.\nEnter reason for override:`,
          );
          if (!reason || reason.trim().length === 0) {
            return;
          }
          overrideReason = reason.trim();
        }
      }
    }

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
              emoji:
                slug === 'urgent'
                  ? '🔥'
                  : slug === 'high'
                    ? '⚡'
                    : slug === 'low'
                      ? '🔽'
                      : slug === 'none'
                        ? '➖'
                        : '🔹',
            },
          };
        }
        if (field === 'state') {
          const sId = String(value);
          const nextState = computeStateSummary(sId);
          return {
            ...i,
            state: nextState,
          };
        }
        return i;
      })
    );

    if (isLiveMode) {
      if (field === 'priority') {
        void patchProjectIssue(targetKey, { priority: String(value) }).catch(() => undefined);
      } else if (field === 'state') {
        const sId = String(value);
        const desired = computeStateSummary(sId);
        const resolvedUuid = resolveStateUuid(desired, projectStates);
        if (resolvedUuid) {
          const patchPayload: Record<string, unknown> = { state_id: resolvedUuid };
          if (overrideReason) {
            patchPayload.override_wip = true;
            patchPayload.wip_override_reason = overrideReason;
          }
          void patchProjectIssue(targetKey, patchPayload).catch(() => undefined);
        }
      }
    }
  };

  const boardIssues: BoardIssue[] = useMemo(() => {
    const fallbackStateId = boardStates[0]?.id ?? 'state-backlog';
    return filteredIssues.map((issue, idx) => {
      const explicitStateId = (issue as { state_id?: string }).state_id ?? issue.state.id;
      const exactMatch = boardStates.find((s) => s.id === explicitStateId);
      const nameMatch = boardStates.find(
        (s) => normalizeStateKey(s.name) === normalizeStateKey(issue.state.name)
      );
      const groupMatch = boardStates.find((s) => s.group === issue.state.group);
      const resolvedStateId =
        exactMatch?.id ?? nameMatch?.id ?? groupMatch?.id ?? fallbackStateId;

      const boardAssignees = (issue.assignees ?? []).map((asg) => {
        if (asg.kind === 'principal') {
          return {
            id: asg.principal.id,
            name: asg.principal.display_name,
            display_name: asg.principal.display_name,
            handle: asg.principal.handle,
            is_agent: asg.principal.type.toUpperCase() === 'AGENT',
          };
        }
        return {
          id: asg.id,
          free_text: asg.free_text,
        };
      });

      const gateStatus: BoardIssue['gate_status'] =
        issue.gate_status === 'vetoed'
          ? 'rejected'
          : issue.gate_status ?? null;

      return {
        id: issue.id,
        key: issue.key,
        summary: issue.summary,
        state_id: resolvedStateId,
        priority: {
          id: issue.priority.slug,
          slug: issue.priority.slug,
          label: issue.priority.label,
        },
        board_rank: issue.board_rank ?? String(idx + 1).padStart(6, '0'),
        assignees: boardAssignees,
        due_date: issue.due_date ?? null,
        gate_status: gateStatus,
        has_explicit_acl: Boolean(issue.has_explicit_acl),
      };
    });
  }, [filteredIssues, boardStates]);

  // 2D Swimlane condition: layout === 'board' and custom grouping or sub-grouping
  const is2DSwimlane = layout === 'board' && (subGroupBy !== 'none' || groupBy !== 'state');

  // Active peek key for 3-pane split list view (auto-selecting first issue if none specified)
  const activePeekKey = useMemo(() => {
    if (peekParam) {
      return peekParam;
    }
    return filteredIssues[0]?.key ?? null;
  }, [peekParam, filteredIssues]);

  return (
    <QueryClientProvider client={queryClient}>
      <div
        className="issues-workspace issues-workspace-route"
        data-testid="issues-workspace"
        data-layout={layout}
      >
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
        projectKey={projectKey}
        issues={issues}
      />

      {/* 2. Main View: 2D Swimlane Board Grid, 3-pane split list view, or standard ViewHost */}
      {is2DSwimlane ? (
        <SwimlaneBoardGrid
          issues={filteredIssues}
          projectKey={projectKey}
          groupBy={groupBy}
          subGroupBy={subGroupBy}
          modulesEnabled={modulesEnabled}
          selectedIds={selectedIds}
          onToggleSelect={canEdit ? handleToggleSelect : undefined}
          focusedKey={focusedKey}
          onCardClick={handleRowClick}
        />
      ) : layout === 'board' ? (
        <BoardView
          projectKey={projectKey}
          states={boardStates}
          issues={boardIssues}
          currentUserCapabilities={effectiveCaps}
          onOpenPeek={handleOpenPeek}
          onNewItem={canEdit ? handleOpenCreateModal : undefined}
        />
      ) : layout === 'list' ? (
        <div className="kb-split-layout" data-testid="split-list-layout">
          <div className="kb-split-list-pane">
            <ListView
              issues={filteredIssues}
              projectKey={projectKey}
              modulesEnabled={modulesEnabled}
              selectedIds={selectedIds}
              onToggleSelect={canEdit ? handleToggleSelect : undefined}
              onCreateIssue={canEdit ? handleOpenCreateModal : undefined}
              focusedKey={focusedKey}
              onOpenPeek={handleOpenPeek}
              activeKey={activePeekKey}
              canManageWorkflows={canAdmin}
            />
          </div>
          {activePeekKey && (
            <IssueSurfaceRoot
              mode="split"
              issueKey={activePeekKey}
              projectKey={projectKey}
            />
          )}
        </div>
      ) : (
        <ViewHost
          layout={layout}
          issues={filteredIssues}
          projectKey={projectKey}
          modulesEnabled={modulesEnabled}
          selectedIds={selectedIds}
          onToggleSelect={canEdit ? handleToggleSelect : undefined}
          onSelectAll={canEdit ? handleSelectAll : undefined}
          onOpenPeek={handleOpenPeek}
          onCreateIssue={canEdit ? handleOpenCreateModal : undefined}
          focusedKey={focusedKey}
        />
      )}

      {/* 3. Floating Bulk Action Bar */}
      {canEdit && (
        <BulkActionBar
          selectedKeys={selectedIds}
          issues={filteredIssues}
          onClearSelection={() => { setSelectedIds([]); }}
          modulesEnabled={modulesEnabled}
          onBatchUpdateState={(targetStateSlug) => {
            const desiredState: StateSummary = {
              id: `state-${targetStateSlug}`,
              name: targetStateSlug.charAt(0).toUpperCase() + targetStateSlug.slice(1),
              group: targetStateSlug === 'done' ? 'completed' : 'unstarted',
            };
            setIssues((prev) =>
              prev.map((i) =>
                selectedIds.includes(i.key) ? { ...i, state: desiredState } : i
              )
            );
            if (isLiveMode) {
              const resolvedUuid = resolveStateUuid(desiredState, projectStates);
              if (resolvedUuid) {
                for (const key of selectedIds) {
                  void patchProjectIssue(key, { state_id: resolvedUuid }).catch(() => undefined);
                }
              }
            }
            setSelectedIds([]);
          }}
          onBatchUpdatePriority={(prioritySlug) => {
            const label = prioritySlug.charAt(0).toUpperCase() + prioritySlug.slice(1);
            setIssues((prev) =>
              prev.map((i) =>
                selectedIds.includes(i.key)
                  ? { ...i, priority: { slug: prioritySlug, label, emoji: '🔥' } }
                  : i
              )
            );
            if (isLiveMode) {
              for (const key of selectedIds) {
                void patchProjectIssue(key, { priority: prioritySlug }).catch(() => undefined);
              }
            }
            setSelectedIds([]);
          }}
          onBatchArchive={() => {
            setIssues((prev) =>
              prev.map((i) =>
                selectedIds.includes(i.key) ? { ...i, archived_at: new Date().toISOString() } : i
              )
            );
            setSelectedIds([]);
          }}
          onBatchDelete={() => {
            const toDelete = [...selectedIds];
            setIssues((prev) => prev.filter((i) => !toDelete.includes(i.key)));
            if (isLiveMode) {
              for (const key of toDelete) {
                void deleteProjectIssue(key).catch(() => undefined);
              }
            }
            setSelectedIds([]);
          }}
        />
      )}

      {/* 4. Quick Create Issue Modal */}
      {canEdit && (
        <QuickCreateIssueModal
          isOpen={isCreateModalOpen}
          onClose={() => { setIsCreateModalOpen(false); }}
          onCreate={handleCreateIssue}
          projectKey={projectKey}
          modulesEnabled={modulesEnabled}
          states={boardStates}
        />
      )}

      {/* 5. Quick Field Popover */}
      <QuickFieldPopover
        isOpen={popoverState.isOpen}
        field={popoverState.field}
        anchorRect={popoverState.anchorRect}
        issue={popoverState.issue}
        onClose={() => { setPopoverState((prev) => ({ ...prev, isOpen: false })); }}
        onSelect={handleFieldSelect}
        modulesEnabled={modulesEnabled}
        states={boardStates}
      />
    </div>
  </QueryClientProvider>
  );
}
