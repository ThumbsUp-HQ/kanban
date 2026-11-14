import type { ComponentType, JSX } from 'react';
import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BoardView, type BoardViewProps } from '../board/BoardView.tsx';
import { ListView } from '../list/ListView';
import { TableView } from '../table/TableView';
import type { IssueItem } from './viewsApi';

export type ViewLayout = 'board' | 'list' | 'table' | 'grid' | 'calendar';

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
  grid: {
    id: 'grid',
    name: 'Grid',
    component: BoardView,
  },
  calendar: {
    id: 'calendar',
    name: 'Calendar',
    component: BoardView,
  },
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
}

export type ViewComponent = ComponentType<ViewComponentProps>;

export const VIEW_REGISTRY: Record<string, ViewComponent> = {
  list: ListView as ViewComponent,
  table: TableView as ViewComponent,
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
  modulesEnabled?: boolean;
  initialIssues?: IssueItem[];
  initialLayout?: ViewLayout;
  queryClient?: QueryClient;
}

/**
 * Shared layout host for /projects/:projectKey/issues (KB-P3-37..40).
 */
export function IssuesWorkspaceRoute({
  projectKey,
  modulesEnabled = true,
  initialIssues,
  initialLayout,
  queryClient = defaultQueryClient,
}: IssuesWorkspaceRouteProps): JSX.Element {
  let searchLayout: string | null = null;
  try {
    const searchParams = new URLSearchParams(window.location.search);
    searchLayout = searchParams.get('layout');
  } catch {
    // window not defined or invalid search
  }

  const defaultLayout: ViewLayout =
    initialLayout ?? (initialIssues && initialIssues.length > 0 ? 'list' : 'board');
  const activeLayout: ViewLayout =
    searchLayout && searchLayout in viewRegistry
      ? (searchLayout as ViewLayout)
      : defaultLayout;

  const [issues] = useState<IssueItem[]>(initialIssues ?? []);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const handleToggleSelect = (key: string, selected: boolean) => {
    setSelectedIds((prev) =>
      selected ? [...prev, key] : prev.filter((id) => id !== key)
    );
  };

  const handleSelectAll = (selected: boolean) => {
    setSelectedIds(selected ? issues.map((i) => i.key) : []);
  };

  const renderContent = () => {
    if (activeLayout === 'board') {
      return <BoardView projectKey={projectKey} />;
    }
    return (
      <ViewHost
        layout={activeLayout}
        issues={issues}
        projectKey={projectKey}
        modulesEnabled={modulesEnabled}
        selectedIds={selectedIds}
        onToggleSelect={handleToggleSelect}
        onSelectAll={handleSelectAll}
      />
    );
  };

  return (
    <QueryClientProvider client={queryClient}>
      <main
        id="main"
        className="issues-workspace issues-workspace-route"
        data-testid="issues-workspace"
        data-layout={activeLayout}
      >
        {renderContent()}
      </main>
    </QueryClientProvider>
  );
}
