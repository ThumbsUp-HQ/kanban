/**
 * Application Routes & Router Table (KB-P3-34, S6.3, KB-P3-41, KANBA-170, KANBA-166, KANBA-167).
 * react-router v7 data router with layout parameter normalization, regex key validation, S3.4 uniform error view,
 * zero-remount ticket drawer & full-screen surface routing, WorkspaceHomeView, and StandaloneStatusPanel route.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  type JSX,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import {
  IssuesWorkspaceRoute,
  type IssuesWorkspaceRouteProps,
  type ViewLayout,
} from '../features/views/viewRegistry.tsx';
import {
  createBrowserRouter,
  createMemoryRouter,
  Link,
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
import ProjectCustomFieldsSettingsRoute from '../routes/projects/settings/custom-fields';
import { apiClient } from '../api/client';
import type { IssueDetail } from '../features/drawer/slots';
import { LoginPage } from '../features/auth/LoginPage';
import { SetupClaimPage } from '../features/auth/SetupClaimPage';
import { AuthStudioPage } from '../features/admin-auth/AuthStudioPage';
import { DeviceActivatePage } from '../features/oauth/DeviceActivatePage';
import { McpAccessStudio } from '../features/settings/McpAccessStudio';
import { StandaloneStatusPanel } from '../features/standalone/StandaloneStatusPanel';
import { CreateProjectModal, type CreatedProject } from '../features/projects/CreateProjectModal';
import { useSessionGuard } from '../features/auth/useSessionGuard';

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

interface ProjectRouteContextValue {
  readonly projectKey: string;
  readonly projectName: string;
  readonly modulesEnabled: boolean;
}

const ProjectRouteContext = createContext<ProjectRouteContextValue>({
  projectKey: 'KAN',
  projectName: 'kanban',
  modulesEnabled: true,
});

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
 * Validated Project Issues route with layout search parameter normalization
 * and persistent background rendering when `?peek=` drawer is open (KANBA-170, KANBA-164).
 */
export function ProjectIssuesRoute(): JSX.Element {
  const { projectKey: paramKey } = useParams<{ projectKey: string }>();
  const ctx = useContext(ProjectRouteContext);
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const resolvedProjectKey = paramKey ?? ctx.projectKey;
  const rawLayout = searchParams.get('layout');
  const createTrigger = searchParams.get('create');

  useEffect(() => {
    if (rawLayout && !VALID_LAYOUTS.has(rawLayout.toLowerCase())) {
      const next = new URLSearchParams(searchParams);
      next.set('layout', 'list');
      void navigate(`?${next.toString()}`, { replace: true });
    }
  }, [rawLayout, searchParams, navigate]);

  useEffect(() => {
    if (createTrigger === '1') {
      const next = new URLSearchParams(searchParams);
      next.delete('create');
      const qs = next.toString();
      void navigate(qs ? `?${qs}` : '.', { replace: true });
      const timer = setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', bubbles: true }));
      }, 0);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [createTrigger, searchParams, navigate]);

  useEffect(() => {
    const handleCreateIssueEvent = (): void => {
      setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', bubbles: true }));
      }, 0);
    };
    window.addEventListener('kb:create-issue', handleCreateIssueEvent);
    return () => {
      window.removeEventListener('kb:create-issue', handleCreateIssueEvent);
    };
  }, []);

  const normalizedLayout: ViewLayout = (
    rawLayout && VALID_LAYOUTS.has(rawLayout.toLowerCase())
      ? rawLayout.toLowerCase()
      : 'list'
  ) as ViewLayout;

  const isNoModules = searchParams.get('nomodules') === '1';
  const modulesEnabled = isNoModules ? false : ctx.modulesEnabled;

  return (
    <div data-testid="route-placeholder" data-route="/projects/:projectKey/issues">
      <IssuesWorkspaceRoute
        key={`${resolvedProjectKey}-${normalizedLayout}`}
        projectKey={resolvedProjectKey}
        modulesEnabled={modulesEnabled}
        initialLayout={normalizedLayout}
        queryClient={queryClient}
      />
    </div>
  );
}

