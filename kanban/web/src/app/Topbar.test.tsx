import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Topbar } from './Topbar';
import { ThemeProvider } from '../theme/ThemeProvider';
import { ShellPanelsProvider } from './shellPanels';

describe('Topbar', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it('renders breadcrumb, search trigger, header pills, and avatar menu', () => {
    const onOpenPalette = vi.fn();
    const onToggleSidebar = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar
                onOpenPalette={onOpenPalette}
                onToggleSidebar={onToggleSidebar}
                projectKey="KAN"
                projectName="kanban"
                currentSection="Work Items"
                issueCount={7}
              />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Breadcrumb
    expect(screen.getByText('kanban')).toBeDefined();
    expect(screen.getByText('Work Items')).toBeDefined();
    expect(screen.getByText('(7)')).toBeDefined();

    // Search trigger
    const searchBtn = screen.getByRole('button', { name: 'Search or run command' });
    expect(searchBtn).toBeDefined();
    act(() => {
      searchBtn.click();
    });
    expect(onOpenPalette).toHaveBeenCalledTimes(1);

    // Hamburger button
    const hamburger = screen.getByRole('button', { name: 'Open navigation' });
    act(() => {
      hamburger.click();
    });
    expect(onToggleSidebar).toHaveBeenCalledTimes(1);

    // Layout switcher rendered on issues route
    expect(screen.getByRole('radiogroup', { name: 'Layout' })).toBeDefined();
  });

  it('toggles avatar menu and sets theme via radiogroup', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter>
              <Topbar />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    act(() => {
      avatarBtn.click();
    });

    const themeRadiogroup = screen.getByRole('radiogroup', { name: 'Theme' });
    expect(themeRadiogroup).toBeDefined();

    const darkRadio = screen.getByRole('radio', { name: /Dark/ });
    act(() => {
      darkRadio.click();
    });

    expect(document.documentElement.dataset.theme).toBe('dark');

    // Click inside avatarRef does not close
    act(() => {
      avatarBtn.click();
    });
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeDefined();

    act(() => {
      themeRadiogroup.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeDefined();

    // Click outside to close
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(screen.queryByRole('radiogroup', { name: 'Theme' })).toBeNull();
  });

  it('omits layout switcher on non-issues routes or when explicitly disabled', () => {
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/overview']}>
              <Topbar />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByRole('radiogroup', { name: 'Layout' })).toBeNull();
    unmount();

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar showLayoutSwitcher={false} />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByRole('radiogroup', { name: 'Layout' })).toBeNull();
  });

  it('omits layout switcher on issue detail route /projects/:key/issues/:id', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-123']}>
              <Topbar />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByRole('radiogroup', { name: 'Layout' })).toBeNull();
  });

  it('renders default breadcrumb and avatar menu with minimal props', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter>
              <Topbar />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    expect(avatarBtn).toBeDefined();
  });

  it('renders Settings & Admin links and executes Log out action in avatar menu', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(JSON.stringify({ csrf_token: 'csrf-logout-1' }), { status: 200 }),
        );
      }
      if (url.includes('/api/v1/auth/logout')) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: 'logged_out' }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    act(() => {
      avatarBtn.click();
    });

    expect(screen.getByRole('menuitem', { name: /Personal MCP Keys/ })).toBeDefined();
    expect(screen.getByRole('menuitem', { name: /Workspace MCP Keys/ })).toBeDefined();
    expect(screen.getByRole('menuitem', { name: /Admin Auth Studio/ })).toBeDefined();
    expect(screen.getByRole('menuitem', { name: /Admin MCP Keys/ })).toBeDefined();
    expect(screen.getByRole('menuitem', { name: /Standalone Status & Backup/ })).toBeDefined();

    const logoutBtn = screen.getByTestId('logout-button');
    await act(async () => {
      logoutBtn.click();
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
