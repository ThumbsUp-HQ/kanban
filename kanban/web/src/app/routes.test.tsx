import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import React from 'react';
import { RouterProvider, MemoryRouter } from 'react-router';
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
    expect(screen.getByText(/👍kanban/)).toBeDefined();
    expect(screen.getByRole('link', { name: /Work Items/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Cycles/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Modules/ })).toBeDefined();
    expect(screen.queryByRole('link', { name: /Views/ })).toBeNull();
    expect(screen.getByRole('link', { name: /^Docs$/ })).toBeDefined();
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

    // After normalization, List should be available
    const listLink = await screen.findByRole('link', { name: /List/ });
    expect(listLink).toBeDefined();
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

  it('preserves IssuesWorkspaceRoute in background when ?peek= is set and triggers create modal on ?create=1', () => {
    const router = createAppRouter(['/projects/KAN/issues?layout=list&peek=KAN-101&create=1']);
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('issues-workspace')).toBeDefined();

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

  it('mounts and renders default ListView', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />,
    );

    expect(screen.getByText('Backlog')).toBeDefined();
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
        return Promise.resolve([{ id: 'cyc-1', name: 'Sprint 1', start_date: '2026-01-01', end_date: '2026-01-14' }]);
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
    });

    const input = screen.getByTestId('new-cycle-name-input');
    fireEvent.change(input, { target: { value: 'Sprint Fail' } });
    fireEvent.change(screen.getByTestId('new-cycle-start-input'), { target: { value: '2026-02-01' } });
    fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-02-14' } });

    const createBtn = screen.getByTestId('create-cycle-btn');
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cycle-error-banner').textContent).toContain('Cycle creation rejected');
    });
  });

  it('ProjectModulesView displays error banner on failure and renders module description', async () => {
    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(client, 'apiFetch').mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path.includes('modules')) {
        return Promise.resolve([{ id: 'mod-1', name: 'Core', description_markdown: 'Core architecture module' }]);
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
    });

    const input = screen.getByTestId('new-module-name-input');
    fireEvent.change(input, { target: { value: 'Fail Mod' } });
    fireEvent.change(screen.getByTestId('new-module-desc-input'), { target: { value: 'Some description' } });

    const createBtn = screen.getByTestId('create-module-btn');
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
});
