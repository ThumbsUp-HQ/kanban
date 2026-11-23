import React, { useState, useMemo, useEffect, useCallback, type ComponentType, type JSX } from 'react';
import { useParams } from 'react-router';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { qk } from '../../api/queryKeys';
import { BoardView, type BoardViewProps } from '../board/BoardView.tsx';
import type { BoardIssue, BoardWorkflowState, StateGroup } from '../board/boardApi.ts';
import { ListView, type IssueSortOption, sortIssuesList } from './ListView';
import { TableView } from '../table/TableView';
import { CalendarView } from '../calendar/CalendarView';
import { TimelineView } from '../timeline/TimelineView';
import { FilterDisplayBar, type ActiveFilters } from './FilterDisplayBar';
import { IssueNavigatorBar } from './IssueNavigatorBar';
import {
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  isIssueStateVisible,
  parseUrlFilterStateParam,
  resolveInitialStateFilter,
  resolveSavedViewStateFilter,
  writeProjectStateFilterCookie,
  type ProjectStateFilterPreference,
} from './issueFilterCookie';
import {
  buildStateQueryTokens,
  hasExplicitStatePredicate,
  matchesIssueQuery,
  parseStateFilterFromQuery,
} from './predicateParser';
import { StateFilterPopover } from './StateFilterPopover';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { BulkActionBar } from './BulkActionBar';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { SaveViewModal } from './SaveViewModal';
import { QuickFieldPopover, type QuickFieldType } from './QuickFieldPopover';
import { CsvImportExportModal } from './CsvImportExportModal';
import { ReportExportModal } from '../reports/ReportExportModal';
import { useIssueKeyboardMap } from './useIssueKeyboardMap';
import { announce } from '../../realtime';
import {
  fetchAllProjectIssues,
  fetchStagedProjectIssues,
  fetchProjectStates,
  fetchProjectSavedViews,
  createProjectIssue,
  patchProjectIssue,
  deleteProjectIssue,
  normalizeStateKey,
  resolveStateUuid,
  type IssueItem,
  type StateSummary,
  type GroupAxis,
  type SavedView,
} from './viewsApi';
import { IssueSurfaceRoot } from '../drawer/IssueSurface';
import './filterBulk.css';

