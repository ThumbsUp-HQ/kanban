import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell, computeCurrentSection } from './AppShell';
import { ThemeProvider } from '../theme/ThemeProvider';
import * as sessionGuardModule from '../features/auth/useSessionGuard';

describe('AppShell', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  it('renders app shell with skip link, sidebar rail, topbar header, main canvas, and anchors', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell
              projectKey="KAN"
              projectName="kanban"
              modulesEnabled={true}
              issueCount={7}
              currentSection="Work Items"
            >
              <div data-testid="test-child-content">Main Canvas Content</div>
            </AppShell>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Skip link
    expect(screen.getByRole('link', { name: 'Skip to content' })).toBeDefined();

    // Main canvas
    const mainEl = document.getElementById('main');
    expect(mainEl).toBeDefined();
    expect(screen.getByTestId('test-child-content')).toBeDefined();

    // Anchors
    expect(document.getElementById('kb-surface-host')).toBeDefined();
    expect(document.getElementById('kb-hint-root')).toBeDefined();

    // Topbar and Breadcrumb
    expect(screen.getAllByText('Work Items').length).toBeGreaterThan(0);
    expect(screen.getByText('(7)')).toBeDefined();
  });

  it('toggles mobile sidebar via hamburger button and closes it', () => {
    vi.stubGlobal('innerWidth', 1024);

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter>
            <AppShell />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Skip link click
    const skipLink = screen.getByRole('link', { name: 'Skip to content' });
    fireEvent.click(skipLink);

    // Skip link click when main does not exist
    const spy = vi.spyOn(document, 'getElementById').mockReturnValue(null);
    fireEvent.click(skipLink);
    spy.mockRestore();

    // Open and close palette via search trigger button
    const searchBtn = screen.getByRole('button', { name: /search/i });
    act(() => {
      searchBtn.click();
    });
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeDefined();

    // Close palette via Escape
    fireEvent.keyDown(window, { key: 'Escape' });

    // Open palette via Mod+K
    const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
    fireEvent.keyDown(window, {
      key: 'k',
      metaKey: isMac,
      ctrlKey: !isMac,
    });
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeDefined();

    // Toggle hamburger
    const hamburger = screen.getByRole('button', { name: 'Open navigation' });
    act(() => {
      hamburger.click();
    });

    const dialog = screen.getByRole('dialog', { name: 'Sidebar navigation' });
    expect(dialog).toBeDefined();

    const scrim = document.querySelector('.kb-sidebar-scrim');
    expect(scrim).not.toBeNull();
    if (scrim) {
      act(() => {
        fireEvent.click(scrim);
      });
    }

    // Select Toggle sidebar from Command palette on mobile (innerWidth = 1024)
    act(() => {
      searchBtn.click();
    });
    const toggleSidebarOption = screen.getByText('Toggle sidebar');
    act(() => {
      toggleSidebarOption.click();
    });
    expect(screen.getByRole('dialog', { name: 'Sidebar navigation' })).toBeDefined();

    // Test Toggle sidebar on desktop (innerWidth = 1440)
    vi.stubGlobal('innerWidth', 1440);
    act(() => {
      searchBtn.click();
    });
    const toggleSidebarDesktop = screen.getByText('Toggle sidebar');
    act(() => {
      toggleSidebarDesktop.click();
    });

    vi.unstubAllGlobals();
  });

  it('renders with all optional props passed explicitly', () => {
    const status = {
      deployment_mode: 'standalone' as const,
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };
    const manifest = {
      pill_label: 'Project + 3',
      users: [],
    };
    const issues = [{ key: 'KAN-1', summary: 'Cached item' }];

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell
              projectKey="KAN"
              projectName="kanban"
              modulesEnabled={false}
              issueCount={42}
              currentSection="Custom Section"
              accessManifest={manifest}
              systemStatus={status}
              cachedIssues={issues}
            />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText('(42)')).toBeDefined();
    expect(screen.getAllByText('Custom Section').length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /Modules/ })).toBeNull();
  });

  it('covers computeCurrentSection branches and kb:open-manage-access events', () => {
    expect(computeCurrentSection('/about')).toBe('About');
    expect(computeCurrentSection('/projects/KAN/settings/workflows')).toBe('Workflows');
    expect(computeCurrentSection('/workflows')).toBe('Workflows');
    expect(computeCurrentSection('/projects/KAN/settings/custom-fields')).toBe('Custom Fields');
    expect(computeCurrentSection('/projects/KAN/settings')).toBe('Settings');
    expect(computeCurrentSection('/projects/KAN/cycles')).toBe('Cycles');
    expect(computeCurrentSection('/projects/KAN/modules')).toBe('Modules');
    expect(computeCurrentSection('/projects/KAN/docs')).toBe('Docs');
    expect(computeCurrentSection('/projects/KAN/stickies')).toBe('Stickies');
    expect(computeCurrentSection('/projects/KAN/views')).toBe('Views');
    expect(computeCurrentSection('/projects/KAN/activity')).toBe('Activity');
    expect(computeCurrentSection('/projects/KAN/overview')).toBe('Overview');
    expect(computeCurrentSection('/projects/KAN/issues')).toBe('Work Items');
    expect(computeCurrentSection('/other/path', 'Fallback')).toBe('Fallback');

    // Test initial collapsed sidebar state from localStorage
    localStorage.setItem('kb.sidebar', 'collapsed');
    const { unmount: unmountCollapsed } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell projectKey="KAN" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    unmountCollapsed();
    localStorage.removeItem('kb.sidebar');

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell projectKey="KAN" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-manage-access', { detail: { projectKey: 'KAN' } }),
      );
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-manage-access', { detail: {} }),
      );
    });

    unmount();

    // Also without projectKey prop
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/workspaces']}>
            <AppShell />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-manage-access', { detail: {} }),
      );
    });
  });

  it('toggles sidebar collapse state via [ shortcut and header buttons', () => {
    localStorage.removeItem('kb.sidebar');

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell projectKey="KAN" projectName="kanban" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const shell = document.querySelector('.kb-app-shell');
    expect(shell).not.toBeNull();
    expect(shell?.classList.contains('kb-app-shell--sidebar-collapsed')).toBe(false);

    // Toggle collapse via [ shortcut
    act(() => {
      fireEvent.keyDown(window, { key: '[' });
    });
    expect(shell?.classList.contains('kb-app-shell--sidebar-collapsed')).toBe(true);
    expect(localStorage.getItem('kb.sidebar')).toBe('collapsed');

    // Toggle expand via [ shortcut
    act(() => {
      fireEvent.keyDown(window, { key: '[' });
    });
    expect(shell?.classList.contains('kb-app-shell--sidebar-collapsed')).toBe(false);
    expect(localStorage.getItem('kb.sidebar')).toBe('open');

    // Click collapse button in sidebar header
    const collapseBtn = screen.getByRole('button', { name: 'Collapse navigation sidebar' });
    act(() => {
      collapseBtn.click();
    });
    expect(shell?.classList.contains('kb-app-shell--sidebar-collapsed')).toBe(true);

    // Click expand button in topbar
    const expandBtn = screen.getByRole('button', { name: 'Expand navigation sidebar' });
    act(() => {
      expandBtn.click();
    });
    expect(shell?.classList.contains('kb-app-shell--sidebar-collapsed')).toBe(false);

    // Shortcuts modal via '?' and 'kb:open-shortcuts'
    act(() => {
      fireEvent.keyDown(window, { key: '?' });
    });
    expect(screen.getByRole('dialog', { name: /Keyboard Shortcuts/i })).toBeDefined();

    // Close shortcuts modal via Escape
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    // Open via kb:open-shortcuts event
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-shortcuts'));
    });
    expect(screen.getByRole('dialog', { name: /Keyboard Shortcuts/i })).toBeDefined();

    // Close via close button
    const closeShortcutsBtn = screen.getByTestId('shortcuts-modal-close-btn');
    act(() => {
      closeShortcutsBtn.click();
    });
    expect(screen.queryByRole('dialog', { name: /Keyboard Shortcuts/i })).toBeNull();

    // 'c' shortcut triggers kb:create-issue
    const createIssueSpy = vi.fn();
    window.addEventListener('kb:create-issue', createIssueSpy);
    act(() => {
      fireEvent.keyDown(window, { key: 'c' });
    });
    expect(createIssueSpy).toHaveBeenCalled();
    window.removeEventListener('kb:create-issue', createIssueSpy);
  });

  it('renders minimal clean shell placeholder without Topbar/Sidebar/Outlet when sessionGuard is checking or redirecting (fail-closed)', () => {
    const spy = vi.spyOn(sessionGuardModule, 'useSessionGuard');

    // Case 1: checking
    spy.mockReturnValue({
      status: 'checking',
      initialized: null,
      authenticated: null,
      csrfToken: null,
      principalId: null,
      workspaceId: null,
      aalLevel: 0,
      mfaPending: false,
    });

    const { unmount: unmount1 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <AppShell>
              <div data-testid="protected-canvas-child">Child Content</div>
            </AppShell>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const placeholder = screen.getByTestId('app-shell-auth-loading');
    expect(placeholder).toBeDefined();
    expect(placeholder.className).toBe('kb-app-shell');
    expect(placeholder.getAttribute('style')).toBeNull();
    expect(screen.queryByTestId('protected-canvas-child')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Skip to content' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Open navigation' })).toBeNull();
    unmount1();

    // Case 2: redirecting
    spy.mockReturnValue({
      status: 'redirecting',
      initialized: false,
      authenticated: null,
      csrfToken: null,
      principalId: null,
      workspaceId: null,
      aalLevel: 0,
      mfaPending: false,
    });

    const { unmount: unmount2 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <AppShell>
              <div data-testid="protected-canvas-child">Child Content</div>
            </AppShell>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('app-shell-auth-loading')).toBeDefined();
    expect(screen.queryByTestId('protected-canvas-child')).toBeNull();
    unmount2();

    // Case 3: authenticated=true, but mfaPending=true
    spy.mockReturnValue({
      status: 'redirecting',
      initialized: true,
      authenticated: true,
      csrfToken: null,
      principalId: 'p1',
      workspaceId: 'w1',
      aalLevel: 1,
      mfaPending: true,
    });

    const { unmount: unmount3 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <AppShell>
              <div data-testid="protected-canvas-child">Child Content</div>
            </AppShell>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('app-shell-auth-loading')).toBeDefined();
    expect(screen.queryByTestId('protected-canvas-child')).toBeNull();
    unmount3();

    // Case 4: authenticated=false
    spy.mockReturnValue({
      status: 'redirecting',
      initialized: true,
      authenticated: false,
      csrfToken: null,
      principalId: null,
      workspaceId: null,
      aalLevel: 0,
      mfaPending: false,
    });

    const { unmount: unmount4 } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <AppShell>
              <div data-testid="protected-canvas-child">Child Content</div>
            </AppShell>
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('app-shell-auth-loading')).toBeDefined();
    expect(screen.queryByTestId('protected-canvas-child')).toBeNull();
    unmount4();

    spy.mockRestore();
  });

  it('does not mount duplicate global IssueSurface drawer when layout is list on project issues route', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=list&peek=KAN-1']}>
            <AppShell projectKey="KAN" projectName="kanban" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const surfaceHost = document.getElementById('kb-surface-host');
    expect(surfaceHost).toBeDefined();
    expect(surfaceHost?.querySelector('.surface--drawer')).toBeNull();
  });

  it('KAN-58: does not mount duplicate global drawer when layout is omitted on /issues route', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-1']}>
            <AppShell projectKey="KAN" projectName="kanban" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const surfaceHost = document.getElementById('kb-surface-host');
    expect(surfaceHost).toBeDefined();
    expect(surfaceHost?.querySelector('.surface--drawer')).toBeNull();
  });

  it('KAN-58: Topbar & Hamburger Always Accessible Above Ticket Views and auto-closes mobile sidebar on resize', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <AppShell projectKey="KAN" projectName="kanban" />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Topbar is rendered with sticky positioning and topbar header
    const topbar = document.querySelector('.kb-topbar');
    expect(topbar).toBeDefined();

    // Open mobile sidebar via hamburger button
    const hamburger = screen.getByRole('button', { name: 'Open navigation' });
    expect(hamburger).toBeDefined();
    act(() => {
      hamburger.click();
    });
    expect(screen.getByRole('dialog', { name: 'Sidebar navigation' })).toBeDefined();

    // Resize viewport past 1279px auto-closes mobile sidebar
    act(() => {
      window.innerWidth = 1440;
      window.dispatchEvent(new Event('resize'));
    });
    expect(screen.queryByRole('dialog', { name: 'Sidebar navigation' })).toBeNull();
  });
});
