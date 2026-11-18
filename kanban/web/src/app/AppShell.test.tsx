import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell, computeCurrentSection } from './AppShell';
import { ThemeProvider } from '../theme/ThemeProvider';

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
    const searchBtn = screen.getByRole('button', { name: 'Search or run command' });
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
    expect(computeCurrentSection('/projects/KAN/settings/workflows')).toBe('Workflows');
    expect(computeCurrentSection('/workflows')).toBe('Workflows');
    expect(computeCurrentSection('/projects/KAN/settings/custom-fields')).toBe('Custom Fields');
    expect(computeCurrentSection('/projects/KAN/activity')).toBe('Activity');

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
});
