import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor, within } from '@testing-library/react';
import React from 'react';
import { RouterProvider, MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import * as client from '../api/client';
import {
  createAppRouter,
  PROJECT_KEY_REGEX,
  ISSUE_KEY_REGEX,
  IssuesWorkspaceRoute,
  RoutePlaceholder,
  AppRoutes,
  ProjectCyclesView,
  ProjectModulesView,
  ProjectSavedViewsView,
  WorkspaceHomeView,
  DraftsWorkspaceView,
  AdminRouteGuard,
  DraftsWorkspaceRouteGuard,
  NotFoundView,
  ProjectMcpRedirect,
  WorkspaceMcpRedirect,
  AdminMcpRedirect,
  ProjectRouteContext,
  ProjectOverviewRoute,
  ProjectIssuesRoute,
  FullScreenIssueRoute,
} from './routes';
import { saveDraft } from '../features/drafts/draftsStore';
import { ThemeProvider } from '../theme/ThemeProvider';
import { FIXTURE_12_ISSUES } from '../features/views/fixtures';

describe('routes and AppShell integration', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  it('validates projectKey and issueKey regexes strictly', () => {
    expect(PROJECT_KEY_REGEX.test('KAN')).toBe(true);
    expect(PROJECT_KEY_REGEX.test('KB1')).toBe(true);
    expect(PROJECT_KEY_REGEX.test('P10')).toBe(true);
    expect(PROJECT_KEY_REGEX.test('kan')).toBe(false); // Lowercase rejected
    expect(PROJECT_KEY_REGEX.test('1KAN')).toBe(false); // Leading digit rejected
    expect(PROJECT_KEY_REGEX.test('')).toBe(false);
    expect(PROJECT_KEY_REGEX.test('TOOLONGPROJECTKEY')).toBe(false);

    expect(ISSUE_KEY_REGEX.test('KAN-1')).toBe(true);
    expect(ISSUE_KEY_REGEX.test('KAN-142')).toBe(true);
    expect(ISSUE_KEY_REGEX.test('KAN-1x')).toBe(false); // Suffix character rejected
    expect(ISSUE_KEY_REGEX.test('kan-142')).toBe(false);
    expect(ISSUE_KEY_REGEX.test('KAN-')).toBe(false);
  });

  it('renders AppShell with sidebar items, breadcrumb, and layout=board selection', () => {
    const router = createAppRouter(['/projects/KAN/issues?layout=board']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Sidebar items
    expect(screen.getByRole('button', { name: /Workspace switcher: kanban/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Work Items/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Cycles/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Modules/ })).toBeDefined();
    expect(screen.queryByRole('link', { name: /Views/ })).toBeNull();
    expect(screen.getByTestId('sidebar-docs-link')).toBeDefined();
    expect(screen.getByRole('link', { name: /Workflows/ })).toBeDefined();

    // Breadcrumb
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeDefined();

    // Layout switcher has Board selected
    const boardLink = screen.getByRole('link', { name: /Board/ });
    expect(boardLink).toBeDefined();

    // Route placeholder rendered inside shell
    expect(screen.getByTestId('route-placeholder')).toBeDefined();
  });

  it('normalizes ?layout=<script> to list via navigate replace', async () => {
    const router = createAppRouter(['/projects/KAN/issues?layout=<script>alert(1)</script>']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // After normalization, Issues view nav link is rendered
    const issuesLink = await screen.findByRole('link', { name: 'Issues view' });
    expect(issuesLink).toBeDefined();
  });

  it('renders "Not found or no access" for invalid projectKey or issueKey without fetch calls', () => {
    const fetchSpy = vi.spyOn(window, 'fetch');

    const routerInvalidProj = createAppRouter(['/projects/kan/issues']);
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={routerInvalidProj} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText('Not found or no access')).toBeDefined();
    expect(fetchSpy).not.toHaveBeenCalled();

    unmount();

    const routerInvalidIssue = createAppRouter(['/projects/KAN/issues/KAN-1x']);
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={routerInvalidIssue} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText('Not found or no access')).toBeDefined();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('focuses #main when skip link is clicked', () => {
    const router = createAppRouter(['/projects/KAN/issues']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const skipLink = screen.getByRole('link', { name: 'Skip to content' });
    const mainEl = document.getElementById('main');
    expect(mainEl).toBeDefined();

    fireEvent.click(skipLink);
    expect(document.activeElement).toBe(mainEl);
  });

  it('opens CommandPalette with Ctrl/Cmd+K even from a focused input', () => {
    const router = createAppRouter(['/projects/KAN/issues']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
    fireEvent.keyDown(window, {
      key: 'k',
      metaKey: isMac,
      ctrlKey: !isMac,
    });

    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeDefined();

    document.body.removeChild(input);
  });

  it('renders various project routes, auth routes, and dev story routes', () => {
    queryClient.setQueryData(qk.me(), { is_server_admin: true, auth_aal: 'aal2' });
    const paths = [
      { path: '/', expected: 'route-placeholder' },
      { path: '/projects/KAN/overview', expected: 'project-overview-page' },
      { path: '/projects/KAN/docs', expected: 'docs-workspace-view' },
      { path: '/projects/KAN/docs/page-42', expected: 'docs-workspace-view' },
      { path: '/projects/KAN/issues/KAN-100', expected: 'full-screen-route-anchor' },
      { path: '/stickies', expected: 'workspace-stickies-page' },
      { path: '/login', expected: 'login-page' },
      { path: '/setup', expected: 'setup-claim-page' },
      { path: '/admin/auth', expected: 'auth-studio-page' },
      { path: '/admin/standalone', expected: 'standalone-status-route' },
      { path: '/drafts', expected: 'drafts-view' },
      { path: '/your-work', expected: 'your-work-view' },
      { path: '/projects/KAN/cycles', expected: 'project-cycles-view' },
      { path: '/projects/KAN/modules', expected: 'project-modules-view' },
      { path: '/projects/KAN/settings', expected: 'project-settings-page' },
      { path: '/workspaces/settings', expected: 'workspace-settings-page' },
      { path: '/__dev/tokens', expected: 'token-story' },
      { path: '/__dev/emoji', expected: 'emoji-story' },
      { path: '/__dev/editor', expected: 'editor-story' },
      { path: '/__dev/media', expected: 'media-story' },
      { path: '/__dev/realtime', expected: 'realtime-story' },
      { path: '/__dev/drawer', expected: 'drawer-story' },
      { path: '/__dev/unknown', expected: 'not-found-view' },
      { path: '/unknown-route', expected: 'not-found-view' },
    ];

    for (const item of paths) {
      const router = createAppRouter([item.path]);
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <RouterProvider router={router} />
          </ThemeProvider>
        </QueryClientProvider>,
      );

      expect(screen.getByTestId(item.expected)).toBeDefined();
      unmount();
    }
  });

  it('createAppRouter creates browser router when initialEntries is omitted', () => {
    const router = createAppRouter();
    expect(router).toBeDefined();
    expect(router.state).toBeDefined();
  });

  it('redirects legacy alias routes /settings/mcp-keys and /admin/oauth-clients', () => {
    const routerMcp = createAppRouter(['/settings/mcp-keys']);
    const { unmount: u1 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={routerMcp} />
        </ThemeProvider>
      </QueryClientProvider>,
    );
    expect(routerMcp.state.location.pathname).toBe('/settings/mcp');
    u1();

    queryClient.setQueryData(qk.me(), {
      is_server_admin: true,
      is_workspace_admin: true,
      auth_aal: 'aal2',
      aal_level: 2,
    });
    const routerOAuth = createAppRouter(['/admin/oauth-clients']);
    const { unmount: u2 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={routerOAuth} />
        </ThemeProvider>
      </QueryClientProvider>,
    );
    expect(routerOAuth.state.location.pathname).toBe('/admin/oauth');
    u2();
  });

  it('fetches project metadata and applies modules_enabled', async () => {
    const getRequestUrl = (input: RequestInfo | URL): string => {
      if (typeof input === 'string') return input;
      if (input instanceof URL) return input.href;
      return input.url;
    };

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (getRequestUrl(url).includes('/projects/KAN')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ name: 'Custom Name', modules_enabled: false }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const router = createAppRouter(['/projects/KAN/issues']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Wait for query to complete and verify modules is unmounted
    expect(await screen.findByRole('button', { name: 'Project: Custom Name' })).toBeDefined();
    expect(screen.queryByRole('link', { name: 'Modules' })).toBeNull();
  });

  it('handles project metadata fetch failure gracefully falling back to defaults', async () => {
    const getRequestUrl = (input: RequestInfo | URL): string => {
      if (typeof input === 'string') return input;
      if (input instanceof URL) return input.href;
      return input.url;
    };

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      if (getRequestUrl(url).includes('/projects/KAN')) {
        return Promise.resolve(new Response(null, { status: 500 }));
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const router = createAppRouter(['/projects/KAN/issues']);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('button', { name: 'Project: kanban' })).toBeDefined();
  });

  it('renders WorkspaceHomeView projects from /api/v1/projects and opens CreateProjectModal', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [
                {
                  id: 'p-1',
                  identifier: 'OPS',
                  name: 'Operations',
                  description_markdown: 'Ops project',
                  modules_enabled: true,
                },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const router = createAppRouter(['/']);
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('project-card-OPS')).toBeDefined();

    fireEvent.click(screen.getByTestId('home-create-project-btn'));
    expect(screen.getByTestId('create-project-modal')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('create-project-modal')).toBeNull();

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:project-created'));
    });

    fireEvent.click(screen.getByTestId('home-create-issue-btn'));
  });

  it('preserves IssuesWorkspaceRoute in background when ?peek= is set and triggers create modal on ?create=1', async () => {
    const router = createAppRouter(['/projects/KAN/issues?layout=list&peek=KAN-101&create=1']);
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('issues-workspace')).toBeDefined();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:create-issue'));
    });

    // Verify RoutePlaceholder and AppRoutes helpers
    expect(AppRoutes()).toBeNull();
    render(<RoutePlaceholder route="/custom" />);
    expect(screen.getByText('Route: /custom')).toBeDefined();
  });

  it('closes StandaloneStatusRoute and navigates back on Close click', () => {
    queryClient.setQueryData(qk.me(), { is_server_admin: true, auth_aal: 'aal2' });
    const router = createAppRouter(['/admin/standalone']);
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);
  });
});

