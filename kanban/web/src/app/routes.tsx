/**
 * Application Routes & Router Table (KB-P3-34, S6.3).
 * react-router v7 data router with layout parameter normalization, regex key validation, and S3.4 uniform error view.
 */

import React, { useEffect, type JSX } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import { IssuesWorkspaceRoute } from '../features/views/viewRegistry.tsx';
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

export function ProjectIssueDetailRoute(): JSX.Element {
  return <RoutePlaceholder route="/projects/:projectKey/issues/:issueKey" />;
}

export function ProjectOverviewRoute(): JSX.Element {
  return <RoutePlaceholder route="/projects/:projectKey/overview" />;
}

export function ProjectDocsRoute(): JSX.Element {
  return <RoutePlaceholder route="/projects/:projectKey/docs" />;
}

export function ProjectDocPageRoute(): JSX.Element {
  return <RoutePlaceholder route="/projects/:projectKey/docs/:pageId" />;
}

export function DevStoryRoute(): JSX.Element {
  const loc = useLocation();
  if (loc.pathname === '/__dev/tokens') return <TokenStory />;
  if (loc.pathname === '/__dev/emoji') return <EmojiStory />;
  if (loc.pathname === '/__dev/editor') return <EditorStory />;
  if (loc.pathname === '/__dev/media') return <MediaStory />;
  if (loc.pathname === '/__dev/realtime') return <RealtimeStory />;
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
        element: <RootShellLayout />,
        children: [
          {
            index: true,
            element: <RoutePlaceholder route="/" />,
          },
          {
            path: 'stickies',
            element: <RoutePlaceholder route="/stickies" />,
          },
          {
            path: 'login',
            element: <RoutePlaceholder route="/login" />,
          },
          {
            path: 'setup',
            element: <RoutePlaceholder route="/setup" />,
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
 * Client router matching /projects/:projectKey/issues (KB-P3-37, KB-P3-34).
 */
export function AppRoutes(): JSX.Element | null {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  const match = /^\/projects\/([^/]+)\/issues\/?$/.exec(pathname);

  if (match?.[1]) {
    const projectKey = decodeURIComponent(match[1]);
    return <IssuesWorkspaceRoute projectKey={projectKey} />;
  }

  return null;
}
