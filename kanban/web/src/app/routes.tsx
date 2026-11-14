/**
 * Application Routes & Router Table (KB-P3-34, S6.3, KB-P3-41).
 * react-router v7 data router with layout parameter normalization, regex key validation, S3.4 uniform error view,
 * and zero-remount ticket drawer & full-screen surface routing.
 */

import React, { useEffect, type JSX } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import {
  IssuesWorkspaceRoute,
  type IssuesWorkspaceRouteProps,
} from '../features/views/viewRegistry.tsx';
import { FIXTURE_12_ISSUES } from '../features/views/fixtures';
import {
  createBrowserRouter,
  createMemoryRouter,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
  type RouteObject,
} from 'react-router';
import { AppShell } from './AppShell';
import { TokenStory } from '../dev/TokenStory';
import { EmojiStory } from '../dev/EmojiStory';
import { EditorStory } from '../dev/EditorStory';
import { MediaStory } from '../dev/MediaStory';
import { RealtimeStory } from '../dev/RealtimeStory';
import { DrawerStory } from '../dev/DrawerStory';
import { RailStory } from '../dev/RailStory';
import { DrawerActionsStory } from '../dev/DrawerActionsStory';
import { DocsWorkspaceView } from '../features/docs/DocsWorkspaceView';
import { StickiesStory } from '../dev/StickiesStory';
import { ProjectOverviewView } from '../features/stickies/ProjectOverviewView';
import { WorkspaceStickiesView } from '../features/stickies/WorkspaceStickiesView';
import { apiClient } from '../api/client';
import type { IssueDetail } from '../features/drawer/slots';
import { LoginPage } from '../features/auth/LoginPage';
import { SetupClaimPage } from '../features/auth/SetupClaimPage';

export { IssuesWorkspaceRoute, type IssuesWorkspaceRouteProps };

export const PROJECT_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}$/;
export const ISSUE_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}-[0-9]{1,9}$/;

export const VALID_LAYOUTS = new Set([
  'list',
  'board',
  'table',
  'calendar',
  'timeline',
]);

/**
 * Uniform 403 / 404 view preventing principal & object enumeration (S3.4).
 */
export function NotFoundView(): JSX.Element {
  return (
    <section data-testid="not-found-view" className="kb-not-found-view">
      <h1>Not found or no access</h1>
      <p>The requested resource does not exist or you do not have permission to view it.</p>
    </section>
  );
}

export function RoutePlaceholder({ route }: { route: string }): JSX.Element {
  return (
    <section data-testid="route-placeholder" data-route={route}>
      <h2>Route: {route}</h2>
    </section>
  );
}

/**
 * Validated Project Issues route with layout search parameter normalization.
 */
export function ProjectIssuesRoute(): JSX.Element {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const rawLayout = searchParams.get('layout');
  useEffect(() => {
    if (rawLayout && !VALID_LAYOUTS.has(rawLayout.toLowerCase())) {
      const next = new URLSearchParams(searchParams);
      next.set('layout', 'list');
      void navigate(`?${next.toString()}`, { replace: true });
    }
  }, [rawLayout, searchParams, navigate]);

  return <RoutePlaceholder route="/projects/:projectKey/issues" />;
}

export function FullScreenIssueRoute(): JSX.Element {
  const { issueKey } = useParams<{ issueKey: string }>();
  const { data: issue } = useQuery<IssueDetail>({
    queryKey: qk.issue(issueKey ?? ''),
    queryFn: async () => {
      return (await apiClient.get(
        '/api/v1/issues/{issue_key}',
        { params: { issue_key: issueKey ?? '' } },
      )) as unknown as IssueDetail;
    },
    enabled: Boolean(issueKey),
  });

  useEffect(() => {
    if (issueKey) {
      document.title = issue?.summary ? `${issueKey} - ${issue.summary}` : issueKey;
    }
  }, [issueKey, issue?.summary]);

  return <div data-testid="full-screen-route-anchor" />;
}

export function ProjectIssueDetailRoute(): JSX.Element {
  return <FullScreenIssueRoute />;
}

export function ProjectOverviewRoute(): JSX.Element {
  return <ProjectOverviewView />;
}

export function ProjectDocsRoute(): JSX.Element {
  return <DocsWorkspaceView />;
}

export function ProjectDocPageRoute(): JSX.Element {
  return <DocsWorkspaceView />;
}

