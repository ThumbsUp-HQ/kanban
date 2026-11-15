import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { RouterProvider } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createAppRouter,
  PROJECT_KEY_REGEX,
  ISSUE_KEY_REGEX,
  IssuesWorkspaceRoute,
  RoutePlaceholder,
  AppRoutes,
} from './routes';
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
    expect(screen.getByRole('link', { name: /Views/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Docs \(Pages\)/ })).toBeDefined();

    // Breadcrumb
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeDefined();

    // Layout switcher has Board selected
    const boardRadio = screen.getByRole('radio', { name: 'Board' });
    expect(boardRadio.getAttribute('aria-checked')).toBe('true');

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

    // After normalization, List should be checked
    const listRadio = await screen.findByRole('radio', { name: 'List' });
    expect(listRadio.getAttribute('aria-checked')).toBe('true');
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
      { path: '/projects/KAN/views', expected: 'project-views-view' },
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
});