/**
 * Workspace Root Home View (`/` — KANBA-170, KANBA-166).
 * Verifies initialization/authentication via `useSessionGuard`, loads projects from
 * `GET /api/v1/projects`, and provides 1-click project & work item creation.
 */
export function WorkspaceHomeView(): JSX.Element {
  useSessionGuard();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<CreatedProject[]>([]);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadProjects(): Promise<void> {
      try {
        const res = await fetch('/api/v1/projects', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        if (!res.ok || !active) {
          return;
        }
        const data = (await res.json()) as
          | { items?: CreatedProject[] }
          | CreatedProject[];
        const items = Array.isArray(data) ? data : (data.items ?? []);
        setProjects(items);
      } catch {
        // Offline or unmocked test environment
      }
    }

    void loadProjects();
    const handleCreated = (): void => {
      void loadProjects();
    };
    window.addEventListener('kb:project-created', handleCreated);
    return () => {
      active = false;
      window.removeEventListener('kb:project-created', handleCreated);
    };
  }, []);

  const displayProjects: readonly CreatedProject[] =
    projects.length > 0
      ? projects
      : [
          {
            id: 'default-kan',
            identifier: 'KAN',
            name: 'kanban',
            description_markdown: 'Default workspace project for tracking issues, stickies, and docs.',
            modules_enabled: true,
          },
        ];

  const primaryKey = displayProjects[0]?.identifier ?? 'KAN';

  return (
    <section
      data-testid="route-placeholder"
      data-route="/"
      className="kb-workspace-home"
    >
      <div className="kb-workspace-home-header">
        <div>
          <h1 className="kb-workspace-home-title">
            Workspace Home
          </h1>
          <p className="kb-workspace-home-subtitle">
            Select a project to manage work items, stickies, and documentation, or create a new project.
          </p>
        </div>

        <div className="kb-workspace-home-actions">
          <button
            type="button"
            data-testid="home-create-project-btn"
            className="kb-home-secondary-btn"
            onClick={() => {
              setCreateOpen(true);
            }}
          >
            + Create Project
          </button>
          <button
            type="button"
            data-testid="home-create-issue-btn"
            className="kb-home-primary-btn"
            onClick={() => {
              void navigate(`/projects/${primaryKey}/issues?create=1`);
            }}
          >
            + New Work Item
          </button>
        </div>
      </div>

      <div
        data-testid="workspace-projects-grid"
        className="kb-workspace-projects-grid"
      >
        {displayProjects.map((proj) => (
          <div
            key={proj.identifier}
            data-testid={`project-card-${proj.identifier}`}
            className="kb-project-card"
          >
            <div>
              <div className="kb-project-card-header">
                <span className="kb-project-card-name">
                  ⚡ {proj.name}
                </span>
                <span className="kb-project-card-key">
                  {proj.identifier}
                </span>
              </div>
              <p className="kb-project-card-desc">
                {proj.description_markdown && proj.description_markdown.length > 0
                  ? proj.description_markdown
                  : 'Project workspace for issues, cycles, and docs.'}
              </p>
            </div>

            <div className="kb-project-card-links">
              <Link
                to={`/projects/${proj.identifier}/issues`}
                className="kb-project-card-primary-link"
              >
                Work Items →
              </Link>
              <Link
                to={`/projects/${proj.identifier}/issues?layout=board`}
                className="kb-project-card-secondary-link"
              >
                Board
              </Link>
              <Link
                to={`/projects/${proj.identifier}/overview`}
                className="kb-project-card-secondary-link"
              >
                Stickies
              </Link>
              <Link
                to={`/projects/${proj.identifier}/docs`}
                className="kb-project-card-secondary-link"
              >
                Docs
              </Link>
              <Link
                to={`/projects/${proj.identifier}/settings/custom-fields`}
                className="kb-project-card-secondary-link"
              >
                Custom Fields
              </Link>
            </div>
          </div>
        ))}
      </div>

      <CreateProjectModal
        isOpen={createOpen}
        onClose={() => {
          setCreateOpen(false);
        }}
        onCreated={(created) => {
          setProjects((prev) => [...prev, created]);
        }}
      />
    </section>
  );
}

