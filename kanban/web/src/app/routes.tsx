/**
 * Application Routes & Router Table (KB-P3-34, S6.3, KB-P3-41, KANBA-170, KANBA-166, KANBA-167).
 * react-router v7 data router with layout parameter normalization, regex key validation, S3.4 uniform error view,
 * zero-remount ticket drawer & full-screen surface routing, WorkspaceHomeView, and StandaloneStatusPanel route.
 */

import React, {
  createContext,
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
import { LoginPage } from '../features/auth/LoginPage';
import { SetupClaimPage } from '../features/auth/SetupClaimPage';
import { AuthStudioPage } from '../features/admin-auth/AuthStudioPage';
import { DeviceActivatePage } from '../features/oauth/DeviceActivatePage';
import { McpAccessStudio } from '../features/settings/McpAccessStudio';
import { PersonalSettingsPage } from '../features/settings/PersonalSettingsPage';
import { WorkflowStudioPage } from '../features/workflows/WorkflowStudioPage';
import { StandaloneStatusPanel } from '../features/standalone/StandaloneStatusPanel';
import { CreateProjectModal, type CreatedProject } from '../features/projects/CreateProjectModal';
import { useSessionGuard } from '../features/auth/useSessionGuard';
import { useDrafts, deleteDraft, type IssueDraft } from '../features/drafts/draftsStore';

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
  const drafts = useDrafts();
  const navigate = useNavigate();

  const handlePublishOrResume = async (draft: IssueDraft): Promise<void> => {
    try {
      const payload: Record<string, unknown> = {
        summary: draft.summary,
      };
      if (draft.description) {
        payload.description_markdown = draft.description;
      }
      if (draft.stateId) {
        payload.state_id = draft.stateId;
      }
      if (draft.prioritySlug) {
        payload.priority_slug = draft.prioritySlug;
      }
      if (draft.moduleIds && draft.moduleIds.length > 0) {
        payload.module_ids = draft.moduleIds;
      }

      const res = await fetch(`/api/v1/projects/${draft.projectKey}/issues`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        deleteDraft(draft.id);
        void navigate(`/projects/${draft.projectKey}/issues`);
        return;
      }
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
          <Link to="/projects/KAN/issues?create=1">Create a new work item →</Link>
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

export function YourWorkView(): JSX.Element {
  return (
    <section data-testid="your-work-view" className="kb-workspace-section">
      <h1>Your work</h1>
      <p>Assigned and subscribed work items across your workspace projects.</p>
      <Link to="/projects/KAN/issues">View project work items →</Link>
    </section>
  );
}

export interface ProjectCycleItem {
  id: string;
  name: string;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
}

function ProjectCyclesViewInner({ projectKey }: { projectKey: string }): JSX.Element {
  const key = projectKey;
  const queryClient = useQueryClient();

  const [newName, setNewName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
      return await apiFetch('POST', '/api/v1/projects/{project_ref}/cycles' as never, {
        params: { project_ref: key },
        body: {
          name: newName.trim(),
          ...(startDate ? { start_date: startDate } : {}),
          ...(endDate ? { end_date: endDate } : {}),
        },
      });
    },
    onSuccess: () => {
      setNewName('');
      setStartDate('');
      setEndDate('');
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'cycles'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create cycle');
    },
  });

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate();
  };

  return (
    <section data-testid="project-cycles-view" className="kb-workspace-section">
      <div className="kb-workspace-section-header">
        <h1>Cycles ({key})</h1>
        <p>Time-boxed sprint cycles for grouping and tracking project velocity.</p>
      </div>

      <form onSubmit={handleSubmit} className="kb-cycles-create-form" data-testid="create-cycle-form">
        <h3>Create New Cycle</h3>
        {errorMsg && (
          <div className="kb-cycles-error" role="alert" data-testid="cycle-error-banner">
            {errorMsg}
          </div>
        )}
        <div className="kb-form-row">
          <input
            type="text"
            className="kb-form-input"
            data-testid="new-cycle-name-input"
            placeholder="Sprint / Cycle name..."
            value={newName}
            onChange={(e) => { setNewName(e.target.value); }}
            required
          />
          <input
            type="date"
            className="kb-form-input"
            data-testid="new-cycle-start-input"
            value={startDate}
            onChange={(e) => { setStartDate(e.target.value); }}
            title="Start date"
          />
          <input
            type="date"
            className="kb-form-input"
            data-testid="new-cycle-end-input"
            value={endDate}
            onChange={(e) => { setEndDate(e.target.value); }}
            title="End date"
          />
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

      <div className="kb-cycles-list-wrapper">
        {isLoading && <p>Loading cycles...</p>}
        {!isLoading && cycles.length === 0 && (
          <p className="kb-empty-text">No cycles defined yet. Create your first sprint cycle above.</p>
        )}
        <ul className="kb-cycles-list" data-testid="cycles-list">
          {cycles.map((cyc) => (
            <li key={cyc.id} className="kb-cycle-item" data-testid={`cycle-item-${cyc.id}`}>
              <div className="kb-cycle-info">
                <strong>{cyc.name}</strong>
                {cyc.status && <span className="kb-cycle-status-badge">{cyc.status}</span>}
                {Boolean(cyc.start_date ?? cyc.end_date) && (
                  <span className="kb-cycle-dates">
                    {cyc.start_date ?? 'TBD'} → {cyc.end_date ?? 'TBD'}
                  </span>
                )}
              </div>
              <Link to={`/projects/${key}/issues?cycle=${cyc.id}`}>Filter work items →</Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function ProjectCyclesView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
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
  return <ProjectCyclesViewInner projectKey={key} />;
}

export interface ProjectModuleItem {
  id: string;
  name: string;
  status?: string;
  description_markdown?: string;
}

function ProjectModulesViewInner({ projectKey }: { projectKey: string }): JSX.Element {
  const key = projectKey;
  const queryClient = useQueryClient();

  const [newName, setNewName] = useState('');
  const [description, setDescription] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
      return await apiFetch('POST', '/api/v1/projects/{project_ref}/modules' as never, {
        params: { project_ref: key },
        body: {
          name: newName.trim(),
          ...(description.trim() ? { description_markdown: description.trim() } : {}),
        },
      });
    },
    onSuccess: () => {
      setNewName('');
      setDescription('');
      void queryClient.invalidateQueries({ queryKey: ['projects', key, 'modules'] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create module');
    },
  });

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    createMutation.mutate();
  };

  return (
    <section data-testid="project-modules-view" className="kb-workspace-section">
      <div className="kb-workspace-section-header">
        <h1>Modules ({key})</h1>
        <p>Feature modules and sub-project groupings for {key}.</p>
      </div>

      <form onSubmit={handleSubmit} className="kb-modules-create-form" data-testid="create-module-form">
        <h3>Create New Module</h3>
        {errorMsg && (
          <div className="kb-modules-error" role="alert" data-testid="module-error-banner">
            {errorMsg}
          </div>
        )}
        <div className="kb-form-row">
          <input
            type="text"
            className="kb-form-input"
            data-testid="new-module-name-input"
            placeholder="Module name..."
            value={newName}
            onChange={(e) => { setNewName(e.target.value); }}
            required
          />
          <input
            type="text"
            className="kb-form-input"
            data-testid="new-module-desc-input"
            placeholder="Description (optional)..."
            value={description}
            onChange={(e) => { setDescription(e.target.value); }}
          />
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

      <div className="kb-modules-list-wrapper">
        {isLoading && <p>Loading modules...</p>}
        {!isLoading && modules.length === 0 && (
          <p className="kb-empty-text">No modules defined yet. Create your first module above.</p>
        )}
        <ul className="kb-modules-list" data-testid="modules-list">
          {modules.map((mod) => (
            <li key={mod.id} className="kb-module-item" data-testid={`module-item-${mod.id}`}>
              <div className="kb-module-info">
                <strong>{mod.name}</strong>
                {mod.status && <span className="kb-module-status-badge">{mod.status}</span>}
                {mod.description_markdown && (
                  <p className="kb-module-desc">{mod.description_markdown}</p>
                )}
              </div>
              <Link to={`/projects/${key}/issues?module=${mod.id}`}>View module work items →</Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function ProjectModulesView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
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
  return <ProjectModulesViewInner projectKey={key} />;
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
        return null;
      }
      return (await res.json()) as {
        id?: string;
        name?: string;
        modules_enabled?: boolean;
        access_manifest?: AccessManifestData;
      };
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
        projectId={projectQuery.data?.id}
        projectName={projectName}
        modulesEnabled={modulesEnabled}
        accessManifest={projectQuery.data?.access_manifest}
      />
    </ProjectRouteContext.Provider>
  );
}

export function RootShellLayout(): JSX.Element {
  return <AppShell projectKey={undefined} projectId={undefined} />;
}

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    errorElement: <RouteErrorBoundary />,
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
          {
            path: 'settings/workflows',
            element: <WorkflowStudioPage />,
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
            path: 'settings/profile',
            element: <PersonalSettingsPage />,
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