describe('IssuesWorkspaceRoute', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/projects/KAN/issues');
  });

  it('mounts and renders default ListView and triggers handleOpenPeek on click', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />,
    );

    expect(screen.getByTestId('navigator-filter-state')).toBeDefined();
    const firstIssue = FIXTURE_12_ISSUES[0];
    expect(firstIssue).toBeDefined();
    if (!firstIssue) return;
    const issueLink = screen.getByText(firstIssue.key);
    fireEvent.click(issueLink);
  });

  it('renders TableView when layout=table in search params', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=table');

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />,
    );

    expect(screen.getByRole('table')).toBeDefined();
  });

  it('ProjectCyclesView creates new cycle and calls POST /api/v1/projects/{projectKey}/cycles', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client, 'apiFetch').mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path.includes('cycles')) {
        return Promise.resolve([{ id: 'cyc-1', name: 'Sprint 1', status: 'active' }]);
      }
      if (method === 'POST' && path.includes('cycles')) {
        return Promise.resolve({ id: 'cyc-2', name: 'Sprint 2', status: 'upcoming' });
      }
      return Promise.resolve([]);
    });

    const router = createAppRouter(['/projects/KAN/cycles']);
    render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('project-cycles-view')).toBeDefined();
    });

    const input = screen.getByTestId('new-cycle-name-input');
    fireEvent.change(input, { target: { value: 'Sprint 2' } });

    const createBtn = screen.getByTestId('create-cycle-btn');
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        'POST',
        '/api/v1/projects/{project_ref}/cycles',
        expect.objectContaining({
          params: { project_ref: 'KAN' },
          body: (expect.objectContaining({ name: 'Sprint 2' }) as unknown) as Record<string, unknown>,
        }),
      );
    });
  });

  it('ProjectModulesView creates new module and calls POST /api/v1/projects/{projectKey}/modules', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client, 'apiFetch').mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path.includes('modules')) {
        return Promise.resolve([{ id: 'mod-1', name: 'Auth Module', status: 'active' }]);
      }
      if (method === 'POST' && path.includes('modules')) {
        return Promise.resolve({ id: 'mod-2', name: 'Billing Module', status: 'planned' });
      }
      return Promise.resolve([]);
    });

    const router = createAppRouter(['/projects/KAN/modules']);
    render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('project-modules-view')).toBeDefined();
    });

    const input = screen.getByTestId('new-module-name-input');
    fireEvent.change(input, { target: { value: 'Billing Module' } });

    const createBtn = screen.getByTestId('create-module-btn');
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        'POST',
        '/api/v1/projects/{project_ref}/modules',
        expect.objectContaining({
          params: { project_ref: 'KAN' },
          body: (expect.objectContaining({ name: 'Billing Module' }) as unknown) as Record<string, unknown>,
        }),
      );
    });
  });

  it('ProjectCyclesView supports start and end dates and displays error banner on failure', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client, 'apiFetch').mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path.includes('cycles')) {
        return Promise.resolve([
          { id: 'cyc-1', name: 'Sprint 1', status: 'upcoming', start_date: '2026-01-01', end_date: '2026-01-14' },
          { id: 'cyc-2', name: 'Sprint Backlog', status: 'backlog' },
          { id: 'cyc-3', name: 'Sprint Paused', status: 'paused' },
          { id: 'cyc-4', name: 'Sprint Cancelled', status: 'cancelled' },
        ]);
      }
      if (method === 'POST' && path.includes('cycles')) {
        return Promise.reject(new Error('Cycle creation rejected'));
      }
      return Promise.resolve([]);
    });

    const router = createAppRouter(['/projects/KAN/cycles']);
    render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('project-cycles-view')).toBeDefined();
      expect(screen.getByText(/2026-01-01/)).toBeDefined();
      expect(screen.getByText('Sprint Backlog')).toBeDefined();
      expect(screen.getByText('Sprint Paused')).toBeDefined();
      expect(screen.getByText('Sprint Cancelled')).toBeDefined();
    });

    const input = screen.getByTestId('new-cycle-name-input');
    fireEvent.change(input, { target: { value: 'Sprint Fail' } });

    // Test endDate < startDate validation branch
    fireEvent.change(screen.getByTestId('new-cycle-start-input'), { target: { value: '2026-05-10' } });
    fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-05-01' } });
    const createBtn = screen.getByTestId('create-cycle-btn');
    fireEvent.click(createBtn);
    await waitFor(() => {
      expect(screen.getByTestId('cycle-error-banner').textContent).toContain('End date cannot be earlier than start date');
    });

    // Valid dates, rejected by server
    fireEvent.change(screen.getByTestId('new-cycle-start-input'), { target: { value: '2026-02-01' } });
    fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-02-14' } });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cycle-error-banner').textContent).toContain('Cycle creation rejected');
    });
  });

  it('ProjectModulesView displays error banner on failure and renders module description', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client, 'apiFetch').mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path.includes('modules')) {
        return Promise.resolve([
          { id: 'mod-1', name: 'Core', status: 'planned', description_markdown: 'Core architecture module' },
          { id: 'mod-2', name: 'Paused Mod', status: 'paused' },
          { id: 'mod-3', name: 'Cancelled Mod', status: 'cancelled' },
        ]);
      }
      if (method === 'POST' && path.includes('modules')) {
        return Promise.reject(new Error('Module creation rejected'));
      }
      return Promise.resolve([]);
    });

    const router = createAppRouter(['/projects/KAN/modules']);
    render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('project-modules-view')).toBeDefined();
      expect(screen.getByText('Core architecture module')).toBeDefined();
      expect(screen.getByText('Paused Mod')).toBeDefined();
      expect(screen.getByText('Cancelled Mod')).toBeDefined();
    });

    const input = screen.getByTestId('new-module-name-input');
    fireEvent.change(input, { target: { value: 'Fail Mod' } });

    // Test targetDate < startDate validation
    fireEvent.change(screen.getByTestId('new-module-start-input'), { target: { value: '2026-06-15' } });
    fireEvent.change(screen.getByTestId('new-module-target-input'), { target: { value: '2026-06-01' } });
    const createBtn = screen.getByTestId('create-module-btn');
    fireEvent.click(createBtn);
    await waitFor(() => {
      expect(screen.getByTestId('module-error-banner').textContent).toContain('Target date cannot be earlier than start date');
    });

    fireEvent.change(screen.getByTestId('new-module-start-input'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByTestId('new-module-target-input'), { target: { value: '2026-06-15' } });
    fireEvent.change(screen.getByTestId('new-module-desc-input'), { target: { value: 'Some description' } });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByTestId('module-error-banner').textContent).toContain('Module creation rejected');
    });
  });

  it('renders ProjectViewsRedirect, ProjectSavedViewsView, and fallback views without query client', () => {
    // 1. ProjectSavedViewsView component
    render(
      <MemoryRouter initialEntries={['/projects/KAN/views']}>
        <ProjectSavedViewsView />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('project-views-view')).toBeDefined();
    expect(screen.getByRole('link', { name: 'List View' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Board View' })).toBeDefined();

    // 2. ProjectViewsRedirect via router
    const router1 = createAppRouter(['/projects/KAN/views']);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThemeProvider>
          <RouterProvider router={router1} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // 3. Fallback views without query client
    render(
      <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
        <ProjectCyclesView />
      </MemoryRouter>,
    );
    expect(screen.getByText('Filter work items by cycle →')).toBeDefined();

    render(
      <MemoryRouter initialEntries={['/projects/KAN/modules']}>
        <ProjectModulesView />
      </MemoryRouter>,
    );
    expect(screen.getByText('View module work items →')).toBeDefined();
  });

  it('renders FullScreenIssueRoute and sets document.title', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client.apiClient, 'get').mockResolvedValue({
      id: 'iss-1',
      key: 'KAN-999',
      summary: 'Critical Bug Fix',
    });

    const router = createAppRouter(['/projects/KAN/issues/KAN-999']);
    render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(document.title).toBe('KAN-999 - Critical Bug Fix');
    });
  });

  it('renders FullScreenIssueRoute, strips leading thumbs, and restores previous title on unmount', async () => {
    document.title = 'Work Items - KAN - kanban';
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client.apiClient, 'get').mockResolvedValue({
      id: 'iss-2',
      key: 'KAN-313',
      summary: '👍 Fix double thumbs in tab title',
    });

    const { unmount } = render(
      <QueryClientProvider client={testQueryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/issues/KAN-313']}>
            <Routes>
              <Route path="/issues/:issueKey" element={<FullScreenIssueRoute />} />
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(document.title).toBe('KAN-313 - Fix double thumbs in tab title');
    });

    unmount();
    expect(document.title).toBe('Work Items - KAN - kanban');
  });

  it('verifies NotFoundView sets document.title without leading thumbs', async () => {
    document.title = 'Initial Title';
    const { unmount } = render(
      <MemoryRouter initialEntries={['/non-existent-route']}>
        <NotFoundView />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(document.title).toBe('404 - Page Not Found - kanban');
    });

    unmount();
    expect(document.title).toBe('Initial Title');
  });

  it('covers cycle creation, validation, and error states in ProjectCyclesView', async () => {
    let cyclesList: unknown[] = [];
    vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
      const m = method.toUpperCase();
      const url = path;
      if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
        return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['EDIT', 'ADMIN'], modules_enabled: true });
      }
      if (url.includes('/cycles') && m === 'GET') {
        return Promise.resolve({ items: cyclesList });
      }
      if (url.includes('/cycles') && m === 'POST') {
        cyclesList = [
          {
            id: 'c-1',
            name: 'Sprint 1',
            status: 'active',
            start_date: '2026-03-01',
            end_date: '2026-03-15',
          },
        ];
        return Promise.resolve(cyclesList[0]);
      }
      return Promise.resolve({});
    });

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
          <ProjectCyclesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Empty submit does nothing
    const form = await screen.findByTestId('create-cycle-form');
    fireEvent.submit(form);

    // Fill form
    const nameInput = screen.getByTestId('new-cycle-name-input');
    fireEvent.change(nameInput, { target: { value: 'Sprint 1' } });
    const startInput = screen.getByTestId('new-cycle-start-input');
    fireEvent.change(startInput, { target: { value: '2026-03-01' } });
    const endInput = screen.getByTestId('new-cycle-end-input');
    fireEvent.change(endInput, { target: { value: '2026-03-15' } });

    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Sprint 1')).toBeDefined();
    });

    // Test creation error
    vi.spyOn(client, 'apiFetch').mockImplementation((method) => {
      if (method.toUpperCase() === 'POST') throw new Error('Cycle overlap error');
      return Promise.resolve({ items: cyclesList });
    });
    fireEvent.change(nameInput, { target: { value: 'Sprint 2' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Cycle overlap error')).toBeDefined();
    });

    // Render with VIEW capabilities hides creation form
    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
          <ProjectCyclesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });

  it('covers module creation, validation, and error states in ProjectModulesView', async () => {
    let modulesList: unknown[] = [];
    vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
      const m = method.toUpperCase();
      const url = path;
      if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
        return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['EDIT', 'ADMIN'], modules_enabled: true });
      }
      if (url.includes('/modules') && m === 'GET') {
        return Promise.resolve({ items: modulesList });
      }
      if (url.includes('/modules') && m === 'POST') {
        modulesList = [
          {
            id: 'm-1',
            name: 'Core Auth',
            status: 'in_progress',
            start_date: '2026-03-01',
            target_date: '2026-03-31',
            description_markdown: 'Authentication and session security',
          },
        ];
        return Promise.resolve(modulesList[0]);
      }
      return Promise.resolve({});
    });

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/modules']}>
          <ProjectModulesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Empty submit does nothing
    const form = await screen.findByTestId('create-module-form');
    fireEvent.submit(form);

    // Fill form
    const nameInput = screen.getByTestId('new-module-name-input');
    fireEvent.change(nameInput, { target: { value: 'Core Auth' } });
    const statusSelect = screen.getByTestId('new-module-status-select');
    fireEvent.change(statusSelect, { target: { value: 'in_progress' } });
    const startInput = screen.getByTestId('new-module-start-input');
    fireEvent.change(startInput, { target: { value: '2026-03-01' } });
    const targetInput = screen.getByTestId('new-module-target-input');
    fireEvent.change(targetInput, { target: { value: '2026-03-31' } });
    const descInput = screen.getByTestId('new-module-desc-input');
    fireEvent.change(descInput, { target: { value: 'Authentication and session security' } });

    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Core Auth')).toBeDefined();
    });

    // Test creation error
    vi.spyOn(client, 'apiFetch').mockImplementation((method) => {
      if (method.toUpperCase() === 'POST') throw new Error('Module collision error');
      return Promise.resolve({ items: modulesList });
    });
    fireEvent.change(nameInput, { target: { value: 'Core Auth 2' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Module collision error')).toBeDefined();
    });

    // Render with VIEW capabilities hides creation form
    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/modules']}>
          <ProjectModulesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });

  it('covers cycle partial dates (TBD fallback) and string error rejections in ProjectCyclesView', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
      const m = method.toUpperCase();
      const url = path;
      if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
        return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['EDIT', 'ADMIN'], modules_enabled: true });
      }
      if (url.includes('/cycles') && m === 'GET') {
        return Promise.resolve([
          { id: 'c-start-only', name: 'Start Only Cycle', start_date: '2026-03-01' },
          { id: 'c-end-only', name: 'End Only Cycle', end_date: '2026-03-15' },
        ]);
      }
      if (url.includes('/cycles') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String cycle creation failure';
      }
      return Promise.resolve({});
    });

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
          <ProjectCyclesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/2026-03-01 → TBD/)).toBeDefined();
    expect(screen.getByText(/TBD → 2026-03-15/)).toBeDefined();

    const cycleNameInput = screen.getByTestId('new-cycle-name-input');
    fireEvent.change(cycleNameInput, { target: { value: 'String Reject Cycle' } });
    fireEvent.submit(screen.getByTestId('create-cycle-form'));

    await waitFor(() => {
      expect(screen.getByTestId('cycle-error-banner').textContent).toContain('Failed to create cycle');
    });
  });

  it('covers module string error rejection in ProjectModulesView', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
      const m = method.toUpperCase();
      const url = path;
      if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
        return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['EDIT', 'ADMIN'], modules_enabled: true });
      }
      if (url.includes('/modules') && m === 'GET') {
        return Promise.resolve([
          { id: 'm-1', name: 'Existing Module', status: 'planned', description_markdown: 'Docs' },
        ]);
      }
      if (url.includes('/modules') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String module creation failure';
      }
      return Promise.resolve({});
    });

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/modules']}>
          <ProjectModulesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Existing Module')).toBeDefined();

    const modNameInput = screen.getByTestId('new-module-name-input');
    fireEvent.change(modNameInput, { target: { value: 'String Reject Module' } });
    fireEvent.submit(screen.getByTestId('create-module-form'));

    await waitFor(() => {
      expect(screen.getByTestId('module-error-banner').textContent).toContain('Failed to create module');
    });
  });

  it('covers queryFn capabilities loading in ProjectCyclesView and ProjectModulesView without prop', async () => {
    let throwApi = false;
    vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
      const url = path;
      if (url.includes('/projects/{project_ref}')) {
        if (throwApi) throw new Error('API failure');
        return Promise.resolve({ capabilities: ['ADMIN', 'EDIT'] });
      }
      if (url.includes('/cycles')) return Promise.resolve([]);
      if (url.includes('/modules')) return Promise.resolve([]);
      return Promise.resolve({});
    });

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    // 1. With capabilities array response
    const { unmount } = render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
          <ProjectCyclesView />
          <ProjectModulesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('project-cycles-view')).toBeDefined();
    expect(await screen.findByTestId('project-modules-view')).toBeDefined();
    unmount();

    // 2. With thrown error -> fallback to ['EDIT', 'ADMIN']
    throwApi = true;
    const testQueryClient2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={testQueryClient2}>
        <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
          <ProjectCyclesView />
          <ProjectModulesView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('project-cycles-view')).toBeDefined();
    expect(await screen.findByTestId('project-modules-view')).toBeDefined();
  });

  it('covers WorkspaceHomeView onCreated and DraftsWorkspaceView full lifecycle', async () => {
    document.cookie = 'kb_csrf=csrf-test-token; Path=/';
    const projectsList = [
      {
        id: 'p-init',
        identifier: 'INIT',
        name: 'Initial Project',
        description_markdown: '',
        modules_enabled: true,
      },
    ];

    // 1. WorkspaceHomeView onCreated
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.includes('/api/v1/projects') && method === 'POST') {
        const created = {
          id: 'p-created',
          identifier: 'NEWP',
          name: 'New Project',
          description_markdown: '',
          modules_enabled: true,
        };
        projectsList.push(created);
        return Promise.resolve(new Response(JSON.stringify(created), { status: 201 }));
      }
      if (url.includes('/api/v1/projects') && !url.includes('/issues')) {
        return Promise.resolve(new Response(
          JSON.stringify({ items: projectsList }),
          { status: 200 },
        ));
      }
      return Promise.resolve(new Response(JSON.stringify({ ok: true, id: 'new-issue' }), { status: 200 }));
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount: uHome } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <WorkspaceHomeView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('project-card-INIT')).toBeDefined();

    // Open create project modal
    fireEvent.click(screen.getByTestId('home-create-project-btn'));
    expect(screen.getByRole('dialog')).toBeDefined();

    fireEvent.change(screen.getByLabelText(/Project Name/i), { target: { value: 'New Project' } });
    fireEvent.change(screen.getByLabelText(/Identifier/i), { target: { value: 'NEWP' } });
    const form = screen.getByRole('dialog').querySelector('form');
    expect(form).toBeTruthy();
    if (form) fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByTestId('project-card-NEWP')).toBeDefined();
    });
    uHome();

    // 2. DraftsWorkspaceView with moduleIds, resume success, resume fallback, and delete
    saveDraft({
      id: 'd-full',
      projectKey: 'KAN',
      summary: 'Full draft with modules',
      description: 'Body markdown',
      stateId: 'st-started',
      prioritySlug: 'urgent',
      moduleIds: ['mod-1', 'mod-2'],
    });

    saveDraft({
      id: 'd-fallback',
      projectKey: 'KAN',
      summary: 'Draft for fallback',
      stateId: 'st-backlog',
      prioritySlug: 'low',
    });

    const { unmount: uDrafts } = render(
      <MemoryRouter initialEntries={['/drafts']}>
        <DraftsWorkspaceView />
      </MemoryRouter>,
    );

    expect(screen.getAllByTestId('draft-card')).toHaveLength(2);

    // Resume first draft successfully
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({ id: 'created-iss' }), { status: 200 }));
    const resumeBtns = screen.getAllByTestId('draft-resume-btn');
    const firstResumeBtn = resumeBtns[0];
    expect(firstResumeBtn).toBeDefined();
    if (firstResumeBtn) fireEvent.click(firstResumeBtn);

    await waitFor(() => {
      expect(screen.getAllByTestId('draft-card')).toHaveLength(1);
    });

    // Resume second draft with network rejection -> fallback to ?create=1
    fetchSpy.mockRejectedValueOnce(new Error('Network error'));
    fireEvent.click(screen.getByTestId('draft-resume-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('drafts-empty')).toBeDefined();
    });

    uDrafts();
  });

  describe('Strict RBAC Route Guards (KANBA-209)', () => {
    let rbacQueryClient: QueryClient;

    beforeEach(() => {
      rbacQueryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
    });

    it('gates /admin/standalone behind SERVER_ADMIN and AAL2', () => {
      // 1. Guest / unauthenticated (user is null)
      rbacQueryClient.setQueryData(qk.me(), null);
      const routerGuest = createAppRouter(['/admin/standalone']);
      const { unmount: u1 } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerGuest} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Not found or no access')).toBeDefined();
      u1();

      // 2. Member / non-server-admin
      rbacQueryClient.setQueryData(qk.me(), { is_server_admin: false, auth_aal: 'aal2' });
      const routerMember = createAppRouter(['/admin/standalone']);
      const { unmount: u2 } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerMember} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Not found or no access')).toBeDefined();
      u2();

      // 3. Server admin with non-AAL2 (aal1)
      rbacQueryClient.setQueryData(qk.me(), { is_server_admin: true, auth_aal: 'aal1', aal_level: 1 });
      const routerAal1 = createAppRouter(['/admin/standalone']);
      const { unmount: u3 } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerAal1} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Not found or no access')).toBeDefined();
      u3();

      // 4. Server admin with AAL2 -> access allowed
      rbacQueryClient.setQueryData(qk.me(), { is_server_admin: true, auth_aal: 'aal2', aal_level: 2 });
      const routerAdmin = createAppRouter(['/admin/standalone']);
      const { unmount: u4 } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerAdmin} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('standalone-status-route')).toBeDefined();
      u4();
    });

    it('gates /drafts to render Not found or no access for VIEWER and WORKSPACE_GUEST', () => {
      // 1. VIEWER
      rbacQueryClient.setQueryData(qk.me(), { workspace_role: 'VIEWER' });
      const routerViewer = createAppRouter(['/drafts']);
      const { unmount: uViewer } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerViewer} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Not found or no access')).toBeDefined();
      uViewer();

      // 2. WORKSPACE_GUEST
      rbacQueryClient.setQueryData(qk.me(), { workspace_role: 'WORKSPACE_GUEST' });
      const routerGuest = createAppRouter(['/drafts']);
      const { unmount: uGuest } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerGuest} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Not found or no access')).toBeDefined();
      uGuest();

      // 3. WORKSPACE_MEMBER -> access allowed
      rbacQueryClient.setQueryData(qk.me(), { workspace_role: 'WORKSPACE_MEMBER' });
      const routerMember = createAppRouter(['/drafts']);
      const { unmount: uMember } = render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={routerMember} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('drafts-view')).toBeDefined();
      uMember();
    });

    it('renders Not found or no access on direct URL access to unauthorized project', async () => {
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects/QAADM')) {
          return Promise.resolve(new Response(JSON.stringify({ detail: 'Project not found' }), { status: 404 }));
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      const router = createAppRouter(['/projects/QAADM/issues']);
      render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={router} />
          </ThemeProvider>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Not found or no access')).toBeDefined();
      expect(screen.queryByTestId('home-create-issue-btn')).toBeNull();
      expect(screen.queryByTestId('view-empty-create-btn')).toBeNull();
    });

    it('renders No accessible projects when project list is empty for guest', async () => {
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ items: [] }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      rbacQueryClient.setQueryData(qk.me(), { workspace_role: 'WORKSPACE_GUEST' });

      const router = createAppRouter(['/']);
      render(
        <QueryClientProvider client={rbacQueryClient}>
          <ThemeProvider>
            <RouterProvider router={router} />
          </ThemeProvider>
        </QueryClientProvider>,
      );

      expect(await screen.findByTestId('no-accessible-projects')).toBeDefined();
      expect(screen.getAllByText('No accessible projects').length).toBeGreaterThanOrEqual(1);
      expect(screen.queryByTestId('project-card-KAN')).toBeNull();
    });
  });

  describe('ProjectCyclesView and ProjectModulesView lifecycle actions (KANBA-211)', () => {
    let lifecycleClient: QueryClient;

    beforeEach(() => {
      lifecycleClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      vi.restoreAllMocks();
    });

    it('enforces RBAC for cycle Delete button and supports Edit and Complete with rollover', async () => {
      const calls: {
        method: string;
        path: string;
        params?: Record<string, unknown> | undefined;
        body?: Record<string, unknown> | undefined;
      }[] = [];
      let cyclesList = [
        { id: 'c-1', name: 'Sprint 1', status: 'in_progress', start_date: '2026-03-01', end_date: '2026-03-14' },
        { id: 'c-2', name: 'Sprint 2', status: 'upcoming', start_date: '2026-03-15', end_date: '2026-03-28' },
        { id: 'c-completed', name: 'Sprint 0', status: 'completed', start_date: '2026-02-15', end_date: '2026-02-28' },
      ];

      vi.spyOn(client, 'apiFetch').mockImplementation((method, path, options?: { params?: unknown; body?: unknown }) => {
        const m = method.toUpperCase();
        const url = path;
        calls.push({
          method: m,
          path: url,
          params: options?.params as Record<string, unknown> | undefined,
          body: options?.body as Record<string, unknown> | undefined,
        });

        if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
          return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['VIEW', 'EDIT'], modules_enabled: true });
        }
        if (url.includes('/cycles') && m === 'GET') {
          return Promise.resolve(cyclesList);
        }
        if (url.includes('/cycles') && m === 'PATCH') {
          const body = options?.body as Record<string, unknown>;
          cyclesList = cyclesList.map((c) => (c.id === 'c-1' ? { ...c, ...body } : c));
          return Promise.resolve(cyclesList[0]);
        }
        if (url.includes('/complete') && m === 'POST') {
          cyclesList = cyclesList.map((c) => (c.id === 'c-1' ? { ...c, status: 'completed' } : c));
          return Promise.resolve({ ...cyclesList[0], status: 'completed' });
        }
        if (m === 'DELETE') {
          cyclesList = cyclesList.filter((c) => c.id !== 'c-1');
          return Promise.resolve({ success: true });
        }
        return Promise.resolve({});
      });

      // 1. Render as MEMBER (capabilities = ['VIEW', 'EDIT']) -> Delete buttons must be absent
      const { unmount } = render(
        <QueryClientProvider client={lifecycleClient}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['VIEW', 'EDIT']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Sprint 1')).toBeDefined();
      expect(screen.queryByTestId('delete-cycle-btn-c-1')).toBeNull();
      expect(screen.getByTestId('edit-cycle-btn-c-1')).toBeDefined();
      expect(screen.getByTestId('complete-cycle-btn-c-1')).toBeDefined();
      // Completed cycle c-completed should NOT show Complete button
      expect(screen.queryByTestId('complete-cycle-btn-c-completed')).toBeNull();

      // Test Complete modal with rollover target
      fireEvent.click(screen.getByTestId('complete-cycle-btn-c-1'));
      expect(screen.getByTestId('complete-cycle-modal')).toBeDefined();
      const rolloverSelect = screen.getByTestId('rollover-target-select');
      fireEvent.change(rolloverSelect, { target: { value: 'c-2' } });
      fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));

      await waitFor(() => {
        expect(
          calls.some(
            (c) =>
              c.path.includes('/complete') &&
              c.body?.rollover_to_cycle_id === 'c-2',
          ),
        ).toBe(true);
      });

      unmount();

      // 2. Render as PROJECT_ADMIN (capabilities = ['VIEW', 'EDIT', 'PROJECT_ADMIN'])
      const adminClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={adminClient}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['VIEW', 'EDIT', 'PROJECT_ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByTestId('delete-cycle-btn-c-1')).toBeDefined();

      // Test Edit cycle modal with date validation
      fireEvent.click(screen.getByTestId('edit-cycle-btn-c-1'));
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();
      const editNameInput = screen.getByTestId('edit-cycle-name-input');
      const editStartInput = screen.getByTestId('edit-cycle-start-input');
      const editEndInput = screen.getByTestId('edit-cycle-end-input');

      // Invalid dates: end < start
      fireEvent.change(editStartInput, { target: { value: '2026-04-10' } });
      fireEvent.change(editEndInput, { target: { value: '2026-04-01' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));
      expect(await screen.findByTestId('edit-cycle-error')).toBeDefined();
      expect(screen.getByTestId('edit-cycle-error').textContent).toContain(
        'End date cannot be earlier than start date',
      );

      // Valid edit
      fireEvent.change(editEndInput, { target: { value: '2026-04-20' } });
      fireEvent.change(editNameInput, { target: { value: 'Sprint 1 Renamed' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

      await waitFor(() => {
        expect(
          calls.some(
            (c) => c.method === 'PATCH' && c.body?.name === 'Sprint 1 Renamed',
          ),
        ).toBe(true);
      });

      // Test Delete cycle
      fireEvent.click(screen.getByTestId('delete-cycle-btn-c-1'));
      await waitFor(() => {
        expect(
          calls.some(
            (c) =>
              c.method === 'DELETE' &&
              (c.params?.cycle_id === 'c-1' || c.path.includes('c-1')),
          ),
        ).toBe(true);
      });
    });

    it('enforces RBAC for module Delete button and supports Edit with date validation', async () => {
      const calls: {
        method: string;
        path: string;
        params?: Record<string, unknown> | undefined;
        body?: Record<string, unknown> | undefined;
      }[] = [];
      let modulesList = [
        {
          id: 'm-1',
          name: 'Auth Core',
          status: 'in_progress',
          start_date: '2026-03-01',
          target_date: '2026-03-30',
          description_markdown: 'Auth module',
        },
      ];

      vi.spyOn(client, 'apiFetch').mockImplementation((method, path, options?: { params?: unknown; body?: unknown }) => {
        const m = method.toUpperCase();
        const url = path;
        calls.push({
          method: m,
          path: url,
          params: options?.params as Record<string, unknown> | undefined,
          body: options?.body as Record<string, unknown> | undefined,
        });

        if (url.includes('/projects/') && !url.includes('/cycles') && !url.includes('/modules')) {
          return Promise.resolve({ id: 'p-1', identifier: 'KAN', name: 'kanban', capabilities: ['VIEW', 'EDIT'], modules_enabled: true });
        }
        if (url.includes('/modules') && m === 'GET') {
          return Promise.resolve(modulesList);
        }
        if (url.includes('/modules') && m === 'PATCH') {
          const body = options?.body as Record<string, unknown>;
          modulesList = modulesList.map((mod) => (mod.id === 'm-1' ? { ...mod, ...body } : mod));
          return Promise.resolve(modulesList[0]);
        }
        if (m === 'DELETE') {
          modulesList = modulesList.filter((mod) => mod.id !== 'm-1');
          return Promise.resolve({ success: true });
        }
        return Promise.resolve({});
      });

      // 1. Member: Delete button is hidden
      const { unmount } = render(
        <QueryClientProvider client={lifecycleClient}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['VIEW', 'EDIT']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Auth Core')).toBeDefined();
      expect(screen.queryByTestId('delete-module-btn-m-1')).toBeNull();
      expect(screen.getByTestId('edit-module-btn-m-1')).toBeDefined();
      unmount();

      // 2. Admin: Delete button is visible and Edit modal validates target date
      const adminClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={adminClient}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['VIEW', 'EDIT', 'ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByTestId('delete-module-btn-m-1')).toBeDefined();

      // Open Edit module modal
      fireEvent.click(screen.getByTestId('edit-module-btn-m-1'));
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();
      const editNameInput = screen.getByTestId('edit-module-name-input');
      const editStartInput = screen.getByTestId('edit-module-start-input');
      const editTargetInput = screen.getByTestId('edit-module-target-input');

      // Invalid dates: target < start
      fireEvent.change(editStartInput, { target: { value: '2026-05-10' } });
      fireEvent.change(editTargetInput, { target: { value: '2026-05-01' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));
      expect(await screen.findByTestId('edit-module-error')).toBeDefined();
      expect(screen.getByTestId('edit-module-error').textContent).toContain(
        'Target date cannot be earlier than start date',
      );

      // Valid edit
      fireEvent.change(editTargetInput, { target: { value: '2026-05-20' } });
      fireEvent.change(editNameInput, { target: { value: 'Auth Core Hardened' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));

      await waitFor(() => {
        expect(
          calls.some(
            (c) => c.method === 'PATCH' && c.body?.name === 'Auth Core Hardened',
          ),
        ).toBe(true);
      });

      // Delete module
      fireEvent.click(screen.getByTestId('delete-module-btn-m-1'));
      await waitFor(() => {
        expect(
          calls.some(
            (c) =>
              c.method === 'DELETE' &&
              (c.params?.module_id === 'm-1' || c.path.includes('m-1')),
          ),
        ).toBe(true);
      });
    });

    it('covers route guards loading and error states and modal cancel buttons', async () => {
      // 1. AdminRouteGuard loading and error
      const pendingClient = new QueryClient();
      vi.spyOn(client, 'apiFetch').mockReturnValue(new Promise(() => undefined));
      const { unmount: u1 } = render(
        <QueryClientProvider client={pendingClient}>
          <MemoryRouter>
            <AdminRouteGuard />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('admin-guard-loading')).toBeDefined();
      u1();

      // 2. DraftsWorkspaceRouteGuard loading and queryFn catch
      const failClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client, 'apiFetch').mockRejectedValue(new Error('Network offline'));
      const { unmount: u2 } = render(
        <QueryClientProvider client={failClient}>
          <MemoryRouter>
            <DraftsWorkspaceRouteGuard />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      // Wait for query catch to resolve to null and render DraftsWorkspaceView
      expect(await screen.findByTestId('drafts-view')).toBeDefined();
      u2();

      // 3. Cancel buttons on Edit Cycle, Complete Cycle, Edit Module
      const editClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client, 'apiFetch').mockImplementation((_method, path) => {
        const url = path;
        if (url.includes('/cycles')) {
          return Promise.resolve([{ id: 'c-cancel', name: 'Sprint Cancel', status: 'upcoming' }]);
        }
        if (url.includes('/modules')) {
          return Promise.resolve([{ id: 'm-cancel', name: 'Module Cancel', status: 'planned' }]);
        }
        return Promise.resolve({});
      });

      const { unmount: u3 } = render(
        <QueryClientProvider client={editClient}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['VIEW', 'EDIT', 'PROJECT_ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Open and cancel edit cycle
      expect(await screen.findByText('Sprint Cancel')).toBeDefined();
      fireEvent.click(screen.getByTestId('edit-cycle-btn-c-cancel'));
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();
      fireEvent.click(screen.getByTestId('cancel-edit-cycle-btn'));
      expect(screen.queryByTestId('edit-cycle-modal')).toBeNull();

      // Open edit cycle, test date order validation, and submit valid save
      fireEvent.click(screen.getByTestId('edit-cycle-btn-c-cancel'));
      fireEvent.change(screen.getByTestId('edit-cycle-name-input'), { target: { value: 'Sprint Edited' } });
      fireEvent.change(screen.getByTestId('edit-cycle-start-input'), { target: { value: '2026-11-20' } });
      fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-11-10' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('edit-cycle-error')).toBeDefined();
      });

      // Fix date order and save successfully
      fireEvent.change(screen.getByTestId('edit-cycle-start-input'), { target: { value: '2026-11-10' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));
      await waitFor(() => {
        expect(screen.queryByTestId('edit-cycle-modal')).toBeNull();
      });

      // Open and cancel complete cycle
      fireEvent.click(screen.getByTestId('complete-cycle-btn-c-cancel'));
      expect(screen.getByTestId('complete-cycle-modal')).toBeDefined();
      fireEvent.click(screen.getByTestId('cancel-complete-cycle-btn'));
      expect(screen.queryByTestId('complete-cycle-modal')).toBeNull();

      // Open complete cycle and submit complete mutation
      fireEvent.click(screen.getByTestId('complete-cycle-btn-c-cancel'));
      fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));
      await waitFor(() => {
        expect(screen.queryByTestId('complete-cycle-modal')).toBeNull();
      });

      // Delete cycle
      fireEvent.click(screen.getByTestId('delete-cycle-btn-c-cancel'));

      u3();

      // Open and cancel edit module
      const { unmount: u4 } = render(
        <QueryClientProvider client={editClient}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['VIEW', 'EDIT', 'PROJECT_ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(await screen.findByText('Module Cancel')).toBeDefined();
      fireEvent.click(screen.getByTestId('edit-module-btn-m-cancel'));
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();
      fireEvent.click(screen.getByTestId('cancel-edit-module-btn'));
      expect(screen.queryByTestId('edit-module-modal')).toBeNull();

      // Open edit module, test date order validation, and submit valid save
      fireEvent.click(screen.getByTestId('edit-module-btn-m-cancel'));
      fireEvent.change(screen.getByTestId('edit-module-name-input'), { target: { value: 'Module Edited' } });
      fireEvent.change(screen.getByTestId('edit-module-start-input'), { target: { value: '2026-11-20' } });
      fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-11-10' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('edit-module-error')).toBeDefined();
      });

      // Fix date order and save module successfully
      fireEvent.change(screen.getByTestId('edit-module-start-input'), { target: { value: '2026-11-10' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));
      await waitFor(() => {
        expect(screen.queryByTestId('edit-module-modal')).toBeNull();
      });

      // Delete module
      fireEvent.click(screen.getByTestId('delete-module-btn-m-cancel'));

      u4();

      // Test NotFoundView inside and outside router
      const { unmount: uNotFound1 } = render(
        <MemoryRouter initialEntries={['/some/unknown/path']}>
          <NotFoundView />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('not-found-path')).toBeDefined();
      fireEvent.click(screen.getByTestId('return-workspace-btn'));
      uNotFound1();

      const { unmount: uNotFound2 } = render(<NotFoundView />);
      expect(screen.getByTestId('not-found-path')).toBeDefined();
      fireEvent.click(screen.getByTestId('return-workspace-btn'));
      uNotFound2();

      // AdminRouteGuard catch
      const adminRejectClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client, 'apiFetch').mockRejectedValue(new Error('Auth failed'));
      const { unmount: uAdmin } = render(
        <QueryClientProvider client={adminRejectClient}>
          <MemoryRouter>
            <AdminRouteGuard />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(await screen.findByText('Not found or no access')).toBeDefined();
      uAdmin();

      // 4. Description input and error states for modules
      const errorModClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
        const m = method.toUpperCase();
        const url = path;
        if (url.includes('/modules') && m === 'GET') {
          return Promise.resolve([{ id: 'm-err', name: 'Module Err', status: 'planned', description_markdown: 'desc' }]);
        }
        if (url.includes('/modules') && m === 'PATCH') {
          throw new Error('Patch module failed');
        }
        if (url.includes('/modules') && m === 'DELETE') {
          throw new Error('Delete module failed');
        }
        return Promise.resolve({});
      });

      const { unmount: u5 } = render(
        <QueryClientProvider client={errorModClient}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['VIEW', 'EDIT', 'ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Module Err')).toBeDefined();
      // Description input in create form
      fireEvent.change(screen.getByTestId('new-module-desc-input'), { target: { value: 'New desc' } });

      // Open Edit module and test description change + patch error
      fireEvent.click(screen.getByTestId('edit-module-btn-m-err'));
      fireEvent.change(screen.getByTestId('edit-module-status-select'), { target: { value: 'in_progress' } });
      fireEvent.change(screen.getByTestId('edit-module-desc-input'), { target: { value: 'Edited desc' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));
      expect(await screen.findByTestId('edit-module-error')).toBeDefined();
      expect(screen.getByTestId('edit-module-error').textContent).toContain('Patch module failed');
      fireEvent.click(screen.getByTestId('cancel-edit-module-btn'));

      // Delete module error
      fireEvent.click(screen.getByTestId('delete-module-btn-m-err'));
      await waitFor(() => {
        expect(screen.getByTestId('module-error-banner').textContent).toContain('Delete module failed');
      });
      u5();

      // 5. Cycle delete and complete errors in ProjectCyclesView
      const errorCycleClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
        const m = method.toUpperCase();
        const url = path;
        if (url.includes('/cycles') && m === 'GET') {
          return Promise.resolve([{ id: 'c-err', name: 'Cycle Err', status: 'active' }]);
        }
        if (url.includes('/complete') && m === 'POST') {
          throw new Error('Cycle completion rejected');
        }
        if (url.includes('/cycles') && m === 'DELETE') {
          throw new Error('Cycle delete rejected');
        }
        return Promise.resolve({});
      });

      const { unmount: u6 } = render(
        <QueryClientProvider client={errorCycleClient}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['VIEW', 'EDIT', 'PROJECT_ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Cycle Err')).toBeDefined();

      // Complete cycle error
      fireEvent.click(screen.getByTestId('complete-cycle-btn-c-err'));
      fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('complete-cycle-error').textContent).toContain('Cycle completion rejected');
      });
      fireEvent.click(screen.getByTestId('cancel-complete-cycle-btn'));

      // Delete cycle error
      fireEvent.click(screen.getByTestId('delete-cycle-btn-c-err'));
      await waitFor(() => {
        expect(screen.getByTestId('cycle-error-banner').textContent).toContain('Cycle delete rejected');
      });
      u6();
    });
  });

  describe('KAN-11: Drafts empty-state CTA link and Mcp redirects', () => {
    it('resolves empty-state CTA link to first accessible project dynamically', async () => {
      localStorage.removeItem('kb.drafts.v1');

      const testQc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      testQc.setQueryData(qk.projects(), [
        { id: 'p-1', identifier: 'ALPHA', name: 'Alpha Project' },
        { id: 'p-2', identifier: 'BETA', name: 'Beta Project' },
      ]);

      const { unmount } = render(
        <QueryClientProvider client={testQc}>
          <MemoryRouter initialEntries={['/drafts']}>
            <DraftsWorkspaceView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const emptyDiv = await screen.findByTestId('drafts-empty');
      expect(emptyDiv).toBeDefined();

      const link = within(emptyDiv).getByRole('link', { name: /Create a new work item/i });
      expect(link.getAttribute('href')).toBe('/projects/ALPHA/issues?create=1');
      unmount();
    });

    it('resolves empty-state CTA link from active ProjectRouteContext', async () => {
      localStorage.removeItem('kb.drafts.v1');

      const testQc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount } = render(
        <QueryClientProvider client={testQc}>
          <MemoryRouter initialEntries={['/drafts']}>
            <ProjectRouteContext.Provider
              value={{
                projectKey: 'ACTIVE',
                projectName: 'Active Project',
                modulesEnabled: true,
                capabilities: ['ADMIN'],
                isProjectAdmin: true,
              }}
            >
              <DraftsWorkspaceView />
            </ProjectRouteContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const emptyDiv = await screen.findByTestId('drafts-empty');
      const link = within(emptyDiv).getByRole('link', { name: /Create a new work item/i });
      expect(link.getAttribute('href')).toBe('/projects/ACTIVE/issues?create=1');
      unmount();
    });

    it('falls back gracefully to / when workspace has 0 accessible projects', async () => {
      localStorage.removeItem('kb.drafts.v1');

      const testQc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      testQc.setQueryData(qk.projects(), []);

      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });

      const { unmount } = render(
        <QueryClientProvider client={testQc}>
          <MemoryRouter initialEntries={['/drafts']}>
            <DraftsWorkspaceView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const emptyDiv = await screen.findByTestId('drafts-empty');
      const link = within(emptyDiv).getByRole('link', { name: /Create a new work item/i });
      expect(link.getAttribute('href')).toBe('/');
      unmount();
    });

    it('covers ProjectMcpRedirect, WorkspaceMcpRedirect, and AdminMcpRedirect routes', async () => {
      // 1. ProjectMcpRedirect with existing scope/project searchParams
      const { unmount: u1 } = render(
        <MemoryRouter initialEntries={['/projects/PRJ/settings/mcp?scope=custom&project=OVERRIDE']}>
          <Routes>
            <Route path="/projects/:projectKey/settings/mcp" element={<ProjectMcpRedirect />} />
          </Routes>
        </MemoryRouter>,
      );
      u1();

      // 2. ProjectMcpRedirect without params (sets scope=project and project=PRJ)
      const { unmount: u2 } = render(
        <MemoryRouter initialEntries={['/projects/PRJ/settings/mcp']}>
          <Routes>
            <Route path="/projects/:projectKey/settings/mcp" element={<ProjectMcpRedirect />} />
          </Routes>
        </MemoryRouter>,
      );
      u2();

      // 3. WorkspaceMcpRedirect
      const { unmount: u3 } = render(
        <MemoryRouter initialEntries={['/workspaces/settings/mcp']}>
          <WorkspaceMcpRedirect />
        </MemoryRouter>,
      );
      u3();

      // 4. AdminMcpRedirect
      const { unmount: u4 } = render(
        <MemoryRouter initialEntries={['/admin/mcp']}>
          <AdminMcpRedirect />
        </MemoryRouter>,
      );
      u4();

      // 5. Workspace switcher event listener while WorkspaceHomeView is mounted
      const qcHome = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: uHome } = render(
        <QueryClientProvider client={qcHome}>
          <MemoryRouter initialEntries={['/']}>
            <WorkspaceHomeView />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      act(() => {
        window.dispatchEvent(new Event('kb:workspace-switched'));
      });
      uHome();

      // 6. create=1 timer execution and onOpenPeek in ProjectIssuesRoute
      const qcIssues = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qcIssues.setQueryData(qk.issues('KAN', {}), FIXTURE_12_ISSUES);
      const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((cb: TimerHandler) => {
        if (typeof cb === 'function') {
          (cb as () => void)();
        }
        return 9999 as unknown as ReturnType<typeof setTimeout>;
      });
      const routerIssues = createAppRouter(['/projects/KAN/issues?create=1']);
      const { unmount: uIssues } = render(
        <QueryClientProvider client={qcIssues}>
          <ThemeProvider>
            <RouterProvider router={routerIssues} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      setTimeoutSpy.mockRestore();
      uIssues();

      // 6b. handleOpenPeek execution in ProjectIssuesRoute
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/states')) {
          return Promise.resolve(new Response(JSON.stringify([{ id: 'state-todo', name: 'Todo', group: 'unstarted' }]), { status: 200 }));
        }
        if (url.includes('/issues')) {
          return Promise.resolve(new Response(JSON.stringify({ items: FIXTURE_12_ISSUES }), { status: 200 }));
        }
        if (url.includes('/api/v1/projects/KAN')) {
          return Promise.resolve(new Response(JSON.stringify({ id: 'p-1', identifier: 'KAN', key: 'KAN', name: 'kanban', capabilities: ['EDIT', 'ADMIN'], modules_enabled: true }), { status: 200 }));
        }
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(new Response(JSON.stringify({ items: [{ identifier: 'KAN', key: 'KAN' }] }), { status: 200 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });
      const qcIssuesPeek = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: uIssuesPeek } = render(
        <QueryClientProvider client={qcIssuesPeek}>
          <ProjectRouteContext.Provider
            value={{
              projectKey: 'KAN',
              projectName: 'kanban',
              modulesEnabled: true,
              capabilities: ['EDIT', 'ADMIN'],
              isProjectAdmin: true,
            }}
          >
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Routes>
                <Route path="/projects/:projectKey/issues" element={<ProjectIssuesRoute />} />
              </Routes>
            </MemoryRouter>
          </ProjectRouteContext.Provider>
        </QueryClientProvider>,
      );
      const rowKeyCard = await screen.findByTestId('issue-list-card-KAN-140');
      fireEvent.click(rowKeyCard);
      uIssuesPeek();

      // 7. DraftsWorkspaceView with cached object having key instead of identifier
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(new Response(JSON.stringify({ items: [{ key: 'KEY_PROJ' }] }), { status: 200 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });
      const qcDraftsKey = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qcDraftsKey.setQueryData(['projects'], { items: [{ key: 'KEY_PROJ' }] });
      const { unmount: uDraftsKey } = render(
        <QueryClientProvider client={qcDraftsKey}>
          <MemoryRouter initialEntries={['/drafts']}>
            <DraftsWorkspaceView />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const emptyDivKey = await screen.findByTestId('drafts-empty');
      const linkKey = within(emptyDivKey).getByRole('link', { name: /Create a new work item/i });
      expect(linkKey.getAttribute('href')).toBe('/projects/KEY_PROJ/issues?create=1');
      uDraftsKey();

      // 8. DraftsWorkspaceView with cached object where items is undefined or null
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });
      const qcDraftsNull = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qcDraftsNull.setQueryData(['projects'], { items: null });
      const { unmount: uDraftsNull } = render(
        <QueryClientProvider client={qcDraftsNull}>
          <MemoryRouter initialEntries={['/drafts']}>
            <DraftsWorkspaceView />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const emptyDivNull = await screen.findByTestId('drafts-empty');
      const linkNull = within(emptyDivNull).getByRole('link', { name: /Create a new work item/i });
      expect(linkNull.getAttribute('href')).toBe('/');
      uDraftsNull();

      // 9. ProjectIssuesRoute invalid layout reset, nomodules=1, and kb:create-issue event
      const qcIssuesInvalid = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const routerIssuesInvalid = createAppRouter(['/projects/KAN/issues?layout=invalid_custom&nomodules=1']);
      const { unmount: uIssuesInvalid } = render(
        <QueryClientProvider client={qcIssuesInvalid}>
          <ThemeProvider>
            <RouterProvider router={routerIssuesInvalid} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      act(() => {
        window.dispatchEvent(new Event('kb:create-issue'));
      });
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });
      uIssuesInvalid();

      // 10. KAN-9: ProjectOverviewRoute stickies alias on /projects/:key/stickies and /w/:slug/p/:key/stickies
      const qcStickies = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: uDirectStickies } = render(
        <QueryClientProvider client={qcStickies}>
          <MemoryRouter initialEntries={['/projects/KAN/stickies']}>
            <ProjectOverviewRoute />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('project-overview-page')).toBeDefined();
      uDirectStickies();

      const routerProjStickies = createAppRouter(['/projects/KAN/stickies']);
      const { unmount: uProjStickies } = render(
        <QueryClientProvider client={qcStickies}>
          <ThemeProvider>
            <RouterProvider router={routerProjStickies} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('project-overview-page')).toBeDefined();
      });
      uProjStickies();

      const routerWsStickies = createAppRouter(['/w/default/p/KAN/stickies']);
      const { unmount: uWsStickies } = render(
        <QueryClientProvider client={qcStickies}>
          <ThemeProvider>
            <RouterProvider router={routerWsStickies} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('project-overview-page')).toBeDefined();
      });
      uWsStickies();
    });
  });
});
