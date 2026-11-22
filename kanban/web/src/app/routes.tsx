/**
 * Application Routes & Router Table (KB-P3-34, S6.3, KB-P3-41, KANBA-170, KANBA-166, KANBA-167).
 * react-router v7 data router with layout parameter normalization, regex key validation, S3.4 uniform error view,
 * zero-remount ticket drawer & full-screen surface routing, WorkspaceHomeView, and StandaloneStatusPanel route.
 */

import React, {
  useCallback,
  useContext,
  useEffect,
  useState,
  type JSX,
} from 'react';
import { useQuery, useMutation, useQueryClient, QueryClientContext } from '@tanstack/react-query';
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
  Navigate,
  Outlet,
  useInRouterContext,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
  type RouteObject,
} from 'react-router';
import { AppShell } from './AppShell';
import type { AccessManifestData } from './HeaderPills';
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
import { IconStory } from '../dev/IconStory';
import { ProjectOverviewView } from '../features/stickies/ProjectOverviewView';
import { WorkspaceStickiesView } from '../features/stickies/WorkspaceStickiesView';
import ProjectCustomFieldsSettingsRoute from '../routes/projects/settings/custom-fields';
import { apiClient, apiFetch } from '../api/client';
import { RouteErrorBoundary } from '../components/error/AppErrorModal';
import type { IssueDetail } from '../features/drawer/slots';
import { ProjectSettingsPage } from '../features/settings/ProjectSettingsPage';
import { WorkspaceSettingsPage } from '../features/settings/WorkspaceSettingsPage';
import { LoginPage } from '../features/auth/LoginPage';
import { SetupClaimPage } from '../features/auth/SetupClaimPage';
import { AuthStudioPage } from '../features/admin-auth/AuthStudioPage';
import { AiStudioPage } from '../features/admin-ai/AiStudioPage';
import { AgentStudioPage } from '../features/admin-agents/AgentStudioPage';
import { RunnerStudioPage } from '../features/admin-runners/RunnerStudioPage';
import { AdminDiagnosticsStudio } from '../features/admin/AdminDiagnosticsStudio';
import { DeviceActivatePage } from '../features/oauth/DeviceActivatePage';
import { McpAccessStudio } from '../features/settings/McpAccessStudio';
import { OAuthClientGovernanceStudio } from '../features/oauth/OAuthClientGovernanceStudio';
import { PlaneImportStudio } from '../features/admin-imports/PlaneImportStudio';
import { PersonalSettingsPage } from '../features/settings/PersonalSettingsPage';
import { AboutPage } from '../features/about/AboutPage';
import { WorkflowStudioPage } from '../features/workflows/WorkflowStudioPage';
import { StandaloneStatusPanel } from '../features/standalone/StandaloneStatusPanel';
import { DocsCenterPage } from '../features/docs-center/DocsCenterPage';
import { CreateProjectModal, type CreatedProject } from '../features/projects/CreateProjectModal';
import { ProjectSavedViewsView } from '../features/views/ProjectSavedViewsView';
import { useSessionGuard } from '../features/auth/useSessionGuard';
import { useDrafts, deleteDraft, type IssueDraft } from '../features/drafts/draftsStore';
import { fetchProjectStates } from '../features/views/viewsApi';
import { fetchProjectModules } from '../features/drawer-rail/railApi';
import { FlowAnalyticsPage } from '../features/analytics/FlowAnalyticsPage';
import { CycleBurndownChart, type BurndownResponse } from '../features/analytics/charts/CycleBurndownChart';

export { IssuesWorkspaceRoute, type IssuesWorkspaceRouteProps };

export const PROJECT_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}$/;
export const ISSUE_KEY_REGEX = /^[A-Z][A-Z0-9_-]{1,24}-[0-9]{1,18}$/;

export const VALID_LAYOUTS = new Set([
  'list',
  'board',
  'table',
  'calendar',
  'timeline',
]);

import {
  type ProjectRouteContextValue,
  ProjectRouteContext,
  useProjectRouteContext,
} from './ProjectRouteContext';

export {
  type ProjectRouteContextValue,
  ProjectRouteContext,
  useProjectRouteContext,
};

interface NotFoundViewContentProps {
  pathname: string;
  onReturn: () => void;
}

function NotFoundViewContent({
  pathname,
  onReturn,
}: NotFoundViewContentProps): JSX.Element {
  return (
    <section data-testid="not-found-view" className="kb-not-found-view">
      <div className="kb-not-found-card">
        <div className="kb-not-found-badge" aria-hidden="true">
          404
        </div>
        <h1 className="kb-not-found-title">404 - Page Not Found</h1>
        <h2 className="kb-not-found-subtitle">Not found or no access</h2>
        <p className="kb-not-found-message">
          The requested resource{' '}
          <code className="kb-not-found-path" data-testid="not-found-path">
            {pathname || 'unknown'}
          </code>{' '}
          does not exist or you do not have permission to view it.
        </p>
        <button
          type="button"
          className="kb-btn kb-btn-primary kb-not-found-btn"
          data-testid="return-workspace-btn"
          onClick={onReturn}
        >
          Return to Workspace
        </button>
      </div>
    </section>
  );
}

function NotFoundViewRouted(): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <NotFoundViewContent
      pathname={location.pathname}
      onReturn={() => void navigate('/')}
    />
  );
}

function NotFoundViewStatic(): JSX.Element {
  return (
    <NotFoundViewContent
      pathname={typeof window !== 'undefined' ? window.location.pathname : ''}
      onReturn={() => {
        if (typeof window !== 'undefined') {
          window.location.href = '/';
        }
      }}
    />
  );
}

/**
 * Uniform 403 / 404 view preventing principal & object enumeration (S3.4, KANBA-213).
 * Branded SPA 404 with path inspection and Return to Workspace action.
 */
export function NotFoundView(): JSX.Element {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <NotFoundViewRouted />;
  }
  return <NotFoundViewStatic />;
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
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const handleOpenPeek = useCallback(
    (issueKey: string) => {
      const next = new URLSearchParams(searchParams);
      next.set('peek', issueKey);
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

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
        onOpenPeek={handleOpenPeek}
        capabilities={ctx.projectKey ? ctx.capabilities : undefined}
        isProjectAdmin={ctx.projectKey ? ctx.isProjectAdmin : true}
      />
    </div>
  );
}

/**
 * Workspace Root Home View (`/` - KANBA-170, KANBA-166).
 * Verifies initialization/authentication via `useSessionGuard`, loads projects from
 * `GET /api/v1/projects`, and provides 1-click project & work item creation.
 */