export function DraftsWorkspaceView(): JSX.Element {
  return (
    <section data-testid="drafts-view" className="kb-workspace-section">
      <h1>Drafts</h1>
      <p>Work item drafts saved before publishing to a project.</p>
      <Link to="/projects/KAN/issues?create=1">Create a new work item →</Link>
    </section>
  );
}

export function YourWorkView(): JSX.Element {
  return (
    <section data-testid="your-work-view" className="kb-workspace-section">
      <h1>Your work</h1>
      <p>Assigned and subscribed work items across your workspace projects.</p>
      <Link to="/projects/KAN/issues">View project work items →</Link>
    </section>
  );
}

export function ProjectCyclesView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
  return (
    <section data-testid="project-cycles-view" className="kb-workspace-section">
      <h1>Cycles ({key})</h1>
      <p>Time-boxed sprint cycles for grouping and tracking project velocity.</p>
      <Link to={`/projects/${key}/issues`}>Filter work items by cycle →</Link>
    </section>
  );
}

export function ProjectModulesView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
  return (
    <section data-testid="project-modules-view" className="kb-workspace-section">
      <h1>Modules ({key})</h1>
      <p>Feature modules and sub-project groupings for {key}.</p>
      <Link to={`/projects/${key}/issues`}>View module work items →</Link>
    </section>
  );
}

export function ProjectSavedViewsView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
  return (
    <section data-testid="project-views-view" className="kb-workspace-section">
      <h1>Views ({key})</h1>
      <p>Switch between saved layouts and filter presets for {key}:</p>
      <div className="kb-views-links-row">
        <Link to={`/projects/${key}/issues?layout=list`}>List View</Link>
        <Link to={`/projects/${key}/issues?layout=board`}>Board View</Link>
        <Link to={`/projects/${key}/issues?layout=table`}>Table View</Link>
        <Link to={`/projects/${key}/issues?layout=calendar`}>Calendar View</Link>
        <Link to={`/projects/${key}/issues?layout=timeline`}>Timeline View</Link>
      </div>
    </section>
  );
}

export function StandaloneStatusRoute(): JSX.Element {
  const navigate = useNavigate();
  return (
    <div data-testid="standalone-status-route">
      <StandaloneStatusPanel
        onClose={() => {
          void navigate('/');
        }}
      />
    </div>
  );
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
  const resolvedKey = projectKey ?? 'KAN';

  return (
    <ProjectRouteContext.Provider
      value={{
        projectKey: resolvedKey,
        projectName,
        modulesEnabled,
      }}
    >
      <AppShell
        projectKey={resolvedKey}
        projectName={projectName}
        modulesEnabled={modulesEnabled}
      />
    </ProjectRouteContext.Provider>
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
            path: 'cycles',
            element: <ProjectCyclesView />,
          },
          {
            path: 'modules',
            element: <ProjectModulesView />,
          },
          {
            path: 'views',
            element: <ProjectSavedViewsView />,
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
          {
            path: 'settings/mcp',
            element: <McpAccessStudio tier="project" />,
          },
          {
            path: 'settings/custom-fields',
            element: <ProjectCustomFieldsSettingsRoute />,
          },
        ],
      },
      {
        path: 'activate',
        element: <DeviceActivatePage />,
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
            element: <WorkspaceHomeView />,
          },
          {
            path: 'drafts',
            element: <DraftsWorkspaceView />,
          },
          {
            path: 'your-work',
            element: <YourWorkView />,
          },
          {
            path: 'stickies',
            element: <WorkspaceStickiesView />,
          },
          {
            path: 'settings/mcp',
            element: <McpAccessStudio tier="personal" />,
          },
          {
            path: 'workspaces/settings/mcp',
            element: <McpAccessStudio tier="workspace" />,
          },
          {
            path: 'admin/mcp',
            element: <McpAccessStudio tier="global" />,
          },
          {
            path: 'admin/auth',
            element: <AuthStudioPage />,
          },
          {
            path: 'admin/standalone',
            element: <StandaloneStatusRoute />,
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
 * Legacy helper kept for API surface compatibility; `/projects/:projectKey/issues`
 * now routes directly through `AppShell` -> `ProjectIssuesRoute`.
 */
export function AppRoutes(): JSX.Element | null {
  return null;
}