export function DevStoryRoute(): JSX.Element {
  const loc = useLocation();
  if (loc.pathname === '/__dev/tokens') return <TokenStory />;
  if (loc.pathname === '/__dev/emoji') return <EmojiStory />;
  if (loc.pathname === '/__dev/editor') return <EditorStory />;
  if (loc.pathname === '/__dev/media') return <MediaStory />;
  if (loc.pathname === '/__dev/realtime') return <RealtimeStory />;
  if (loc.pathname === '/__dev/drawer') return <DrawerStory />;
  if (loc.pathname === '/__dev/drawer-rail' || loc.pathname === '/__dev/rail') return <RailStory />;
  if (loc.pathname === '/__dev/drawer-actions') return <DrawerActionsStory />;
  if (loc.pathname === '/__dev/stickies') return <StickiesStory />;
  return <NotFoundView />;
}

/**
 * Guards project route validation before mounting shell or issuing fetch calls.
 */
export function ProjectRouteContainer(): JSX.Element {
  const { projectKey, issueKey } = useParams<{
    projectKey?: string;
    issueKey?: string;
  }>();

  const isValidProject = Boolean(projectKey && PROJECT_KEY_REGEX.test(projectKey));
  const isValidIssue = issueKey === undefined || ISSUE_KEY_REGEX.test(issueKey);

  const projectQuery = useQuery({
    queryKey: qk.project(projectKey ?? ''),
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/v1/projects/${projectKey ?? ''}`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
        signal,
      });
      if (!res.ok) {
        return null;
      }
      return (await res.json()) as { name?: string; modules_enabled?: boolean };
    },
    enabled: isValidProject && isValidIssue,
    staleTime: 60000,
  });

  if (!isValidProject || !isValidIssue) {
    return <NotFoundView />;
  }

  const modulesEnabled = projectQuery.data?.modules_enabled ?? true;
  const projectName = projectQuery.data?.name ?? 'kanban';

  return (
    <AppShell
      projectKey={projectKey}
      projectName={projectName}
      modulesEnabled={modulesEnabled}
    />
  );
}

export function RootShellLayout(): JSX.Element {
  return <AppShell projectKey="KAN" />;
}

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    children: [
      {
        path: 'projects/:projectKey',
        element: <ProjectRouteContainer />,
        children: [
          {
            path: 'issues',
            element: <ProjectIssuesRoute />,
          },
          {
            path: 'issues/:issueKey',
            element: <ProjectIssueDetailRoute />,
          },
          {
            path: 'overview',
            element: <ProjectOverviewRoute />,
          },
          {
            path: 'docs',
            element: <ProjectDocsRoute />,
          },
          {
            path: 'docs/:pageId',
            element: <ProjectDocPageRoute />,
          },
        ],
      },
      {
        path: 'login',
        element: <LoginPage />,
      },
      {
        path: 'setup',
        element: <SetupClaimPage />,
      },
      {
        element: <RootShellLayout />,
        children: [
          {
            index: true,
            element: <RoutePlaceholder route="/" />,
          },
          {
            path: 'stickies',
            element: <WorkspaceStickiesView />,
          },
          {
            path: 'admin/auth',
            element: <RoutePlaceholder route="/admin/auth" />,
          },
          {
            path: '__dev/*',
            element: <DevStoryRoute />,
          },
          {
            path: '*',
            element: <NotFoundView />,
          },
        ],
      },
    ],
  },
];

export function createAppRouter(
  initialEntries?: string[],
): ReturnType<typeof createBrowserRouter | typeof createMemoryRouter> {
  if (initialEntries && initialEntries.length > 0) {
    return createMemoryRouter(appRoutes, { initialEntries });
  }
  return createBrowserRouter(appRoutes);
}

/**
 * Client router matching /projects/:projectKey/issues (KB-P3-37, KB-P3-34, KB-P3-38).
 */
export function AppRoutes(): JSX.Element | null {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  const search = typeof window !== 'undefined' ? window.location.search : '';

  // If opening ticket drawer (?peek=), let AppShell with IssueSurface handle it
  if (search.includes('peek=')) {
    return null;
  }

  const match = /^\/projects\/([^/]+)\/issues\/?$/.exec(pathname);

  if (match?.[1]) {
    const projectKey = decodeURIComponent(match[1]);
    const isNoModules =
      pathname.includes('nomodules') ||
      (typeof window !== 'undefined' && window.location.search.includes('nomodules=1'));
    return (
      <IssuesWorkspaceRoute
        projectKey={projectKey}
        modulesEnabled={!isNoModules}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );
  }

  return null;
}