function WorkspaceHomeInner({
  currentUser,
}: {
  currentUser: {
    workspace_role?: string;
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
  } | null;
}): JSX.Element {
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
    const handleSwitched = (): void => {
      void loadProjects();
    };
    window.addEventListener('kb:project-created', handleCreated);
    window.addEventListener('kb:workspace-switched', handleSwitched);
    return () => {
      active = false;
      window.removeEventListener('kb:project-created', handleCreated);
      window.removeEventListener('kb:workspace-switched', handleSwitched);
    };
  }, []);

  const isViewer = currentUser?.workspace_role === 'VIEWER' || currentUser?.workspace_role === 'WORKSPACE_GUEST';
  const isExplicitNonAdmin =
    isViewer ||
    currentUser?.workspace_role === 'WORKSPACE_MEMBER' ||
    currentUser?.workspace_role === 'MEMBER' ||
    (currentUser?.workspace_role != null && !currentUser.is_workspace_admin && !currentUser.is_server_admin);
  const canCreateProject = currentUser
    ? ((currentUser.is_workspace_admin ?? false) || (currentUser.is_server_admin ?? false) || !isExplicitNonAdmin)
    : true;
  const displayProjects: readonly CreatedProject[] = projects;
  const canCreateWorkItem =
    !isViewer &&
    displayProjects.length > 0 &&
    displayProjects.some(
      (p) =>
        p.capabilities === undefined ||
        p.capabilities.includes('EDIT') ||
        p.capabilities.includes('ADMIN') ||
        p.is_project_admin,
    );
  const primaryKey = displayProjects[0]?.identifier ?? '';

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
          {canCreateProject && (
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
          )}
          {canCreateWorkItem && (
            <button
              type="button"
              data-testid="home-create-issue-btn"
              className="kb-home-primary-btn"
              onClick={() => {
                if (primaryKey) {
                  void navigate(`/projects/${primaryKey}/issues?create=1`);
                }
              }}
            >
              + New Work Item
            </button>
          )}
        </div>
      </div>

      {displayProjects.length === 0 ? (
        <div data-testid="no-accessible-projects" className="kb-workspace-no-projects">
          No accessible projects
        </div>
      ) : (
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
                {(proj.is_project_admin ?? proj.capabilities?.includes('ADMIN')) && (
                  <Link
                    to={`/projects/${proj.identifier}/settings/custom-fields`}
                    className="kb-project-card-secondary-link"
                  >
                    Custom Fields
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

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

function WorkspaceHomeWithQuery(): JSX.Element {
  const { data: currentUser } = useQuery<{
    workspace_role?: string;
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
  } | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as {
          workspace_role?: string;
          is_server_admin?: boolean;
          is_workspace_admin?: boolean;
        };
      } catch {
        return null;
      }
    },
    staleTime: 60000,
  });

  return <WorkspaceHomeInner currentUser={currentUser ?? null} />;
}

export function WorkspaceHomeView(): JSX.Element {
  const client = useContext(QueryClientContext);
  if (!client) {
    return <WorkspaceHomeInner currentUser={null} />;
  }
  return <WorkspaceHomeWithQuery />;
}

