import type { ComponentType, JSX } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BoardView, type BoardViewProps } from '../board/BoardView.tsx';

export type ViewLayout = 'board' | 'list' | 'grid' | 'calendar';

export interface ViewRegistryEntry {
  id: ViewLayout;
  name: string;
  component: ComponentType<BoardViewProps>;
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
    component: BoardView,
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
  initialLayout?: ViewLayout;
  queryClient?: QueryClient;
}

/**
 * Shared layout host for /projects/:projectKey/issues (KB-P3-37..40).
 */
export function IssuesWorkspaceRoute({
  projectKey,
  initialLayout = 'board',
  queryClient = defaultQueryClient,
}: IssuesWorkspaceRouteProps): JSX.Element {
  const searchParams = new URLSearchParams(window.location.search);
  const rawLayout = searchParams.get('layout');
  const layoutEntry = rawLayout && rawLayout in viewRegistry
    ? viewRegistry[rawLayout as ViewLayout]
    : viewRegistry[initialLayout];
  const LayoutComponent = layoutEntry.component;

  return (
    <QueryClientProvider client={queryClient}>
      <main
        id="main"
        className="issues-workspace"
        data-testid="issues-workspace"
        data-layout={layoutEntry.id}
      >
        <LayoutComponent projectKey={projectKey} />
      </main>
    </QueryClientProvider>
  );
}
