import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Topbar, resolveDisplayHandle } from './Topbar';
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
    const searchBtn = screen.getByRole('button', { name: 'Search... (Cmd+K)' });
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

    fireEvent.click(avatarBtn);
    const menu = screen.getByRole('menu');
    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    fireEvent.keyDown(menu, { key: 'ArrowUp' });
    fireEvent.keyDown(menu, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
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
              <Topbar user={{ is_server_admin: true, is_workspace_admin: true }} />
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
    expect(
      screen.getByRole('menuitem', { name: /System Storage, Backups & Deployment/ }),
    ).toBeDefined();

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

  it('hides admin links in avatar menu when user is standard member', () => {
    const memberUser = {
      is_server_admin: false,
      is_workspace_admin: false,
      workspace_role: 'WORKSPACE_MEMBER',
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar user={memberUser} />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    act(() => {
      avatarBtn.click();
    });

    expect(screen.getByRole('menuitem', { name: /Personal Settings/ })).toBeDefined();
    expect(screen.getByRole('menuitem', { name: /Personal MCP Keys/ })).toBeDefined();
    expect(screen.queryByRole('menuitem', { name: /Workspace Settings/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /Workspace MCP Keys/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /Admin Auth Studio/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /Admin MCP Keys/ })).toBeNull();
    expect(
      screen.queryByRole('menuitem', { name: /System Storage, Backups & Deployment/ }),
    ).toBeNull();
  });

  it('supports keyboard navigation (ArrowDown, ArrowUp, Escape) in avatar menu', () => {
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

    const menu = screen.getByRole('menu');
    expect(menu).toBeDefined();

    // Test ArrowDown navigation
    act(() => {
      fireEvent.keyDown(menu, { key: 'ArrowDown' });
    });

    // Test ArrowUp navigation
    act(() => {
      fireEvent.keyDown(menu, { key: 'ArrowUp' });
    });

    // Test Escape to close
    act(() => {
      fireEvent.keyDown(menu, { key: 'Escape' });
    });

    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('closes avatar menu when clicking navigation links or clicking outside', () => {
    const adminUser = {
      is_server_admin: true,
      is_workspace_admin: true,
      workspace_role: 'WORKSPACE_ADMIN',
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar user={adminUser} />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });

    // Open and click Personal Settings link
    act(() => {
      avatarBtn.click();
    });
    const personalSettingsLink = screen.getByRole('menuitem', { name: /Personal Settings/ });
    act(() => {
      personalSettingsLink.click();
    });
    expect(screen.queryByRole('menu')).toBeNull();

    // Open and click Workspace Settings link
    act(() => {
      avatarBtn.click();
    });
    const workspaceSettingsLink = screen.getByRole('menuitem', { name: /Workspace Settings/ });
    act(() => {
      workspaceSettingsLink.click();
    });
    expect(screen.queryByRole('menu')).toBeNull();

    // Open and click Admin Auth Studio link
    act(() => {
      avatarBtn.click();
    });
    const adminAuthLink = screen.getByRole('menuitem', { name: /Admin Auth Studio/ });
    act(() => {
      adminAuthLink.click();
    });
    expect(screen.queryByRole('menu')).toBeNull();

    // Open and click outside on document body
    act(() => {
      avatarBtn.click();
    });
    expect(screen.getByRole('menu')).toBeDefined();
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('supports ArrowDown and ArrowUp keyboard navigation in avatar menu', () => {
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

    const menu = screen.getByRole('menu');
    expect(menu).toBeDefined();

    // ArrowDown moves focus
    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    fireEvent.keyDown(menu, { key: 'ArrowDown' });

    // ArrowUp moves focus backward
    fireEvent.keyDown(menu, { key: 'ArrowUp' });

    // Escape closes menu
    fireEvent.keyDown(menu, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders avatar image with fallback alt and handles logout network failure', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockRejectedValue(new Error('Logout network drop'));

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar
                user={{
                  avatar_url: '/avatars/custom.png',
                  display_name: null,
                }}
              />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Image alt fallback when display_name is empty
    const avatarImg = screen.getByAltText('User avatar');
    expect(avatarImg).toBeDefined();

    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    act(() => {
      avatarBtn.click();
    });

    const logoutBtn = screen.getByRole('menuitem', { name: /Log out/i });
    await act(async () => {
      logoutBtn.click();
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/auth/logout', expect.anything());
    expect(screen.queryByRole('menu')).toBeNull();
  });

  describe('resolveDisplayHandle and user profile rendering (KANBA-210)', () => {
    it('normalizes handles, removes double-@ prefixes, and avoids leaking UUIDs', () => {
      // Normal handle
      expect(resolveDisplayHandle({ handle: 'johndoe' })).toBe('@johndoe');
      // Single @
      expect(resolveDisplayHandle({ handle: '@johndoe' })).toBe('@johndoe');
      // Double @@
      expect(resolveDisplayHandle({ handle: '@@member' })).toBe('@member');
      // Raw short UUID handle falls back to display name
      expect(
        resolveDisplayHandle({
          handle: '01a1ede4',
          display_name: 'Audit Guest',
        }),
      ).toBe('@audit.guest');
      // Raw UUID handle with @ prefix falls back to email prefix
      expect(
        resolveDisplayHandle({
          handle: '@01a1ede4',
          display_name: null,
          email: 'guest@audit.local',
        }),
      ).toBe('@guest');
      // Raw full UUID handle falls back to @user if no other info
      expect(
        resolveDisplayHandle({
          handle: '01a1ede4-1234-5678-9abc-def012345678',
        }),
      ).toBe('@user');
      // Empty input
      expect(resolveDisplayHandle(null)).toBe('');
    });

    it('renders user avatar img with testid and user profile card in menu', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar
                  user={{
                    id: 'usr-1',
                    handle: '@@paranoiac.sec',
                    display_name: 'Paranoiac Architect',
                    email: 'sec@example.com',
                    avatar_url: '/uploads/avatars/user1.webp',
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      const avatarImg = screen.getByTestId('topbar-avatar-img');
      expect(avatarImg).toBeDefined();
      expect(avatarImg.getAttribute('src')).toBe('/uploads/avatars/user1.webp');

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      act(() => {
        avatarBtn.click();
      });

      const profileCard = screen.getByTestId('topbar-user-profile');
      expect(profileCard).toBeDefined();
      expect(screen.getByTestId('topbar-user-name').textContent).toBe('Paranoiac Architect');
      expect(screen.getByTestId('topbar-user-handle').textContent).toBe('@paranoiac.sec');
    });

    it('renders fallback initial when avatar_url is missing', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar
                  user={{
                    id: 'usr-2',
                    display_name: 'Bob Ross',
                    email: 'bob@example.com',
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      const initialEl = screen.getByTestId('topbar-avatar-initial');
      expect(initialEl.textContent).toBe('B');
      expect(screen.queryByTestId('topbar-avatar-img')).toBeNull();
    });

    it('covers clicking personal, workspace, admin MCP and storage links in avatar menu', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar
                  user={{
                    id: 'usr-admin',
                    display_name: 'Admin User',
                    is_server_admin: true,
                    is_workspace_admin: true,
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      act(() => {
        avatarBtn.click();
      });

      const personalMcp = screen.getByText('Personal MCP Keys');
      act(() => {
        personalMcp.click();
      });

      act(() => {
        avatarBtn.click();
      });

      const wsMcp = screen.getByText('Workspace MCP Keys');
      act(() => {
        wsMcp.click();
      });

      act(() => {
        avatarBtn.click();
      });

      const adminMcp = screen.getByText('Admin MCP Keys');
      act(() => {
        adminMcp.click();
      });

      act(() => {
        avatarBtn.click();
      });

      const storage = screen.getByText('System Storage, Backups & Deployment');
      act(() => {
        storage.click();
      });
    });

    it('covers resolveDisplayHandle edge branches and empty user fallbacks', () => {
      expect(resolveDisplayHandle(null)).toBe('');
      expect(resolveDisplayHandle(undefined)).toBe('');

      // Handle with raw @@@
      expect(resolveDisplayHandle({ handle: '@@@' })).toBe('@user');

      // UUID handle falls through to display name
      expect(
        resolveDisplayHandle({
          handle: '01931234-5678-7000-8000-000000000001',
          display_name: '   ',
          email: '01931234-5678-7000-8000-000000000001@example.com',
          id: 'dev-user-id',
        }),
      ).toBe('@dev-user-id');

      // UUID id fallback
      expect(
        resolveDisplayHandle({
          id: '01931234-5678-7000-8000-000000000001',
        }),
      ).toBe('@user');

      // Empty id fallback
      expect(
        resolveDisplayHandle({
          id: '',
        }),
      ).toBe('@user');
    });

    it('covers avatar initial fallback A when display_name and email are empty', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar
                  user={{
                    id: 'u-empty',
                    email: '',
                    display_name: '',
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      expect(avatarBtn.textContent).toContain('A');

      // Open menu and test ArrowUp / ArrowDown navigation
      act(() => {
        avatarBtn.click();
      });
      const menu = screen.getByRole('menu');
      fireEvent.keyDown(menu, { key: 'ArrowDown' });
      fireEvent.keyDown(menu, { key: 'ArrowUp' });
    });
  });
});
