import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { RouterProvider } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAppRouter, PROJECT_KEY_REGEX, ISSUE_KEY_REGEX } from './routes';
import { ThemeProvider } from '../theme/ThemeProvider';

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
      { path: '/projects/KAN/overview', expected: 'route-placeholder' },
      { path: '/projects/KAN/docs', expected: 'route-placeholder' },
      { path: '/projects/KAN/docs/page-42', expected: 'route-placeholder' },
      { path: '/projects/KAN/issues/KAN-100', expected: 'route-placeholder' },
      { path: '/stickies', expected: 'route-placeholder' },
      { path: '/login', expected: 'route-placeholder' },
      { path: '/setup', expected: 'route-placeholder' },
      { path: '/admin/auth', expected: 'route-placeholder' },
      { path: '/__dev/tokens', expected: 'token-story' },
      { path: '/__dev/emoji', expected: 'emoji-story' },
      { path: '/__dev/editor', expected: 'editor-story' },
      { path: '/__dev/media', expected: 'media-story' },
      { path: '/__dev/realtime', expected: 'realtime-story' },
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
});