// Export all KB-P3-40 and KAN-308 components per Scoped Definition of Done
export {
  FilterDisplayBar,
  SwimlaneBoardGrid,
  BulkActionBar,
  QuickCreateIssueModal,
  SaveViewModal,
  QuickFieldPopover,
  StateFilterPopover,
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
  projectStates?: StateSummary[] | undefined;
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
  capabilities?: string[] | undefined;
  totalProjectIssueCount?: number | undefined;
  hiddenByStateCount?: number | undefined;
  onShowAllStates?: (() => void) | undefined;
  onResetFilters?: (() => void) | undefined;
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

export const defaultQueryClient = new QueryClient({
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
  workspaceSlug?: string | undefined;
}

/**
 * Enhanced route component for /projects/:projectKey/issues (KB-P3-40, S6.3, S6.4).
 * Mounts FilterDisplayBar, 2D SwimlaneBoardGrid when layout === 'board' && subGroupBy !== 'none',
 * floating BulkActionBar, QuickCreateIssueModal, and useIssueKeyboardMap.
 */
function resolveIssueStateSummary(
  issue: IssueItem,
  projectStates: StateSummary[],
): { id?: string; name?: string; group?: string; color_hex?: string | null } | undefined {
  const rawState = (issue as { state?: { id?: string; name?: string; group?: string; color_hex?: string | null } }).state;
  const explicitStateId = (issue as { state_id?: string }).state_id ?? rawState?.id;
  if (rawState?.name && rawState.group) {
    return rawState;
  }
  if (explicitStateId) {
    const found = projectStates.find((s) => s.id === explicitStateId);
    if (found) return found;
  }
  return rawState;
}

export function computeStateSummary(
  sId: string,
  projectStates?: StateSummary[],
): StateSummary {
  if (projectStates && projectStates.length > 0) {
    const matched =
      projectStates.find((s) => s.id === sId) ??
      projectStates.find(
        (s) => normalizeStateKey(s.name) === normalizeStateKey(sId),
      ) ??
      projectStates.find((s) => s.group === sId);
    if (matched) {
      return {
        id: matched.id,
        name: matched.name,
        group: matched.group,
        color_hex: matched.color_hex ?? null,
      };
    }
  }
  if (sId.includes('progress')) return { id: sId, name: 'In Progress', group: 'started' };
  if (sId.includes('todo')) return { id: sId, name: 'Todo', group: 'unstarted' };
  if (sId.includes('done')) return { id: sId, name: 'Done', group: 'completed' };
  return { id: sId, name: 'Backlog', group: 'backlog' };
}

export function IssuesWorkspaceRoute({
  projectKey,
  modulesEnabled: propModulesEnabled,
  initialIssues,
  initialLayout,
  queryClient = defaultQueryClient,
  onOpenPeek: propOnOpenPeek,
  capabilities,
  isProjectAdmin,
  workspaceSlug: propWorkspaceSlug,
}: IssuesWorkspaceRouteProps): JSX.Element {
  const routeParams = useParams<{ workspaceSlug?: string }>();
  const auth = useAuth();
  const cachedMe = queryClient.getQueryData<{ workspace_id?: string }>(qk.me());
  const activeWorkspaceSlug =
    (propWorkspaceSlug && propWorkspaceSlug !== 'default' && propWorkspaceSlug.trim().length > 0)
      ? propWorkspaceSlug.trim()
      : (routeParams.workspaceSlug && routeParams.workspaceSlug !== 'default' && routeParams.workspaceSlug.trim().length > 0)
        ? routeParams.workspaceSlug.trim()
        : (auth.session?.workspace_id && auth.session.workspace_id.trim().length > 0)
          ? auth.session.workspace_id.trim()
          : (cachedMe?.workspace_id && cachedMe.workspace_id.trim().length > 0)
            ? cachedMe.workspace_id.trim()
            : 'current';

  const isLiveMode = initialIssues === undefined;

  const [projectMetadata, setProjectMetadata] = useState<{ modules_enabled?: boolean; name?: string } | null>(() => {
    return queryClient.getQueryData<{ modules_enabled?: boolean; name?: string }>(['project', projectKey]) ?? null;
  });

  useEffect(() => {
    if (!projectKey) return;
    const updateFromCache = (): void => {
      const data = queryClient.getQueryData<{ modules_enabled?: boolean; name?: string }>(['project', projectKey]);
      setProjectMetadata(data ?? null);
    };
    updateFromCache();
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      const keyParts = event.query.queryKey as readonly unknown[];
      if (keyParts[0] === 'project' && keyParts[1] === projectKey) {
        updateFromCache();
      }
    });
    return () => {
      unsubscribe();
    };
  }, [queryClient, projectKey]);

  // KB-P3-AUDIT-08: In live mode or when project query is tracked, do NOT pass modulesEnabled=true
  // until project query explicitly confirms project?.modules_enabled === true.
  const hasProjectQuery = Boolean(
    projectMetadata !== null || queryClient.getQueryState(['project', projectKey])
  );
  const modulesEnabled = propModulesEnabled === false
    ? false
    : hasProjectQuery
      ? Boolean(projectMetadata?.modules_enabled)
      : (propModulesEnabled ?? (isLiveMode ? false : true));

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

  useState(() => {
    if (initialIssues !== undefined) {
      queryClient.setQueryData(qk.issues(projectKey, {}), initialIssues);
    }
    return 0;
  });

  const [isStagedLoading, setIsStagedLoading] = useState<boolean>(false);
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(isLiveMode);

  const issuesQuery = useQuery(
    {
      queryKey: qk.issues(projectKey, {}),
      queryFn: async ({ signal }) => {
        const res = await fetchAllProjectIssues(projectKey, { signal, lod: 'summary' });
        return res.items;
      },
      enabled: false,
      initialData: initialIssues,
    },
    queryClient,
  );

  const [projectStates, setProjectStates] = useState<StateSummary[]>(() => {
    return queryClient.getQueryData<StateSummary[]>(['states', projectKey]) ?? [];
  });

  const issues = useMemo(
    () => issuesQuery.data ?? initialIssues ?? [],
    [issuesQuery.data, initialIssues],
  );

  const setIssues = useCallback(
    (updater: IssueItem[] | ((prev: IssueItem[]) => IssueItem[])) => {
      queryClient.setQueryData<IssueItem[]>(qk.issues(projectKey, {}), (old) => {
        const base = old ?? initialIssues ?? [];
        return typeof updater === 'function' ? updater(base) : updater;
      });
    },
    [initialIssues, projectKey, queryClient],
  );
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

  const [closedSplitKey, setClosedSplitKey] = useState<string | null>(null);

  const handleOpenPeek = useCallback(
    (issueKey: string | null) => {
      setPeekParam(issueKey);
      if (issueKey) {
        setClosedSplitKey(null);
      }
      if (propOnOpenPeek) {
        if (issueKey) propOnOpenPeek(issueKey);
        return;
      }
      const url = new URL(window.location.href);
      if (issueKey) {
        url.searchParams.set('peek', issueKey);
      } else {
        url.searchParams.delete('peek');
      }
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
    let currentController: AbortController | null = null;
    const refreshLive = (): void => {
      currentController?.abort();
      const controller = new AbortController();
      currentController = controller;
      setIsInitialLoading(true);
      void Promise.all([
        fetchStagedProjectIssues(projectKey, {
          signal: controller.signal,
          lod: 'summary',
          onPhase1: (phase1Items, hasMore) => {
            if (!active || controller.signal.aborted) return;
            setIssues(phase1Items);
            setIsInitialLoading(false);
            if (hasMore) {
              setIsStagedLoading(true);
            }
          },
        }),
        fetchProjectStates(projectKey).catch((): StateSummary[] => []),
      ])
        .then(([issuesRes, statesRes]) => {
          if (!active || controller.signal.aborted) return;
          setIssues(issuesRes.items);
          setIsStagedLoading(false);
          setIsInitialLoading(false);
          if (statesRes.length > 0) {
            setProjectStates(statesRes);
          }
        })
        .catch(() => {
          if (active && !controller.signal.aborted) {
            setIsStagedLoading(false);
            setIsInitialLoading(false);
          }
        });
    };
    refreshLive();
    window.addEventListener('kb:issue-updated', refreshLive);
    return () => {
      active = false;
      currentController?.abort();
      window.removeEventListener('kb:issue-updated', refreshLive);
    };
  }, [isLiveMode, projectKey, setIssues, setProjectStates]);
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>(() => {
    const filters: ActiveFilters = {};
    const stateParam = searchParams.get('filter_state');
    if (stateParam && parseUrlFilterStateParam(stateParam, projectStates) !== null) {
      filters.state = stateParam
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
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

  const [stateFilterPref, setStateFilterPref] = useState<ProjectStateFilterPreference>(() => {
    return resolveInitialStateFilter({
      projectKey,
      urlSearch: typeof window !== 'undefined' ? window.location.search : '',
      projectStates,
    }).preference;
  });

  const handleUserStateFilterChange = useCallback(
    (nextPref: ProjectStateFilterPreference) => {
      setStateFilterPref(nextPref);
      writeProjectStateFilterCookie(projectKey, nextPref);
    },
    [projectKey],
  );

  const [isStatePopoverOpen, setIsStatePopoverOpen] = useState(false);

  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [favVersion, setFavVersion] = useState(0);

  useEffect(() => {
    const handleFavChange = (): void => {
      setFavVersion((v) => v + 1);
    };
    window.addEventListener('kb:favorites-changed', handleFavChange);
    return () => {
      window.removeEventListener('kb:favorites-changed', handleFavChange);
    };
  }, []);
  const [searchQuery, setSearchQuery] = useState('');
  const [queryMode, setQueryMode] = useState<'basic' | 'query'>('basic');
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [activeViewId, setActiveViewId] = useState<string | null>(() => searchParams.get('view'));

  const handleQueryModeChange = useCallback(
    (nextMode: 'basic' | 'query') => {
      if (nextMode === queryMode) return;
      if (nextMode === 'query') {
        if (searchQuery.trim().length === 0) {
          const prefill = buildStateQueryTokens(stateFilterPref, projectStates);
          if (prefill) {
            setSearchQuery(prefill);
          }
        }
        setQueryMode('query');
        return;
      }
      // Switching Query -> Basic: sync state predicates back into checkbox preference without overwriting cookie
      const parsed = parseStateFilterFromQuery(searchQuery, projectStates);
      if (parsed.hasStatePredicate) {
        setStateFilterPref(parsed.preference);
        setSearchQuery(parsed.remainingQuery);
      }
      setQueryMode('basic');
    },
    [queryMode, searchQuery, stateFilterPref, projectStates],
  );

  useEffect(() => {
    if (!projectKey) return;
    let active = true;
    void fetchProjectSavedViews(projectKey)
      .then((views) => {
        if (active && Array.isArray(views)) {
          setSavedViews(views);
          const currentParams = new URLSearchParams(window.location.search);
          const viewParam = currentParams.get('view');
          if (viewParam) {
            const matched = views.find((v) => v.id === viewParam);
            if (matched) {
              setActiveViewId(viewParam);
              setGroupBy(matched.group_by);
              setSubGroupBy(matched.sub_group_by);
              const urlFilterState = currentParams.get('filter_state');
              if (!urlFilterState || parseUrlFilterStateParam(urlFilterState, projectStates) === null) {
                const viewPref = resolveSavedViewStateFilter(matched, projectStates);
                if (viewPref) {
                  setStateFilterPref(viewPref);
                }
              }
              if (matched.filters?.search_query) {
                setSearchQuery(matched.filters.search_query);
              }
            }
          }
        }
      })
      .catch(() => {
        // unit test or offline fallback
      });
    return () => {
      active = false;
    };
  }, [projectKey, projectStates]);

  const handleSelectSavedView = useCallback(
    (viewId: string) => {
      setActiveViewId(viewId);
      const view = savedViews.find((v) => v.id === viewId);
      if (view) {
        setGroupBy(view.group_by);
        setSubGroupBy(view.sub_group_by);
        const viewPref = resolveSavedViewStateFilter(view, projectStates);
        if (viewPref) {
          setStateFilterPref(viewPref);
        }
        if (view.filters?.search_query !== undefined && view.filters.search_query !== null) {
          setSearchQuery(view.filters.search_query);
        }
      }
      const url = new URL(window.location.href);
      url.searchParams.set('view', viewId);
      window.history.pushState({}, '', url.toString());
    },
    [savedViews, projectStates],
  );

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isSaveViewModalOpen, setIsSaveViewModalOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [csvModalTab, setCsvModalTab] = useState<'export' | 'import' | null>(null);
  const [csvExportFormat, setCsvExportFormat] = useState<'csv' | 'zip_csv'>('csv');
  const [isReportsModalOpen, setIsReportsModalOpen] = useState(false);

  const handleExport = useCallback((format: 'csv' | 'zip_csv' = 'csv') => {
    setCsvExportFormat(format);
    setCsvModalTab('export');
  }, []);

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

  // Evaluate non-state filters + text/query search first so we can distinguish state-hidden items
  const { filteredIssues, hiddenByStateIssues } = useMemo(() => {
    const isIssuesView = layout === 'list' || layout === 'table';
    const queryHasExplicitState =
      queryMode === 'query' && hasExplicitStatePredicate(searchQuery);

    const visible: IssueItem[] = [];
    const hiddenByState: IssueItem[] = [];

    for (const issue of issues) {
      const explicitStateId = (issue as { state_id?: string }).state_id;
      const resolvedState = resolveIssueStateSummary(issue, projectStates);

      const stateGroup = resolvedState?.group ?? 'unstarted';
      const stateName = resolvedState?.name ?? '';
      const stateId = resolvedState?.id ?? explicitStateId ?? '';

      // 1. Priority filter
      if (activeFilters.priority && activeFilters.priority.length > 0) {
        const rawPriority = (issue as { priority?: { slug?: string } }).priority;
        const pSlug = rawPriority?.slug ? rawPriority.slug.toLowerCase() : 'none';
        if (!activeFilters.priority.includes(pSlug)) continue;
      }

      // 2. Assignee filter
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
                  a.toLowerCase() === asg.principal.handle.toLowerCase(),
              );
            }
            return false;
          });
          if (!matchesPrincipal) continue;
        }
      }

      // 3. Label filter
      if (activeFilters.label && activeFilters.label.length > 0) {
        const issueLabels = issue.labels ?? [];
        const matchesLabel = issueLabels.some((lbl) =>
          activeFilters.label?.some(
            (l) =>
              l.toLowerCase() === lbl.name.toLowerCase() ||
              l === lbl.id,
          ),
        );
        if (!matchesLabel) continue;
      }

      // 4. Cycle filter
      if (activeFilters.cycle && activeFilters.cycle.length > 0) {
        if (!issue.cycle_id || !activeFilters.cycle.includes(issue.cycle_id)) {
          continue;
        }
      }

      // 5. Module filter (only if modulesEnabled is true)
      if (modulesEnabled && activeFilters.module && activeFilters.module.length > 0) {
        const issueMods = issue.module_ids ?? [];
        const matchesMod = issueMods.some((m) => activeFilters.module?.includes(m));
        if (!matchesMod) continue;
      }

      // 6. Gate status filter
      if (activeFilters.gate_status && activeFilters.gate_status.length > 0) {
        if (!issue.gate_status || !activeFilters.gate_status.includes(issue.gate_status)) {
          continue;
        }
      }

      // 7. Due date filter
      if (activeFilters.due_date && activeFilters.due_date.length > 0) {
        const today = new Date().toISOString().slice(0, 10);
        const isOverdue =
          issue.due_date &&
          issue.due_date < today &&
          stateGroup !== 'completed' &&
          stateGroup !== 'cancelled';
        if (activeFilters.due_date.includes('overdue') && !isOverdue) continue;
        if (activeFilters.due_date.includes('no_due_date') && issue.due_date) continue;
      }

      // 8. Favorites-only filter
      if (favoritesOnly) {
        if (favVersion < 0) continue;
        try {
          const raw = typeof window !== 'undefined' ? localStorage.getItem('kb_favorite_issues') : null;
          const parsed: unknown = raw ? JSON.parse(raw) : [];
          const favs = Array.isArray(parsed)
            ? (parsed as unknown[]).filter((x): x is string => typeof x === 'string')
            : [];
          if (!favs.includes(issue.key)) continue;
        } catch {
          // ignore
        }
      }

      // 9. Text / Query search filter
      if (searchQuery.trim().length > 0) {
        if (queryMode === 'query') {
          if (!matchesIssueQuery(searchQuery, issue, projectKey)) continue;
        } else {
          const lower = searchQuery.trim().toLowerCase();
          const matchesKey = issue.key.toLowerCase().includes(lower);
          const matchesSummary = issue.summary.toLowerCase().includes(lower);
          const matchesDesc = (issue.description_markdown ?? '').toLowerCase().includes(lower);
          if (!matchesKey && !matchesSummary && !matchesDesc) continue;
        }
      }

      // 10. State visibility evaluation
      const hasExplicitFilterBarState = Boolean(
        activeFilters.state && activeFilters.state.length > 0 && (!isIssuesView || layout === 'table'),
      );
      let isStateVisible = true;
      if (queryHasExplicitState) {
        // Explicit Query Mode state predicate overrides checkbox hiding
        isStateVisible = true;
      } else if (hasExplicitFilterBarState && activeFilters.state) {
        const matchesAll = activeFilters.state.includes('all');
        const matchesActive =
          (activeFilters.state.includes('active') ||
            activeFilters.state.includes('actionable')) &&
          stateGroup !== 'completed' &&
          stateGroup !== 'cancelled';
        const matchesSpecific = activeFilters.state.some(
          (s) =>
            s === stateGroup ||
            (stateName ? normalizeStateKey(s) === normalizeStateKey(stateName) : false) ||
            s === stateId,
        );
        isStateVisible = matchesAll || matchesActive || matchesSpecific;
      } else if (isIssuesView) {
        isStateVisible = isIssueStateVisible(
          { id: stateId, name: stateName, group: stateGroup },
          stateFilterPref,
        );
      }

      if (isStateVisible) {
        visible.push(issue);
      } else {
        hiddenByState.push(issue);
      }
    }

    return { filteredIssues: visible, hiddenByStateIssues: hiddenByState };
  }, [
    issues,
    layout,
    activeFilters,
    stateFilterPref,
    modulesEnabled,
    projectStates,
    favoritesOnly,
    searchQuery,
    queryMode,
    projectKey,
    favVersion,
  ]);

  const hiddenByStateCount = hiddenByStateIssues.length;

  const hiddenExactSearchMatch = useMemo(() => {
    const trimmed = searchQuery.trim().toLowerCase();
    if (!trimmed || hiddenByStateIssues.length === 0) return null;
    const exact = hiddenByStateIssues.find((i) => i.key.toLowerCase() === trimmed);
    if (!exact) return null;
    const resolvedState = resolveIssueStateSummary(exact, projectStates);
    return {
      key: exact.key,
      stateName: resolvedState?.name ?? resolvedState?.group ?? 'Closed',
    };
  }, [searchQuery, hiddenByStateIssues, projectStates]);

  const handleShowAllStates = useCallback(() => {
    const allPref = createAllStatesFilterPreference();
    setStateFilterPref(allPref);
    writeProjectStateFilterCookie(projectKey, allPref);
    setActiveFilters((prev) => {
      const next = { ...prev };
      delete next.state;
      return next;
    });
  }, [projectKey]);

  const handleResetFilters = useCallback(() => {
    const actionablePref = createActionableStateFilterPreference();
    setStateFilterPref(actionablePref);
    writeProjectStateFilterCookie(projectKey, actionablePref);
    setActiveFilters({});
    setSearchQuery('');
    setFavoritesOnly(false);
  }, [projectKey]);

  // Normalize board workflow states and issues so "Todo" and "To Do" match seamlessly (KANBA-164)
  const boardStates: [BoardWorkflowState, ...BoardWorkflowState[]] = useMemo(() => {
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
          color_hex: s.color_hex ?? null,
          ...(wipHard != null ? { wip_hard_limit: wipHard } : {}),
          ...(wipSoft != null ? { wip_soft_limit: wipSoft } : {}),
        };
      }) as unknown as [BoardWorkflowState, ...BoardWorkflowState[]];
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
    onOpenPeek: handleOpenPeek,
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
    isPopoverOrModalOpen:
      isCreateModalOpen || isSaveViewModalOpen || popoverState.isOpen || isStatePopoverOpen,
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

  const handleFieldSelect = (field: QuickFieldType, value: unknown, targetKeyOverride?: string) => {
    const targetKey = targetKeyOverride ?? popoverState.issue?.key;
    if (!targetKey) return;
    const currentIssue = issues.find((i) => i.key === targetKey);
    if (!currentIssue) return;
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

      const curResolvedState = resolveIssueStateSummary(currentIssue, projectStates);
      const curStateId = (currentIssue as { state_id?: string }).state_id ?? curResolvedState?.id ?? '';
      const curStateName = curResolvedState?.name ?? '';

      const targetStateName = targetState?.name ?? sId;
      const isCrossState =
        curStateId !== sId &&
        normalizeStateKey(curStateName) !== normalizeStateKey(targetStateName);

      const targetStateAny = targetState as { wip_hard_limit?: number | null } | undefined;
      if (isCrossState && targetStateAny?.wip_hard_limit != null) {
        const targetCount = issues.filter((i) => {
          if (i.key === targetKey) return false;
          const iResolvedState = resolveIssueStateSummary(i, projectStates);
          const iStateId = (i as { state_id?: string }).state_id ?? iResolvedState?.id ?? '';
          const iStateName = iResolvedState?.name ?? '';
          return (
            iStateId === targetState?.id ||
            normalizeStateKey(iStateName) === normalizeStateKey(targetStateName)
          );
        }).length;

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

    const prevIssue = issues.find((i) => i.key === targetKey);
    const prevPriority = prevIssue?.priority;
    const prevState = prevIssue?.state;

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
          const nextState = computeStateSummary(sId, projectStates);
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
        void patchProjectIssue(targetKey, { priority: String(value) }).catch((err: unknown) => {
          if (prevPriority) {
            setIssues((p) =>
              p.map((it) => (it.key === targetKey ? { ...it, priority: prevPriority } : it)),
            );
          }
          const msg = err instanceof Error ? err.message : 'Failed to update priority';
          window.dispatchEvent(
            new CustomEvent('kb:alert', { detail: { type: 'error', message: msg } }),
          );
        });
      } else if (field === 'state') {
        const sId = String(value);
        const desired = computeStateSummary(sId, projectStates);
        const resolvedUuid = resolveStateUuid(desired, projectStates);
        if (resolvedUuid) {
          const patchPayload: Record<string, unknown> = { state_id: resolvedUuid };
          if (overrideReason) {
            patchPayload.override_wip = true;
            patchPayload.wip_override_reason = overrideReason;
          }
          void patchProjectIssue(targetKey, patchPayload).catch((err: unknown) => {
            if (prevState) {
              setIssues((p) =>
                p.map((it) => (it.key === targetKey ? { ...it, state: prevState } : it)),
              );
            }
            const msg = err instanceof Error ? err.message : 'Failed to transition state';
            window.dispatchEvent(
              new CustomEvent('kb:alert', { detail: { type: 'error', message: msg } }),
            );
          });
        }
      }
    }
  };

  const boardIssues: BoardIssue[] = useMemo(() => {
    const fallbackStateId = boardStates[0].id;
    return filteredIssues.map((issue, idx) => {
      const explicitStateId = (issue as { state_id?: string }).state_id;
      const resolvedState = resolveIssueStateSummary(issue, projectStates);

      const stateId = resolvedState?.id ?? explicitStateId;
      const stateName = resolvedState?.name ?? '';
      const stateGroup = resolvedState?.group;

      const exactMatch = boardStates.find((s) => s.id === stateId);
      const nameMatch = stateName
        ? boardStates.find((s) => normalizeStateKey(s.name) === normalizeStateKey(stateName))
        : undefined;
      const groupMatch = stateGroup ? boardStates.find((s) => s.group === stateGroup) : undefined;
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

      const rawPriority = (issue as { priority?: { slug?: string; label?: string } }).priority;
      const pSlug = rawPriority?.slug ?? 'none';
      const pLabel = rawPriority?.label ?? 'None';

      return {
        id: issue.id,
        key: issue.key,
        summary: issue.summary,
        state_id: resolvedStateId,
        state: resolvedState
          ? {
              id: resolvedState.id ?? resolvedStateId,
              name: resolvedState.name ?? stateName,
              group: (resolvedState.group ?? 'unstarted') as StateGroup,
              color_hex: (resolvedState as { color_hex?: string | null | undefined }).color_hex ?? null,
            }
          : undefined,
        priority: {
          id: pSlug,
          slug: pSlug,
          label: pLabel,
        },
        board_rank: issue.board_rank ?? String(idx + 1).padStart(6, '0'),
        assignees: boardAssignees,
        due_date: issue.due_date ?? null,
        gate_status: gateStatus,
        has_explicit_acl: Boolean(issue.has_explicit_acl),
      };
    });
  }, [filteredIssues, boardStates, projectStates]);

  // 2D Swimlane condition: layout === 'board' and custom grouping or sub-grouping
  const is2DSwimlane = layout === 'board' && (subGroupBy !== 'none' || groupBy !== 'state');

  const [isMobileViewport, setIsMobileViewport] = useState<boolean>(() => {
    return typeof window !== 'undefined' && (window.innerWidth <= 767 || window.innerHeight <= 540);
  });

  useEffect(() => {
    const handleResize = (): void => {
      setIsMobileViewport(window.innerWidth <= 767 || window.innerHeight <= 540);
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const [railSortBy, setRailSortBy] = useState<IssueSortOption>('updated');
  const [railSortDir, setRailSortDir] = useState<'asc' | 'desc'>('desc');

  const sortedRailIssues = useMemo(() => {
    return sortIssuesList(filteredIssues, railSortBy, railSortDir);
  }, [filteredIssues, railSortBy, railSortDir]);

  // Active peek key for 3-pane split list view (auto-selecting first issue if none specified, unless mobile/landscape or explicitly closed)
  const activePeekKey = useMemo(() => {
    const firstRailIssue = sortedRailIssues[0];
    if (sortedRailIssues.length === 0 || !firstRailIssue) {
      return peekParam && peekParam !== 'none' ? peekParam : null;
    }
    const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    const historyState =
      typeof window !== 'undefined'
        ? (window.history.state as { suppressAutoPeek?: boolean; usr?: { suppressAutoPeek?: boolean } } | null)
        : null;
    const isExplicitlyClosed =
      Boolean(closedSplitKey) ||
      searchParams?.get('closed') === '1' ||
      searchParams?.get('peek') === 'none' ||
      Boolean(historyState?.suppressAutoPeek ?? historyState?.usr?.suppressAutoPeek);

    if (peekParam) {
      if (peekParam === 'none') {
        return null;
      }
      const existsInList = sortedRailIssues.some((i) => i.key === peekParam);
      if (existsInList) {
        return peekParam;
      }
      if (isMobileViewport || isExplicitlyClosed) {
        return null;
      }
      return firstRailIssue.key;
    }
    if (isMobileViewport || isExplicitlyClosed) {
      return null;
    }
    return firstRailIssue.key;
  }, [peekParam, isMobileViewport, closedSplitKey, sortedRailIssues]);

  useEffect(() => {
    const firstRailIssue = sortedRailIssues[0];
    if (
      layout === 'list' &&
      !isMobileViewport &&
      peekParam &&
      peekParam !== 'none' &&
      firstRailIssue &&
      !sortedRailIssues.some((i) => i.key === peekParam)
    ) {
      const firstIssueKey = firstRailIssue.key;
      queueMicrotask(() => {
        handleOpenPeek(firstIssueKey);
      });
    }
  }, [layout, isMobileViewport, peekParam, sortedRailIssues, handleOpenPeek]);

  return (
    <QueryClientProvider client={queryClient}>
      <div
        className="issues-workspace issues-workspace-route"
        data-testid="issues-workspace"
        data-layout={layout}
      >
        {isStagedLoading && (
          <div
            data-testid="issues-staged-loading-indicator"
            className="issues-staged-loading-indicator"
            role="status"
            aria-live="polite"
          >
            Loading additional issues...
          </div>
        )}
        {/* 1. Filter and Display Bar */}
      {layout === 'list' ? (
        <IssueNavigatorBar
          projectKey={projectKey}
          workspaceScope={activeWorkspaceSlug}
          issues={issues}
          projectStates={projectStates}
          modulesEnabled={modulesEnabled}
          activeFilters={activeFilters}
          onFiltersChange={setActiveFilters}
          stateFilter={stateFilterPref}
          onStateFilterChange={handleUserStateFilterChange}
          onStatePopoverOpenChange={setIsStatePopoverOpen}
          hiddenCompletedCount={
            searchQuery.trim().length > 0 &&
            !(queryMode === 'query' && hasExplicitStatePredicate(searchQuery))
              ? hiddenByStateCount
              : 0
          }
          hiddenExactMatch={hiddenExactSearchMatch}
          onShowAllStates={handleShowAllStates}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onSearchSubmit={() => {
            setActiveFilters((prev) => ({ ...prev }));
          }}
          queryMode={queryMode}
          onQueryModeChange={handleQueryModeChange}
          favoritesOnly={favoritesOnly}
          onToggleFavoritesOnly={() => {
            setFavoritesOnly((prev) => !prev);
          }}
          savedViews={savedViews}
          activeViewId={activeViewId}
          onSelectSavedView={handleSelectSavedView}
          onExport={handleExport}
          onImport={() => { setCsvModalTab('import'); }}
          onExportReports={() => { setIsReportsModalOpen(true); }}
        />
      ) : (
        <FilterDisplayBar
          projectKey={projectKey}
          workspaceScope={activeWorkspaceSlug}
          activeFilters={activeFilters}
          onFiltersChange={setActiveFilters}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          subGroupBy={subGroupBy}
          onSubGroupByChange={setSubGroupBy}
          modulesEnabled={modulesEnabled}
          isFilterOpen={isFilterOpen}
          onToggleFilterOpen={setIsFilterOpen}
          issues={issues}
          onSaveView={() => { setIsSaveViewModalOpen(true); }}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          queryMode={queryMode}
          onQueryModeChange={handleQueryModeChange}
          onSearchSubmit={() => {
            setActiveFilters((prev) => ({ ...prev }));
          }}
          savedViews={savedViews}
          activeViewId={activeViewId}
          onSelectSavedView={handleSelectSavedView}
          projectStates={projectStates}
          stateFilter={stateFilterPref}
          onStateFilterChange={handleUserStateFilterChange}
          onExport={handleExport}
          onImport={() => { setCsvModalTab('import'); }}
          onExportReports={() => { setIsReportsModalOpen(true); }}
        />
      )}

      {/* 2. Main View: 2D Swimlane Board Grid, 3-pane split list view, or standard ViewHost */}
      {is2DSwimlane ? (
        <SwimlaneBoardGrid
          issues={filteredIssues}
          projectKey={projectKey}
          groupBy={groupBy}
          subGroupBy={subGroupBy}
          modulesEnabled={modulesEnabled}
          projectStates={projectStates}
          selectedIds={selectedIds}
          onToggleSelect={canEdit ? handleToggleSelect : undefined}
          focusedKey={focusedKey}
          onCardClick={handleRowClick}
          currentUserCapabilities={effectiveCaps}
          onStateTransition={(issueKey, targetStateId) => {
            handleFieldSelect('state', targetStateId, issueKey);
          }}
          onCardMove={
            groupBy === 'state'
              ? (issueKey, targetColId) => {
                  handleFieldSelect('state', targetColId, issueKey);
                }
              : undefined
          }
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
              issues={sortedRailIssues}
              isLoading={isInitialLoading || issuesQuery.isLoading}
              projectKey={projectKey}
              projectStates={projectStates}
              modulesEnabled={modulesEnabled}
              selectedIds={selectedIds}
              onToggleSelect={canEdit ? handleToggleSelect : undefined}
              onCreateIssue={canEdit ? handleOpenCreateModal : undefined}
              focusedKey={focusedKey}
              capabilities={effectiveCaps}
              onOpenPeek={handleOpenPeek}
              activeKey={activePeekKey}
              canManageWorkflows={canAdmin}
              sortBy={railSortBy}
              onSortByChange={setRailSortBy}
              sortDir={railSortDir}
              onSortDirChange={setRailSortDir}
              totalProjectIssueCount={issues.length}
              hiddenByStateCount={hiddenByStateCount}
              onShowAllStates={handleShowAllStates}
              onResetFilters={handleResetFilters}
              onOpenFieldPopover={(field, issue, rect) => {
                setPopoverState({
                  isOpen: true,
                  field,
                  issue,
                  anchorRect: rect,
                });
              }}
            />
          </div>
          {activePeekKey && (
            <IssueSurfaceRoot
              mode="split"
              issueKey={activePeekKey}
              projectKey={projectKey}
              issuesList={sortedRailIssues}
              onNavigateIssue={(key: string) => {
                handleOpenPeek(key);
              }}
              projectName={typeof projectMetadata?.name === 'string' ? projectMetadata.name : undefined}
              onClose={() => {
                setClosedSplitKey('__ALL__');
                handleOpenPeek(null);
              }}
            />
          )}
        </div>
      ) : (
        <ViewHost
          layout={layout}
          issues={sortedRailIssues}
          projectKey={projectKey}
          projectStates={projectStates}
          modulesEnabled={modulesEnabled}
          selectedIds={selectedIds}
          onToggleSelect={canEdit ? handleToggleSelect : undefined}
          onSelectAll={canEdit ? handleSelectAll : undefined}
          onOpenPeek={handleOpenPeek}
          onCreateIssue={canEdit ? handleOpenCreateModal : undefined}
          focusedKey={focusedKey}
          capabilities={effectiveCaps}
          totalProjectIssueCount={issues.length}
          hiddenByStateCount={hiddenByStateCount}
          onShowAllStates={handleShowAllStates}
          onResetFilters={handleResetFilters}
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
            const matchedSt = projectStates.find(
              (s) =>
                s.id === targetStateSlug ||
                s.group === (targetStateSlug === 'done' ? 'completed' : 'unstarted'),
            );
            const desiredState: StateSummary = {
              id: matchedSt?.id ?? `state-${targetStateSlug}`,
              name:
                matchedSt?.name ??
                (targetStateSlug.charAt(0).toUpperCase() + targetStateSlug.slice(1)),
              group:
                matchedSt?.group ?? (targetStateSlug === 'done' ? 'completed' : 'unstarted'),
              color_hex: matchedSt?.color_hex ?? null,
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

      {/* 6. Save View Modal */}
      <SaveViewModal
        isOpen={isSaveViewModalOpen}
        onClose={() => { setIsSaveViewModalOpen(false); }}
        projectKey={projectKey}
        layout={layout}
        groupBy={groupBy}
        subGroupBy={subGroupBy}
        activeFilters={activeFilters}
        onSaved={() => {
          setIsSaveViewModalOpen(false);
        }}
      />

      {/* 7. CSV Import & Export Modal (KAN-365 Parity across layouts) */}
      {csvModalTab && (
        <CsvImportExportModal
          isOpen={true}
          onClose={() => { setCsvModalTab(null); }}
          projectKey={projectKey}
          workspaceScope={activeWorkspaceSlug}
          activeFilters={activeFilters}
          searchQuery={searchQuery}
          initialTab={csvModalTab}
          initialExportFormat={csvExportFormat}
        />
      )}

      {/* 8. Reports & Document Export Modal (KAN-365 Parity across layouts) */}
      {isReportsModalOpen && (
        <ReportExportModal
          isOpen={isReportsModalOpen}
          onClose={() => { setIsReportsModalOpen(false); }}
          projectKey={projectKey}
          workspaceSlug={activeWorkspaceSlug}
        />
      )}
    </div>
  </QueryClientProvider>
  );
}