export function DraftsWorkspaceView(): JSX.Element {
  const drafts = useDrafts();
  const navigate = useNavigate();
  const queryClient = useContext(QueryClientContext);
  const routeCtx = useContext(ProjectRouteContext);
  const [projects, setProjects] = useState<{ identifier?: string; key?: string }[]>(() => {
    if (queryClient) {
      const cached = queryClient.getQueryData<
        { identifier?: string; key?: string }[] | { items?: { identifier?: string; key?: string }[] }
      >(['projects']);
      if (cached) {
        return Array.isArray(cached) ? cached : (cached.items ?? []);
      }
    }
    return [];
  });

  useEffect(() => {
    let active = true;
    async function loadProjects(): Promise<void> {
      try {
        const res = await fetch('/api/v1/projects', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        if (!res.ok || !active) return;
        const data = (await res.json()) as
          | { items?: { identifier?: string; key?: string }[] }
          | { identifier?: string; key?: string }[];
        const items = Array.isArray(data) ? data : (data.items ?? []);
        setProjects(items);
      } catch {
        // Fallback / offline / unmocked environment
      }
    }
    void loadProjects();
    return () => {
      active = false;
    };
  }, []);

  const activeOrFirstKey =
    (routeCtx.projectKey && routeCtx.projectKey.trim().length > 0 ? routeCtx.projectKey : undefined) ??
    projects[0]?.identifier ??
    projects[0]?.key;
  const emptyStateCtaLink = activeOrFirstKey
    ? `/projects/${encodeURIComponent(activeOrFirstKey)}/issues?create=1`
    : '/';

  const handlePublishOrResume = async (draft: IssueDraft): Promise<void> => {
    try {
      const payload: Record<string, unknown> = {
        summary: draft.summary,
      };
      if (draft.description) {
        payload.description_markdown = draft.description;
      }
      if (draft.prioritySlug) {
        payload.priority = draft.prioritySlug;
      }

      // Resolve live project states to find matching state_id
      try {
        const liveStates = await fetchProjectStates(draft.projectKey);
        if (draft.stateId) {
          const matched = liveStates.find(
            (s) =>
              s.id === draft.stateId ||
              s.name.toLowerCase() === draft.stateId.toLowerCase().replace(/^state-/, ''),
          );
          if (matched?.id && !matched.id.startsWith('state-')) {
            payload.state_id = matched.id;
          }
        }
      } catch {
        // Ignore fallback
      }

      // Resolve live project modules
      try {
        const liveModules = await fetchProjectModules(draft.projectKey);
        if (draft.moduleIds && draft.moduleIds.length > 0) {
          const validIds = liveModules
            .filter((m) => draft.moduleIds?.includes(m.id))
            .map((m) => m.id);
          if (validIds.length > 0) {
            payload.module_ids = validIds;
          }
        }
      } catch {
        // Ignore fallback
      }

      await apiFetch('POST', '/api/v1/projects/{project_ref}/issues' as never, {
        params: { project_ref: draft.projectKey },
        body: payload,
      });

      deleteDraft(draft.id);
      void navigate(`/projects/${draft.projectKey}/issues`);
      return;
    } catch {
      // Fallback on network error
    }

    deleteDraft(draft.id);
    void navigate(`/projects/${draft.projectKey}/issues?create=1`);
  };

  const handleDelete = (id: string): void => {
    deleteDraft(id);
  };

  return (
    <section data-testid="drafts-view" className="kb-workspace-section">
      <div className="kb-workspace-section-header">
        <h1>Drafts</h1>
        <p>Work item drafts saved before publishing to a project.</p>
      </div>

      {drafts.length === 0 ? (
        <div data-testid="drafts-empty" className="drafts-empty-notice">
          <p>No work item drafts found.</p>
          <Link to={emptyStateCtaLink}>Create a new work item →</Link>
        </div>
      ) : (
        <div className="drafts-grid" data-testid="drafts-list">
          {drafts.map((draft) => (
            <div key={draft.id} className="draft-card" data-testid="draft-card">
              <div className="draft-card-header">
                <span className="mono draft-project-badge">{draft.projectKey}</span>
                <span className="draft-timestamp">
                  {new Date(draft.createdAt).toLocaleDateString()}
                </span>
              </div>
              <h3 className="draft-card-title">{draft.summary}</h3>
              {draft.description && (
                <p className="draft-card-desc">{draft.description}</p>
              )}
              <div className="draft-card-meta">
                {draft.prioritySlug && (
                  <span className="draft-meta-pill">
                    Priority: {draft.prioritySlug}
                  </span>
                )}
                {draft.stateId && (
                  <span className="draft-meta-pill">State: {draft.stateId}</span>
                )}
              </div>
              <div className="draft-card-actions">
                <button
                  type="button"
                  className="quick-create-btn-submit draft-resume-btn"
                  data-testid="draft-resume-btn"
                  onClick={() => {
                    void handlePublishOrResume(draft);
                  }}
                >
                  Resume / Publish to Board
                </button>
                <button
                  type="button"
                  className="quick-create-btn-cancel draft-delete-btn"
                  data-testid="draft-delete-btn"
                  onClick={() => {
                    handleDelete(draft.id);
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

import { YourWorkView } from '../features/your-work/YourWorkView';
export { YourWorkView };

export interface ProjectCycleItem {
  id: string;
  name: string;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
}

function formatStatusLabel(rawStatus?: string): string {
  if (!rawStatus) return 'Upcoming';
  const s = rawStatus.toLowerCase().replace(/_/g, ' ');
  if (s === 'in progress') return 'In Progress';
  if (s === 'upcoming') return 'Upcoming';
  if (s === 'planned') return 'Planned';
  if (s === 'completed') return 'Completed';
  if (s === 'backlog') return 'Backlog';
  if (s === 'paused') return 'Paused';
  if (s === 'cancelled') return 'Cancelled';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatDateOrderError(msg: string): string {
  const lower = msg.toLowerCase();
  if (lower.includes('end_date') || lower.includes('end date')) {
    return 'End date cannot be earlier than start date.';
  }
  if (lower.includes('target_date') || lower.includes('target date')) {
    return 'Target date cannot be earlier than start date.';
  }
  return msg;
}

function ProjectCyclesViewInner({
  projectKey,
  capabilities: propCapabilities,
}: {
  projectKey: string;
  capabilities?: string[] | undefined;
}): JSX.Element {
  const key = projectKey;
  const queryClient = useQueryClient();

  const [newName, setNewName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Edit cycle state
  const [editingCycle, setEditingCycle] = useState<ProjectCycleItem | null>(null);
  const [editName, setEditName] = useState('');
  const [editStartDate, setEditStartDate] = useState('');
  const [editEndDate, setEditEndDate] = useState('');
  const [editErrorMsg, setEditErrorMsg] = useState<string | null>(null);

  // Complete cycle state (with rollover target selector)
  const [completingCycle, setCompletingCycle] = useState<ProjectCycleItem | null>(null);
  const [rolloverTargetId, setRolloverTargetId] = useState('');
  const [completeErrorMsg, setCompleteErrorMsg] = useState<string | null>(null);

  // Active burndown cycle toggle
  const [activeBurndownCycleId, setActiveBurndownCycleId] = useState<string | null>(null);

  const { data: cycleBurndownData, isLoading: isCycleBurndownLoading } = useQuery<BurndownResponse>({
    queryKey: ['cycles', activeBurndownCycleId, 'burndown'],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/cycles/{cycle_id}/burndown' as never, {
        params: { cycle_id: activeBurndownCycleId ?? '' },
      });
      return res as BurndownResponse;
    },
    enabled: Boolean(activeBurndownCycleId),
  });

  const { data: projectData } = useQuery<{ capabilities?: string[] }>({
    queryKey: ['projects', key, 'detail'],
    queryFn: async () => {
      try {
        const res = await apiFetch('GET', '/api/v1/projects/{project_ref}' as never, {
          params: { project_ref: key },
        });
        if (
          res &&
          typeof res === 'object' &&
          'capabilities' in res &&
          Array.isArray(res.capabilities)
        ) {
          return res as { capabilities: string[] };
        }
      } catch {
        // fallback
      }
      return { capabilities: [] };
    },
    enabled: propCapabilities === undefined,
  });

  const capabilities = propCapabilities ?? projectData?.capabilities ?? [];
  const canCreate = capabilities.includes('EDIT') || capabilities.includes('ADMIN') || capabilities.includes('PROJECT_ADMIN');
  const canDelete = capabilities.includes('ADMIN') || capabilities.includes('PROJECT_ADMIN');

  const { data: cycles = [], isLoading } = useQuery<ProjectCycleItem[]>({
    queryKey: ['projects', key, 'cycles'],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/cycles' as never, {
        params: { project_ref: key },
      });
      const data = res as { items?: ProjectCycleItem[] } | ProjectCycleItem[];
      return Array.isArray(data) ? data : data.items ?? [];
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      setErrorMsg(null);
      if (startDate && endDate && endDate < startDate) {
        throw new Error('End date cannot be earlier than start date.');
      }
      return await apiFetch('POST', '/api/v1/projects/{project_ref}/cycles' as never, {
        params: { project_ref: key },
        body: {
          name: newName.trim(),
          ...(startDate ? { start_date: startDate } : {}),
          ...(endDate ? { end_date: endDate } : {}),
        },
      });
    },
    onSuccess: (newCycle: unknown) => {
      setNewName('');
      setStartDate('');
      setEndDate('');
      if (newCycle && typeof newCycle === 'object' && 'id' in newCycle) {
        queryClient.setQueryData<ProjectCycleItem[]>(['projects', key, 'cycles'], (old = []) => [
          ...old,
          newCycle as ProjectCycleItem,
        ]);
      }
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'cycles'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatDateOrderError(err instanceof Error ? err.message : 'Failed to create cycle'));
    },
  });

  const patchMutation = useMutation({
    mutationFn: async () => {
      if (!editingCycle) return null;
      setEditErrorMsg(null);
      if (editStartDate && editEndDate && editEndDate < editStartDate) {
        throw new Error('End date cannot be earlier than start date.');
      }
      return await apiFetch('PATCH', '/api/v1/cycles/{cycle_id}' as never, {
        params: { cycle_id: editingCycle.id },
        body: {
          name: editName.trim(),
          start_date: editStartDate || null,
          end_date: editEndDate || null,
        },
      });
    },
    onSuccess: (updated: unknown) => {
      if (updated && typeof updated === 'object' && 'id' in updated) {
        queryClient.setQueryData<ProjectCycleItem[]>(['projects', key, 'cycles'], (old = []) =>
          old.map((c) => (c.id === (updated as ProjectCycleItem).id ? (updated as ProjectCycleItem) : c))
        );
      }
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'cycles'] });
      setEditingCycle(null);
    },
    onError: (err: unknown) => {
      setEditErrorMsg(formatDateOrderError(err instanceof Error ? err.message : 'Failed to update cycle'));
    },
  });

  const completeMutation = useMutation({
    mutationFn: async () => {
      if (!completingCycle) return null;
      setCompleteErrorMsg(null);
      return await apiFetch('POST', '/api/v1/cycles/{cycle_id}/complete' as never, {
        params: { cycle_id: completingCycle.id },
        body: {
          rollover_to_cycle_id: rolloverTargetId ? rolloverTargetId : null,
        },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'cycles'] });
      setCompletingCycle(null);
    },
    onError: (err: unknown) => {
      setCompleteErrorMsg(err instanceof Error ? err.message : 'Failed to complete cycle');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (cycleId: string) => {
      return await apiFetch('DELETE', '/api/v1/cycles/{cycle_id}' as never, {
        params: { cycle_id: cycleId },
      });
    },
    onSuccess: (_data, cycleId) => {
      queryClient.setQueryData<ProjectCycleItem[]>(['projects', key, 'cycles'], (old = []) =>
        old.filter((c) => c.id !== cycleId)
      );
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'cycles'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete cycle');
    },
  });

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate();
  };

  const handleEditSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!editName.trim()) return;
    patchMutation.mutate();
  };

  const handleCompleteSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    completeMutation.mutate();
  };

  const openEditModal = (cyc: ProjectCycleItem) => {
    setEditingCycle(cyc);
    setEditName(cyc.name);
    setEditStartDate(cyc.start_date ?? '');
    setEditEndDate(cyc.end_date ?? '');
    setEditErrorMsg(null);
  };

  const openCompleteModal = (cyc: ProjectCycleItem) => {
    setCompletingCycle(cyc);
    setRolloverTargetId('');
    setCompleteErrorMsg(null);
  };

  return (
    <section data-testid="project-cycles-view" className="kb-workspace-section">
      <div className="kb-workspace-section-header">
        <h1>Cycles ({key})</h1>
        <p>Time-boxed sprint cycles for grouping and tracking project velocity.</p>
        <div className="kb-chart-actions">
          <Link
            to={`/projects/${key}/analytics`}
            className="kb-btn-secondary"
            data-testid="cycles-flow-analytics-link"
          >
            📊 View Flow Analytics Studio &rarr;
          </Link>
        </div>
      </div>

      {canCreate && (
        <form onSubmit={handleSubmit} className="kb-cycles-create-form" data-testid="create-cycle-form">
          <h3>Create New Cycle</h3>
          {errorMsg && (
            <div className="kb-cycles-error" role="alert" data-testid="cycle-error-banner">
              {errorMsg}
            </div>
          )}
          <div className="kb-form-row">
            <label className="kb-form-field">
              <span className="kb-form-label">Cycle Name</span>
              <input
                type="text"
                className="kb-form-input"
                data-testid="new-cycle-name-input"
                placeholder="Sprint / Cycle name..."
                value={newName}
                onChange={(e) => { setNewName(e.target.value); }}
                required
              />
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">Start Date</span>
              <input
                type="date"
                className="kb-form-input"
                data-testid="new-cycle-start-input"
                value={startDate}
                onChange={(e) => { setStartDate(e.target.value); }}
                title="Start date"
              />
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">End Date</span>
              <input
                type="date"
                className="kb-form-input"
                data-testid="new-cycle-end-input"
                value={endDate}
                onChange={(e) => { setEndDate(e.target.value); }}
                title="End date"
              />
            </label>
            <button
              type="submit"
              className="kb-btn-primary"
              data-testid="create-cycle-btn"
              disabled={createMutation.isPending || !newName.trim()}
            >
              {createMutation.isPending ? 'Creating...' : '+ Create Cycle'}
            </button>
          </div>
        </form>
      )}

      {/* Edit Cycle Modal */}
      {editingCycle && (
        <div className="kb-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="edit-cycle-modal-title">
          <div className="kb-modal" data-testid="edit-cycle-modal">
            <h3 id="edit-cycle-modal-title">Edit Cycle</h3>
            {editErrorMsg && (
              <div className="kb-cycles-error" role="alert" data-testid="edit-cycle-error">
                {editErrorMsg}
              </div>
            )}
            <form onSubmit={handleEditSubmit}>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Cycle Name</span>
                <input
                  type="text"
                  className="kb-form-input"
                  data-testid="edit-cycle-name-input"
                  value={editName}
                  onChange={(e) => { setEditName(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Start Date</span>
                <input
                  type="date"
                  className="kb-form-input"
                  data-testid="edit-cycle-start-input"
                  value={editStartDate}
                  onChange={(e) => { setEditStartDate(e.target.value); }}
                />
              </div>
              <div className="kb-form-field" style={{ marginBottom: 16 }}>
                <span className="kb-form-label">End Date</span>
                <input
                  type="date"
                  className="kb-form-input"
                  data-testid="edit-cycle-end-input"
                  value={editEndDate}
                  onChange={(e) => { setEditEndDate(e.target.value); }}
                />
              </div>
              <div className="kb-modal-footer">
                <button
                  type="button"
                  className="kb-btn-secondary"
                  data-testid="cancel-edit-cycle-btn"
                  onClick={() => { setEditingCycle(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-btn-primary"
                  data-testid="save-edit-cycle-btn"
                  disabled={patchMutation.isPending || !editName.trim()}
                >
                  {patchMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Complete Cycle Modal */}
      {completingCycle && (
        <div className="kb-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="complete-cycle-modal-title">
          <div className="kb-modal" data-testid="complete-cycle-modal">
            <h3 id="complete-cycle-modal-title">Complete Cycle ({completingCycle.name})</h3>
            <p style={{ fontSize: 13, color: 'var(--fg-secondary)', marginBottom: 16 }}>
              Select a target cycle to roll over any unfinished issues, or send them to the backlog.
            </p>
            {completeErrorMsg && (
              <div className="kb-cycles-error" role="alert" data-testid="complete-cycle-error">
                {completeErrorMsg}
              </div>
            )}
            <form onSubmit={handleCompleteSubmit}>
              <div className="kb-form-field" style={{ marginBottom: 16 }}>
                <span className="kb-form-label">Rollover Unfinished Issues To</span>
                <select
                  className="kb-form-input"
                  data-testid="rollover-target-select"
                  value={rolloverTargetId}
                  onChange={(e) => { setRolloverTargetId(e.target.value); }}
                >
                  <option value="">No rollover (Send to Backlog)</option>
                  {cycles
                    .filter((c) => c.id !== completingCycle.id && c.status?.toLowerCase() !== 'completed')
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({formatStatusLabel(c.status)})
                      </option>
                    ))}
                </select>
              </div>
              <div className="kb-modal-footer">
                <button
                  type="button"
                  className="kb-btn-secondary"
                  data-testid="cancel-complete-cycle-btn"
                  onClick={() => { setCompletingCycle(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-btn-primary"
                  data-testid="confirm-complete-cycle-btn"
                  disabled={completeMutation.isPending}
                >
                  {completeMutation.isPending ? 'Completing...' : 'Complete Cycle'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="kb-cycles-list-wrapper">
        {isLoading && <p>Loading cycles...</p>}
        {!isLoading && cycles.length === 0 && (
          <p className="kb-empty-text">No cycles defined yet. Create your first sprint cycle above.</p>
        )}
        <ul className="kb-cycles-list" data-testid="cycles-list">
          {cycles.map((cyc) => {
            const statusKey = cyc.status?.toLowerCase().replace(/_/g, '-') ?? 'upcoming';
            const isCompleted = statusKey === 'completed';
            return (
              <li key={cyc.id} className="kb-cycle-item" data-testid={`cycle-item-${cyc.id}`}>
                <div className="kb-cycle-info">
                  <strong>{cyc.name}</strong>
                  <span
                    className={`kb-status-pill kb-status-pill--${statusKey}`}
                    data-testid={`cycle-status-${cyc.id}`}
                  >
                    {formatStatusLabel(cyc.status)}
                  </span>
                  <span
                    className="kb-cycle-dates"
                    data-testid={`cycle-dates-${cyc.id}`}
                    aria-label={`Start: ${cyc.start_date ?? 'TBD'}, End: ${cyc.end_date ?? 'TBD'}`}
                  >
                    {cyc.start_date ?? 'TBD'} → {cyc.end_date ?? 'TBD'}
                  </span>
                </div>
                <div className="kb-cycle-actions">
                  <Link to={`/projects/${key}/issues?cycle=${cyc.id}`} style={{ marginRight: 8, fontSize: 13 }}>
                    Filter work items &rarr;
                  </Link>
                  <button
                    type="button"
                    className="kb-btn-secondary"
                    data-testid={`view-burndown-btn-${cyc.id}`}
                    onClick={() => {
                      setActiveBurndownCycleId((prev) => (prev === cyc.id ? null : cyc.id));
                    }}
                  >
                    {activeBurndownCycleId === cyc.id ? 'Hide Burndown' : 'Burndown'}
                  </button>
                  {canCreate && (
                    <button
                      type="button"
                      className="kb-btn-secondary"
                      data-testid={`edit-cycle-btn-${cyc.id}`}
                      onClick={() => { openEditModal(cyc); }}
                    >
                      Edit
                    </button>
                  )}
                  {canCreate && !isCompleted && (
                    <button
                      type="button"
                      className="kb-btn-secondary"
                      data-testid={`complete-cycle-btn-${cyc.id}`}
                      onClick={() => { openCompleteModal(cyc); }}
                    >
                      Complete
                    </button>
                  )}
                  {canDelete && (
                    <button
                      type="button"
                      className="kb-btn-danger"
                      data-testid={`delete-cycle-btn-${cyc.id}`}
                      onClick={() => { deleteMutation.mutate(cyc.id); }}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  )}
                </div>
                {activeBurndownCycleId === cyc.id && (
                  <div
                    className="kb-cycle-burndown-container"
                    data-testid={`cycle-burndown-container-${cyc.id}`}
                  >
                    {isCycleBurndownLoading ? (
                      <p className="kb-flow-empty">Loading cycle burndown...</p>
                    ) : (
                      <CycleBurndownChart burndown={cycleBurndownData} cycleName={cyc.name} />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

export function ProjectCyclesView({
  capabilities,
}: {
  capabilities?: string[] | undefined;
} = {}): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const ctx = useContext(ProjectRouteContext);
  const key = projectKey ?? (ctx.projectKey || 'KAN');
  const client = useContext(QueryClientContext);
  if (!client) {
    return (
      <section data-testid="project-cycles-view" className="kb-workspace-section">
        <h1>Cycles ({key})</h1>
        <p>Time-boxed sprint cycles for grouping and tracking project velocity.</p>
        <Link to={`/projects/${key}/issues`}>Filter work items by cycle →</Link>
      </section>
    );
  }
  return (
    <ProjectCyclesViewInner
      projectKey={key}
      capabilities={capabilities ?? (ctx.projectKey ? ctx.capabilities : undefined)}
    />
  );
}

export interface ProjectModuleItem {
  id: string;
  name: string;
  status?: string;
  start_date?: string | null;
  target_date?: string | null;
  description_markdown?: string | null;
}

function ProjectModulesViewInner({
  projectKey,
  capabilities: propCapabilities,
}: {
  projectKey: string;
  capabilities?: string[] | undefined;
}): JSX.Element {
  const key = projectKey;
  const queryClient = useQueryClient();

  const [newName, setNewName] = useState('');
  const [status, setStatus] = useState('planned');
  const [startDate, setStartDate] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [description, setDescription] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Edit module state
  const [editingModule, setEditingModule] = useState<ProjectModuleItem | null>(null);
  const [editName, setEditName] = useState('');
  const [editStatus, setEditStatus] = useState('planned');
  const [editStartDate, setEditStartDate] = useState('');
  const [editTargetDate, setEditTargetDate] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editErrorMsg, setEditErrorMsg] = useState<string | null>(null);

  const { data: projectData } = useQuery<{ capabilities?: string[] }>({
    queryKey: ['projects', key, 'detail'],
    queryFn: async () => {
      try {
        const res = await apiFetch('GET', '/api/v1/projects/{project_ref}' as never, {
          params: { project_ref: key },
        });
        if (
          res &&
          typeof res === 'object' &&
          'capabilities' in res &&
          Array.isArray(res.capabilities)
        ) {
          return res as { capabilities: string[] };
        }
      } catch {
        // fallback
      }
      return { capabilities: [] };
    },
    enabled: propCapabilities === undefined,
  });

  const capabilities = propCapabilities ?? projectData?.capabilities ?? [];
  const canCreate = capabilities.includes('EDIT') || capabilities.includes('ADMIN') || capabilities.includes('PROJECT_ADMIN');
  const canDelete = capabilities.includes('ADMIN') || capabilities.includes('PROJECT_ADMIN');

  const { data: modules = [], isLoading } = useQuery<ProjectModuleItem[]>({
    queryKey: ['projects', key, 'modules'],
    queryFn: async () => {
      const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/modules' as never, {
        params: { project_ref: key },
      });
      const data = res as { items?: ProjectModuleItem[] } | ProjectModuleItem[];
      return Array.isArray(data) ? data : data.items ?? [];
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      setErrorMsg(null);
      if (startDate && targetDate && targetDate < startDate) {
        throw new Error('Target date cannot be earlier than start date.');
      }
      return await apiFetch('POST', '/api/v1/projects/{project_ref}/modules' as never, {
        params: { project_ref: key },
        body: {
          name: newName.trim(),
          status,
          ...(startDate ? { start_date: startDate } : {}),
          ...(targetDate ? { target_date: targetDate } : {}),
          ...(description.trim() ? { description_markdown: description.trim() } : {}),
        },
      });
    },
    onSuccess: (newMod: unknown) => {
      setNewName('');
      setStatus('planned');
      setStartDate('');
      setTargetDate('');
      setDescription('');
      if (newMod && typeof newMod === 'object' && 'id' in newMod) {
        queryClient.setQueryData<ProjectModuleItem[]>(['projects', key, 'modules'], (old = []) => [
          ...old,
          newMod as ProjectModuleItem,
        ]);
      }
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'modules'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatDateOrderError(err instanceof Error ? err.message : 'Failed to create module'));
    },
  });

  const patchMutation = useMutation({
    mutationFn: async () => {
      if (!editingModule) return null;
      setEditErrorMsg(null);
      if (editStartDate && editTargetDate && editTargetDate < editStartDate) {
        throw new Error('Target date cannot be earlier than start date.');
      }
      return await apiFetch('PATCH', '/api/v1/modules/{module_id}' as never, {
        params: { module_id: editingModule.id },
        body: {
          name: editName.trim(),
          status: editStatus,
          start_date: editStartDate || null,
          target_date: editTargetDate || null,
          description_markdown: editDesc.trim() || null,
        },
      });
    },
    onSuccess: (updated: unknown) => {
      if (updated && typeof updated === 'object' && 'id' in updated) {
        queryClient.setQueryData<ProjectModuleItem[]>(['projects', key, 'modules'], (old = []) =>
          old.map((m) => (m.id === (updated as ProjectModuleItem).id ? (updated as ProjectModuleItem) : m))
        );
      }
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'modules'] });
      setEditingModule(null);
    },
    onError: (err: unknown) => {
      setEditErrorMsg(formatDateOrderError(err instanceof Error ? err.message : 'Failed to update module'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (moduleId: string) => {
      return await apiFetch('DELETE', '/api/v1/modules/{module_id}' as never, {
        params: { module_id: moduleId },
      });
    },
    onSuccess: (_data, moduleId) => {
      queryClient.setQueryData<ProjectModuleItem[]>(['projects', key, 'modules'], (old = []) =>
        old.filter((m) => m.id !== moduleId)
      );
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'modules'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete module');
    },
  });

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate();
  };

  const handleEditSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!editName.trim()) return;
    patchMutation.mutate();
  };

  const openEditModal = (mod: ProjectModuleItem) => {
    setEditingModule(mod);
    setEditName(mod.name);
    setEditStatus(mod.status ?? 'planned');
    setEditStartDate(mod.start_date ?? '');
    setEditTargetDate(mod.target_date ?? '');
    setEditDesc(mod.description_markdown ?? '');
    setEditErrorMsg(null);
  };

  return (
    <section data-testid="project-modules-view" className="kb-workspace-section">
      <div className="kb-workspace-section-header">
        <h1>Modules ({key})</h1>
        <p>Feature modules and sub-project groupings for {key}.</p>
      </div>

      {canCreate && (
        <form onSubmit={handleSubmit} className="kb-modules-create-form" data-testid="create-module-form">
          <h3>Create New Module</h3>
          {errorMsg && (
            <div className="kb-modules-error" role="alert" data-testid="module-error-banner">
              {errorMsg}
            </div>
          )}
          <div className="kb-form-row">
            <label className="kb-form-field">
              <span className="kb-form-label">Module Name</span>
              <input
                type="text"
                className="kb-form-input"
                data-testid="new-module-name-input"
                placeholder="Module name..."
                value={newName}
                onChange={(e) => { setNewName(e.target.value); }}
                required
              />
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">Status</span>
              <select
                className="kb-form-input"
                data-testid="new-module-status-select"
                value={status}
                onChange={(e) => { setStatus(e.target.value); }}
              >
                <option value="planned">Planned</option>
                <option value="backlog">Backlog</option>
                <option value="in_progress">In Progress</option>
                <option value="paused">Paused</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">Start Date</span>
              <input
                type="date"
                className="kb-form-input"
                data-testid="new-module-start-input"
                value={startDate}
                onChange={(e) => { setStartDate(e.target.value); }}
                title="Start date"
              />
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">Target Date</span>
              <input
                type="date"
                className="kb-form-input"
                data-testid="new-module-target-input"
                value={targetDate}
                onChange={(e) => { setTargetDate(e.target.value); }}
                title="Target date"
              />
            </label>
            <label className="kb-form-field">
              <span className="kb-form-label">Description</span>
              <input
                type="text"
                className="kb-form-input"
                data-testid="new-module-desc-input"
                placeholder="Description (optional)..."
                value={description}
                onChange={(e) => { setDescription(e.target.value); }}
              />
            </label>
            <button
              type="submit"
              className="kb-btn-primary"
              data-testid="create-module-btn"
              disabled={createMutation.isPending || !newName.trim()}
            >
              {createMutation.isPending ? 'Creating...' : '+ Create Module'}
            </button>
          </div>
        </form>
      )}

      {/* Edit Module Modal */}
      {editingModule && (
        <div className="kb-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="edit-module-modal-title">
          <div className="kb-modal" data-testid="edit-module-modal">
            <h3 id="edit-module-modal-title">Edit Module</h3>
            {editErrorMsg && (
              <div className="kb-modules-error" role="alert" data-testid="edit-module-error">
                {editErrorMsg}
              </div>
            )}
            <form onSubmit={handleEditSubmit}>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Module Name</span>
                <input
                  type="text"
                  className="kb-form-input"
                  data-testid="edit-module-name-input"
                  value={editName}
                  onChange={(e) => { setEditName(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Status</span>
                <select
                  className="kb-form-input"
                  data-testid="edit-module-status-select"
                  value={editStatus}
                  onChange={(e) => { setEditStatus(e.target.value); }}
                >
                  <option value="planned">Planned</option>
                  <option value="backlog">Backlog</option>
                  <option value="in_progress">In Progress</option>
                  <option value="paused">Paused</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Start Date</span>
                <input
                  type="date"
                  className="kb-form-input"
                  data-testid="edit-module-start-input"
                  value={editStartDate}
                  onChange={(e) => { setEditStartDate(e.target.value); }}
                />
              </div>
              <div className="kb-form-field" style={{ marginBottom: 12 }}>
                <span className="kb-form-label">Target Date</span>
                <input
                  type="date"
                  className="kb-form-input"
                  data-testid="edit-module-target-input"
                  value={editTargetDate}
                  onChange={(e) => { setEditTargetDate(e.target.value); }}
                />
              </div>
              <div className="kb-form-field" style={{ marginBottom: 16 }}>
                <span className="kb-form-label">Description</span>
                <input
                  type="text"
                  className="kb-form-input"
                  data-testid="edit-module-desc-input"
                  value={editDesc}
                  onChange={(e) => { setEditDesc(e.target.value); }}
                />
              </div>
              <div className="kb-modal-footer">
                <button
                  type="button"
                  className="kb-btn-secondary"
                  data-testid="cancel-edit-module-btn"
                  onClick={() => { setEditingModule(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-btn-primary"
                  data-testid="save-edit-module-btn"
                  disabled={patchMutation.isPending || !editName.trim()}
                >
                  {patchMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="kb-modules-list-wrapper">
        {isLoading && <p>Loading modules...</p>}
        {!isLoading && modules.length === 0 && (
          <p className="kb-empty-text">No modules defined yet. Create your first module above.</p>
        )}
        <ul className="kb-modules-list" data-testid="modules-list">
          {modules.map((mod) => {
            const statusKey = mod.status?.toLowerCase().replace(/_/g, '-') ?? 'planned';
            return (
              <li key={mod.id} className="kb-module-item" data-testid={`module-item-${mod.id}`}>
                <div className="kb-module-info">
                  <strong>{mod.name}</strong>
                  <span
                    className={`kb-status-pill kb-status-pill--${statusKey}`}
                    data-testid={`module-status-${mod.id}`}
                  >
                    {formatStatusLabel(mod.status)}
                  </span>
                  <span
                    className="kb-module-dates"
                    data-testid={`module-dates-${mod.id}`}
                    aria-label={`Start: ${mod.start_date ?? 'TBD'}, Target: ${mod.target_date ?? 'TBD'}`}
                  >
                    {mod.start_date ?? 'TBD'} → {mod.target_date ?? 'TBD'}
                  </span>
                  {mod.description_markdown && (
                    <p className="kb-module-desc">{mod.description_markdown}</p>
                  )}
                </div>
                <div className="kb-module-actions">
                  <Link to={`/projects/${key}/issues?module=${mod.id}`} style={{ marginRight: 8, fontSize: 13 }}>
                    View module work items &rarr;
                  </Link>
                  {canCreate && (
                    <button
                      type="button"
                      className="kb-btn-secondary"
                      data-testid={`edit-module-btn-${mod.id}`}
                      onClick={() => { openEditModal(mod); }}
                    >
                      Edit
                    </button>
                  )}
                  {canDelete && (
                    <button
                      type="button"
                      className="kb-btn-danger"
                      data-testid={`delete-module-btn-${mod.id}`}
                      onClick={() => { deleteMutation.mutate(mod.id); }}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

export function ProjectModulesView({
  capabilities,
}: {
  capabilities?: string[] | undefined;
} = {}): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const ctx = useContext(ProjectRouteContext);
  const key = projectKey ?? (ctx.projectKey || 'KAN');
  const client = useContext(QueryClientContext);
  if (!client) {
    return (
      <section data-testid="project-modules-view" className="kb-workspace-section">
        <h1>Modules ({key})</h1>
        <p>Feature modules and sub-project groupings for {key}.</p>
        <Link to={`/projects/${key}/issues`}>View module work items →</Link>
      </section>
    );
  }
  return (
    <ProjectModulesViewInner
      projectKey={key}
      capabilities={capabilities ?? (ctx.projectKey ? ctx.capabilities : undefined)}
    />
  );
}

export function ProjectViewsRedirect(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
  return <Navigate to={`/projects/${key}/issues`} replace />;
}

export function IssueKeyRedirectRoute(): JSX.Element {
  const { issueKey } = useParams<{ issueKey: string }>();
  const navigate = useNavigate();

  const resolveQuery = useQuery({
    queryKey: ['resolve', 'issue', issueKey ?? ''],
    queryFn: async ({ signal }) => {
      const res = await fetch(
        `/api/v1/resolve?kind=issue&ref=${encodeURIComponent(issueKey ?? '')}`,
        {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
          signal,
        },
      );
      if (!res.ok) {
        return { isNotFound: true };
      }
      return (await res.json()) as { canonical_key?: string; key?: string; isNotFound?: boolean };
    },
    enabled: Boolean(issueKey),
  });

  useEffect(() => {
    if (resolveQuery.data && !resolveQuery.data.isNotFound) {
      const canonicalKey = resolveQuery.data.canonical_key ?? resolveQuery.data.key;
      if (canonicalKey) {
        const projKey = canonicalKey.includes('-')
          ? canonicalKey.slice(0, canonicalKey.lastIndexOf('-'))
          : canonicalKey;
        void navigate(`/projects/${projKey}/issues/${canonicalKey}`, { replace: true });
      }
    }
  }, [resolveQuery.data, navigate]);

  if (!issueKey || resolveQuery.isError || resolveQuery.data?.isNotFound) {
    return <NotFoundView />;
  }

  return (
    <div data-testid="issue-key-resolving" style={{ padding: '2rem', textAlign: 'center' }}>
      Resolving issue {issueKey}...
    </div>
  );
}

export { ProjectSavedViewsView };

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
  if (loc.pathname === '/__dev/icons') return <IconStory />;
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
        if (res.status === 404 || res.status === 403) {
          return { isNotFound: true };
        }
        return null;
      }
      return (await res.json()) as {
        id?: string;
        identifier?: string;
        name?: string;
        modules_enabled?: boolean;
        access_manifest?: AccessManifestData;
        capabilities?: string[];
        is_project_admin?: boolean;
        isNotFound?: boolean;
      };
    },
    enabled: isValidProject && isValidIssue,
    staleTime: 60000,
  });

  if (!isValidProject || !isValidIssue) {
    return <NotFoundView />;
  }

  const projectData = projectQuery.data;

  if (projectData?.isNotFound) {
    return <NotFoundView />;
  }

  const modulesEnabled = projectData?.modules_enabled ?? true;
  const projectName = projectData?.name ?? 'kanban';
  const resolvedKey = projectData?.identifier ?? projectKey ?? '';
  const capabilities = projectData?.capabilities ?? (projectData === null || projectData === undefined ? ['EDIT', 'ADMIN'] : []);
  const isProjectAdmin = projectData?.is_project_admin ?? capabilities.includes('ADMIN');

  return (
    <ProjectRouteContext.Provider
      value={{
        projectKey: resolvedKey,
        projectName,
        modulesEnabled,
        capabilities,
        isProjectAdmin,
      }}
    >
      <AppShell
        projectKey={resolvedKey}
        projectId={projectData?.id}
        projectName={projectName}
        modulesEnabled={modulesEnabled}
        accessManifest={projectData?.access_manifest}
      />
    </ProjectRouteContext.Provider>
  );
}

export function AdminRouteGuard({ children }: { children?: React.ReactNode } = {}): JSX.Element {
  const { data: user, isLoading } = useQuery<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    workspace_role?: string;
    aal_level?: number | string;
    auth_aal?: string;
  } | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as {
          is_server_admin?: boolean;
          is_workspace_admin?: boolean;
          workspace_role?: string;
          aal_level?: number | string;
          auth_aal?: string;
        };
      } catch {
        return null;
      }
    },
    staleTime: 60000,
  });

  if (isLoading) {
    return <div data-testid="admin-guard-loading" className="kb-loading-state" />;
  }

  const isServerAdmin = Boolean(user?.is_server_admin);
  const isWorkspaceAdmin =
    Boolean(user?.is_workspace_admin) || user?.workspace_role === 'WORKSPACE_ADMIN';
  const aal = user?.aal_level;
  const isAal2 = aal === 2 || aal === '2' || aal === 'aal2' || user?.auth_aal === 'aal2';

  if ((!isServerAdmin && !isWorkspaceAdmin) || !isAal2) {
    return <NotFoundView />;
  }

  return <>{children ?? <Outlet />}</>;
}

export function DraftsWorkspaceRouteGuard(): JSX.Element {
  const { data: user, isLoading } = useQuery<{
    workspace_role?: string;
  } | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as {
          workspace_role?: string;
        };
      } catch {
        return null;
      }
    },
    staleTime: 60000,
  });

  if (isLoading) {
    return <div data-testid="drafts-guard-loading" className="kb-loading-state" />;
  }

  const isViewer = user?.workspace_role === 'VIEWER' || user?.workspace_role === 'WORKSPACE_GUEST';
  if (isViewer) {
    return <NotFoundView />;
  }

  return <DraftsWorkspaceView />;
}

export function RootShellLayout(): JSX.Element {
  return <AppShell projectKey={undefined} projectId={undefined} />;
}

export function ProjectMcpRedirect(): JSX.Element {
  const { projectKey } = useParams<{ projectKey?: string }>();
  const [searchParams] = useSearchParams();
  const nextParams = new URLSearchParams(searchParams);
  if (!nextParams.has('scope')) {
    nextParams.set('scope', 'project');
  }
  if (projectKey && !nextParams.has('project')) {
    nextParams.set('project', projectKey);
  }
  return <Navigate to={`/settings/mcp?${nextParams.toString()}`} replace />;
}

export function WorkspaceMcpRedirect(): JSX.Element {
  const [searchParams] = useSearchParams();
  const nextParams = new URLSearchParams(searchParams);
  if (!nextParams.has('scope')) {
    nextParams.set('scope', 'workspace');
  }
  return <Navigate to={`/settings/mcp?${nextParams.toString()}`} replace />;
}

export function AdminMcpRedirect(): JSX.Element {
  const [searchParams] = useSearchParams();
  const nextParams = new URLSearchParams(searchParams);
  if (!nextParams.has('scope')) {
    nextParams.set('scope', 'server');
  }
  return <Navigate to={`/settings/mcp?${nextParams.toString()}`} replace />;
}

const projectRouteChildren: RouteObject[] = [
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
    path: 'analytics',
    element: <FlowAnalyticsPage />,
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
    path: 'stickies',
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
    element: <ProjectMcpRedirect />,
  },
  {
    path: 'settings/custom-fields',
    element: <ProjectCustomFieldsSettingsRoute />,
  },
  {
    path: 'settings/workflows',
    element: <WorkflowStudioPage />,
  },
  {
    path: 'settings',
    element: <ProjectSettingsPage />,
  },
];

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        path: 'projects/:projectKey',
        element: <ProjectRouteContainer />,
        children: projectRouteChildren,
      },
      {
        path: 'w/:workspaceSlug/p/:projectKey',
        element: <ProjectRouteContainer />,
        children: projectRouteChildren,
      },
      {
        path: 'issues/:issueKey',
        element: <IssueKeyRedirectRoute />,
      },
      {
        path: 'activate',
        element: <DeviceActivatePage />,
      },
      {
        path: 'oauth/device',
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
        path: 'docs',
        element: <DocsCenterPage />,
      },
      {
        path: 'docs/:slug',
        element: <DocsCenterPage />,
      },
      {
        path: 'help',
        element: <DocsCenterPage />,
      },
      {
        path: 'help/:slug',
        element: <DocsCenterPage />,
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
            element: <DraftsWorkspaceRouteGuard />,
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
            path: 'settings/profile',
            element: <PersonalSettingsPage />,
          },
          {
            path: 'about',
            element: <AboutPage />,
          },
          {
            path: 'settings/about',
            element: <Navigate to="/about" replace />,
          },
          {
            path: 'settings/mcp',
            element: <McpAccessStudio />,
          },
          {
            path: 'settings/mcp-keys',
            element: <Navigate to="/settings/mcp" replace />,
          },
          {
            path: 'workspaces/settings',
            element: <WorkspaceSettingsPage />,
          },
          {
            path: 'workspaces/settings/mcp',
            element: <WorkspaceMcpRedirect />,
          },
          {
            path: 'workspaces/settings/ai',
            element: <AiStudioPage />,
          },
          {
            path: 'admin',
            element: <AdminRouteGuard />,
            children: [
              {
                path: 'link-auditor',
                element: <AdminDiagnosticsStudio defaultTab="links" />,
              },
              {
                path: 'diagnostics',
                element: <AdminDiagnosticsStudio defaultTab="health" />,
              },
              {
                path: 'mcp',
                element: <AdminMcpRedirect />,
              },
              {
                path: 'mcp-keys',
                element: <AdminMcpRedirect />,
              },
              {
                path: 'oauth',
                element: <OAuthClientGovernanceStudio />,
              },
              {
                path: 'oauth-clients',
                element: <Navigate to="/admin/oauth" replace />,
              },
              {
                path: 'imports',
                element: <PlaneImportStudio />,
              },
              {
                path: 'auth',
                element: <AuthStudioPage />,
              },
              {
                path: 'ai',
                element: <AiStudioPage />,
              },
              {
                path: 'agents',
                element: <AgentStudioPage />,
              },
              {
                path: 'agent-runners',
                element: <RunnerStudioPage />,
              },
              {
                path: 'standalone',
                element: <StandaloneStatusRoute />,
              },
              {
                path: '*',
                element: <NotFoundView />,
              },
            ],
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
