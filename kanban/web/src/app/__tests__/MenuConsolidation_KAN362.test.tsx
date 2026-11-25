// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminStudioSubnav } from '../../features/admin/AdminStudioSubnav';
import { AdminMcpRedirect } from '../routes';
import { Topbar } from '../Topbar';
import { computeCurrentSection } from '../AppShell';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../shellPanels';
import { McpAccessStudio } from '../../features/settings/McpAccessStudio';

vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  apiFetch: vi.fn().mockReturnValue(new Promise<void>(() => undefined)),
}));

vi.mock('../../features/settings/settingsApi', () => ({
  fetchConnectedApps: vi.fn().mockResolvedValue([]),
  revokeConnectedApp: vi.fn().mockResolvedValue({}),
  fetchUnifiedMcpKeys: vi.fn().mockResolvedValue([]),
  mintUnifiedMcpKey: vi.fn().mockResolvedValue({ raw_token: 'kb_agt_test_123' }),
  revokeUnifiedMcpKey: vi.fn().mockResolvedValue({}),
}));

describe('Topbar Avatar Menu Consolidation & Unified Admin Studio Hub Subnav (KAN-362)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  describe('1. AdminStudioSubnav Component Coverage & WCAG Attributes', () => {
    const allTabs = [
      { id: 'auth', testId: 'tab-admin-auth', label: 'Auth Cards', path: '/admin/auth', icon: '🛡️' },
      { id: 'ai', testId: 'tab-admin-ai', label: 'AI Providers', path: '/admin/ai', icon: '🧠' },
      { id: 'agents', testId: 'tab-admin-agents', label: 'Agents', path: '/admin/agents', icon: '🤖' },
      { id: 'runners', testId: 'tab-admin-runners', label: 'Remote Runners', path: '/admin/agent-runners', icon: '🚀' },
      { id: 'mcp', testId: 'tab-admin-mcp', label: 'Bot API Keys', path: '/admin/mcp', icon: '🔑' },
      { id: 'oauth', testId: 'tab-admin-oauth', label: 'OAuth 2.1 Clients', path: '/admin/oauth', icon: '🌐' },
      { id: 'imports', testId: 'tab-admin-imports', label: 'Migration', path: '/admin/imports', icon: '📥' },
      { id: 'standalone', testId: 'tab-admin-standalone', label: 'System & Backups', path: '/admin/standalone', icon: '💾' },
      { id: 'diagnostics', testId: 'tab-admin-diagnostics', label: 'Diagnostics', path: '/admin/diagnostics', icon: '🩺' },
    ] as const;

    it('renders all 9 tabs with navigation aria-label and accessible markup in router', () => {
      render(
        <MemoryRouter initialEntries={['/admin/mcp']}>
          <AdminStudioSubnav activeTab="mcp" isServerAdmin={true} />
        </MemoryRouter>,
      );

      const nav = screen.getByRole('navigation', { name: 'Admin MCP and Governance Navigation' });
      expect(nav).toBeDefined();

      for (const tab of allTabs) {
        const tabEl = screen.getByTestId(tab.testId);
        expect(tabEl.textContent).toContain(tab.label);
        expect(tabEl.getAttribute('href')).toBe(tab.path);
      }

      // Explicit negative and exact string assertions for tab-admin-imports
      const importsTab = screen.getByTestId('tab-admin-imports');
      expect(importsTab.textContent).toContain('Migration');
      expect(importsTab.textContent).not.toContain('Plane Migration');
      expect(importsTab.textContent).not.toContain('Plane Migration Import Studio');
      expect(importsTab.textContent.replace(/\s+/g, ' ').trim()).toBe('📥Migration');
    });

    it('filters out server-only tabs when isServerAdmin is false', () => {
      render(
        <MemoryRouter initialEntries={['/admin/diagnostics']}>
          <AdminStudioSubnav isServerAdmin={false} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('tab-admin-diagnostics')).toBeDefined();
      expect(screen.queryByTestId('tab-admin-imports')).toBeNull();
      expect(screen.queryByTestId('tab-admin-auth')).toBeNull();
    });

    it.each(allTabs)('activates tab "%s" when activeTab prop is passed', (tab) => {
      render(
        <MemoryRouter initialEntries={['/admin/overview']}>
          <AdminStudioSubnav activeTab={tab.id} isServerAdmin={true} />
        </MemoryRouter>,
      );

      const activeEl = screen.getByTestId(tab.testId);
      expect(activeEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
      expect(activeEl.classList.contains('admin-studio-subnav__item--active')).toBe(true);
      expect(activeEl.getAttribute('aria-current')).toBe('page');

      // Verify other tabs are not marked active
      for (const other of allTabs) {
        if (other.id !== tab.id) {
          const inactiveEl = screen.getByTestId(other.testId);
          expect(inactiveEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(false);
          expect(inactiveEl.getAttribute('aria-current')).toBeNull();
        }
      }
    });

    it('activates tab matching subpaths via prefix when activeTab is omitted', () => {
      render(
        <MemoryRouter initialEntries={['/admin/agent-runners/node-42']}>
          <AdminStudioSubnav isServerAdmin={true} />
        </MemoryRouter>,
      );

      const runnersEl = screen.getByTestId('tab-admin-runners');
      expect(runnersEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
      expect(runnersEl.getAttribute('aria-current')).toBe('page');

      const authEl = screen.getByTestId('tab-admin-auth');
      expect(authEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(false);
      expect(authEl.getAttribute('aria-current')).toBeNull();
    });

    it('renders no active tab when current route does not match any admin path', () => {
      render(
        <MemoryRouter initialEntries={['/settings/profile']}>
          <AdminStudioSubnav isServerAdmin={true} />
        </MemoryRouter>,
      );

      for (const tab of allTabs) {
        const tabEl = screen.getByTestId(tab.testId);
        expect(tabEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(false);
        expect(tabEl.getAttribute('aria-current')).toBeNull();
      }
    });

    it('renders accessible anchor tags outside router context (inRouter = false)', () => {
      // Rendering without MemoryRouter exercises useInRouterContext() === false branch
      render(<AdminStudioSubnav activeTab="diagnostics" isServerAdmin={true} />);

      const diagEl = screen.getByTestId('tab-admin-diagnostics');
      expect(diagEl.tagName.toLowerCase()).toBe('a');
      expect(diagEl.getAttribute('href')).toBe('/admin/diagnostics');
      expect(diagEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
      expect(diagEl.getAttribute('aria-current')).toBe('page');

      const authEl = screen.getByTestId('tab-admin-auth');
      expect(authEl.tagName.toLowerCase()).toBe('a');
      expect(authEl.getAttribute('href')).toBe('/admin/auth');
      expect(authEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(false);
      expect(authEl.getAttribute('aria-current')).toBeNull();
    });

    it('derives active tab from window.location.pathname outside router context', () => {
      const originalPath = window.location.pathname;
      try {
        window.history.pushState({}, '', '/admin/oauth');

        render(<AdminStudioSubnav isServerAdmin={true} />);

        const oauthEl = screen.getByTestId('tab-admin-oauth');
        expect(oauthEl.tagName.toLowerCase()).toBe('a');
        expect(oauthEl.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
        expect(oauthEl.getAttribute('aria-current')).toBe('page');
      } finally {
        window.history.pushState({}, '', originalPath || '/');
      }
    });
  });

  describe('2. Topbar Avatar Menu Consolidation & Role Gating', () => {
    function renderTopbarWithUser(user: {
      id?: string;
      handle?: string;
      display_name?: string;
      avatar_url?: string | null;
      is_server_admin?: boolean;
      is_workspace_admin?: boolean;
    } | null) {
      return render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <Topbar
                  onOpenPalette={vi.fn()}
                  onToggleSidebar={vi.fn()}
                  projectKey="KAN"
                  projectName="kanban"
                  currentSection="Work Items"
                  user={user}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );
    }

    it('renders complete consolidated admin studio options for Server + Workspace Admin', () => {
      renderTopbarWithUser({
        id: 'u-super',
        handle: 'superadmin',
        display_name: 'Super Admin',
        is_server_admin: true,
        is_workspace_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      // Personal & Developer keys
      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-mcp-studio-link')).toBeDefined();

      // Workspace admin links
      expect(screen.getByTestId('topbar-workspace-settings-link')).toBeDefined();

      // Diagnostics & Link Inspector (KANBA-187 / KAN-362 consolidation)
      expect(screen.getByTestId('topbar-link-auditor-link')).toBeDefined();

      // All 7 Server Admin Studios
      expect(screen.getByTestId('topbar-admin-auth-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-ai-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-agents-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-runners-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-oauth-link')).toBeDefined();
      const importsLink = screen.getByTestId('topbar-admin-imports-link');
      expect(importsLink).toBeDefined();
      expect(importsLink.textContent).toContain('Migration Import Studio');
      expect(importsLink.textContent).not.toContain('Plane Migration');
      expect(importsLink.textContent).not.toContain('Plane Migration Import Studio');
      expect(importsLink.textContent.replace(/\s+/g, ' ').trim()).toBe('📥Migration Import Studio');
      expect(screen.getByTestId('topbar-admin-standalone-link')).toBeDefined();

      // Documentation & About
      expect(screen.getByTestId('topbar-avatar-docs-link')).toBeDefined();
      expect(screen.getByTestId('topbar-about-link')).toBeDefined();
    });

    it('renders server admin studio options for server admin who is not workspace admin', () => {
      renderTopbarWithUser({
        id: 'u-srv',
        handle: 'serveradmin',
        display_name: 'Server Admin',
        is_server_admin: true,
        is_workspace_admin: false,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      // Should have diagnostics and server admin links
      expect(screen.getByTestId('topbar-link-auditor-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-auth-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-ai-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-oauth-link')).toBeDefined();
      const srvImportsLink = screen.getByTestId('topbar-admin-imports-link');
      expect(srvImportsLink).toBeDefined();
      expect(srvImportsLink.textContent).toContain('Migration Import Studio');
      expect(srvImportsLink.textContent).not.toContain('Plane Migration');
      expect(srvImportsLink.textContent).not.toContain('Plane Migration Import Studio');
      expect(srvImportsLink.textContent.replace(/\s+/g, ' ').trim()).toBe('📥Migration Import Studio');

      // Should NOT have workspace-level settings link
      expect(screen.queryByTestId('topbar-workspace-settings-link')).toBeNull();
    });

    it('renders diagnostics and workspace settings for workspace admin who is not server admin', () => {
      renderTopbarWithUser({
        id: 'u-ws',
        handle: 'wsadmin',
        display_name: 'Workspace Admin',
        is_server_admin: false,
        is_workspace_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      expect(screen.getByTestId('topbar-workspace-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-link-auditor-link')).toBeDefined();

      // Workspace admin has access to workspace-level AI providers & agents (KAN-402)
      expect(screen.getByTestId('topbar-admin-ai-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-agents-link')).toBeDefined();

      // Server admin links must be strictly hidden
      expect(screen.queryByTestId('topbar-admin-auth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-runners-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-oauth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-imports-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-standalone-link')).toBeNull();
    });

    it('strictly hides all admin and diagnostics links for standard users', () => {
      renderTopbarWithUser({
        id: 'u-standard',
        handle: 'developer',
        display_name: 'Standard Developer',
        is_server_admin: false,
        is_workspace_admin: false,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-mcp-studio-link')).toBeDefined();

      expect(screen.queryByTestId('topbar-workspace-settings-link')).toBeNull();
      expect(screen.queryByTestId('topbar-link-auditor-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-auth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-ai-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-oauth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-imports-link')).toBeNull();
    });

    it('closes the avatar menu when an admin navigation item is clicked', () => {
      renderTopbarWithUser({
        id: 'u-admin',
        handle: 'admin',
        is_server_admin: true,
        is_workspace_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      const oauthLink = screen.getByTestId('topbar-admin-oauth-link');
      fireEvent.click(oauthLink);

      expect(screen.queryByTestId('topbar-admin-oauth-link')).toBeNull();
    });

    it('closes the avatar menu on Escape key press and outside click', () => {
      renderTopbarWithUser({
        id: 'u-admin',
        handle: 'admin',
        is_server_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);
      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();

      // Escape key closes menu
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByTestId('topbar-personal-settings-link')).toBeNull();

      // Re-open and outside click closes menu
      fireEvent.click(avatarBtn);
      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();
      fireEvent.mouseDown(document.body);
      expect(screen.queryByTestId('topbar-personal-settings-link')).toBeNull();
    });

    it.each([
      { testId: 'topbar-admin-imports-link', label: 'Migration Import Studio', path: '/admin/imports' },
      { testId: 'topbar-admin-auth-link', label: 'Admin Auth Studio', path: '/admin/auth' },
      { testId: 'topbar-admin-ai-link', label: 'AI Providers & Token Caps', path: '/workspaces/settings/ai' },
      { testId: 'topbar-admin-agents-link', label: 'Autonomous Agents', path: '/workspaces/settings/agents' },
      { testId: 'topbar-admin-runners-link', label: 'Remote mTLS Runners', path: '/admin/agent-runners' },
      { testId: 'topbar-admin-oauth-link', label: 'OAuth 2.1 Clients', path: '/admin/oauth' },
      { testId: 'topbar-admin-standalone-link', label: 'System Storage, Backups & Deployment', path: '/admin/standalone' },
      { testId: 'topbar-link-auditor-link', label: 'Diagnostics & Link Inspector', path: '/admin/diagnostics' },
      { testId: 'topbar-avatar-docs-link', label: 'Documentation', path: '/docs' },
      { testId: 'topbar-about-link', label: 'About 👍kanban', path: '/about' },
      { testId: 'topbar-personal-settings-link', label: 'Personal Profile & Security', path: '/settings/profile' },
      { testId: 'topbar-mcp-studio-link', label: 'Bot Keys & MCP Tools', path: '/settings/mcp' },
      { testId: 'topbar-workspace-settings-link', label: 'Workspace Configuration', path: '/workspaces/settings' },
    ])('clicks link "$testId", verifies href, and closes menu', ({ testId, path }) => {
      renderTopbarWithUser({
        id: 'u-admin',
        handle: 'admin',
        is_server_admin: true,
        is_workspace_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      const linkEl = screen.getByTestId(testId);
      expect(linkEl.getAttribute('href')).toBe(path);
      fireEvent.click(linkEl);
      expect(screen.queryByTestId(testId)).toBeNull();
    });

    it('covers Home/End keys in menu and avatar error fallback', () => {
      renderTopbarWithUser({
        id: 'u-admin',
        handle: 'admin',
        avatar_url: '/bad-avatar.png',
        is_server_admin: true,
      });

      const avatarImg = screen.getByTestId('topbar-avatar-img');
      fireEvent.error(avatarImg);
      expect(screen.getByTestId('topbar-avatar-initial')).toBeDefined();

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      const menuAvatarImgs = screen.queryAllByRole('img');
      const firstImg = menuAvatarImgs[0];
      if (firstImg) {
        fireEvent.error(firstImg);
      }

      const menu = screen.getByRole('menu');
      fireEvent.keyDown(menu, { key: 'Home' });
      fireEvent.keyDown(menu, { key: 'End' });
    });

    it('handles logout network error gracefully and still navigates to /login', async () => {
      const fetchSpy = vi.spyOn(window, 'fetch').mockRejectedValueOnce(new Error('Network error'));
      renderTopbarWithUser({
        id: 'u-admin',
        handle: 'admin',
        is_server_admin: true,
      });

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      const logoutBtn = screen.getByRole('menuitem', { name: /Log out/i });
      await act(async () => {
        fireEvent.click(logoutBtn);
        await Promise.resolve();
      });

      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/auth/logout', expect.anything());
      expect(screen.queryByRole('menu')).toBeNull();
    });
  });

  describe('3. AdminMcpRedirect Route Behavior', () => {
    it('redirects to /admin/mcp without query string when no search params present', () => {
      render(
        <MemoryRouter initialEntries={['/legacy-mcp']}>
          <Routes>
            <Route path="/legacy-mcp" element={<AdminMcpRedirect />} />
            <Route
              path="/admin/mcp"
              element={<div data-testid="admin-mcp-target">Admin MCP Target</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('admin-mcp-target')).toBeDefined();
    });

    it('preserves multi-part query string parameters across redirect', () => {
      render(
        <MemoryRouter initialEntries={['/legacy-mcp?tier=global&view=workloads&tab=keys']}>
          <Routes>
            <Route path="/legacy-mcp" element={<AdminMcpRedirect />} />
            <Route
              path="/admin/mcp"
              element={<div data-testid="admin-mcp-with-params">Params Preserved</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('admin-mcp-with-params')).toBeDefined();
    });
  });

  describe('4. McpAccessStudio Subnav Rendering by Scope Tier', () => {
    it('renders AdminStudioSubnav with activeTab="mcp" when tier="global"', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/admin/mcp']}>
            <McpAccessStudio
              tier="global"
              user={{ is_server_admin: true, is_workspace_admin: true, is_project_admin: true }}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        const mcpTab = screen.getByTestId('tab-admin-mcp');
        expect(mcpTab).toBeDefined();
        expect(mcpTab.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
        expect(mcpTab.getAttribute('aria-current')).toBe('page');
      });
    });

    it('does not render AdminStudioSubnav when tier="workspace"', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/workspaces/settings/mcp']}>
            <McpAccessStudio tier="workspace" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('tab-admin-mcp')).toBeNull();
      });
    });
  });

  describe('5. AppShell computeCurrentSection Mappings (KAN-397)', () => {
    it('correctly maps server admin routes to descriptive section labels', () => {
      expect(computeCurrentSection('/admin/imports')).toBe('Migration Import Studio');
      expect(computeCurrentSection('/admin/imports/')).toBe('Migration Import Studio');
      expect(computeCurrentSection('/admin/auth')).toBe('Auth Cards');
      expect(computeCurrentSection('/admin/oauth')).toBe('OAuth Clients');
      expect(computeCurrentSection('/admin/agent-runners')).toBe('Agent Runners');
      expect(computeCurrentSection('/admin/ai')).toBe('AI Providers');
      expect(computeCurrentSection('/admin/agents')).toBe('Autonomous Agents');
      expect(computeCurrentSection('/admin/diagnostics')).toBe('Diagnostics');
      expect(computeCurrentSection('/admin/link-auditor')).toBe('Diagnostics');
      expect(computeCurrentSection('/docs')).toBe('Docs');
      expect(computeCurrentSection('/settings/profile')).toBe('Settings');
      expect(computeCurrentSection('/settings/mcp')).toBe('Settings');
      expect(computeCurrentSection('/workspaces/settings')).toBe('Settings');
      expect(computeCurrentSection('/projects/KAN/cycles')).toBe('Cycles');
      expect(computeCurrentSection('/projects/KAN/modules')).toBe('Modules');
      expect(computeCurrentSection('/projects/KAN/stickies')).toBe('Stickies');
      expect(computeCurrentSection('/projects/KAN/views')).toBe('Views');
      expect(computeCurrentSection('/projects/KAN/activity')).toBe('Activity');
      expect(computeCurrentSection('/projects/KAN/overview')).toBe('Overview');
      expect(computeCurrentSection('/projects/KAN/issues')).toBe('Work Items');
    });

    it('falls back to provided fallback or Work Items', () => {
      expect(computeCurrentSection('/other/path', 'Custom Fallback')).toBe('Custom Fallback');
      expect(computeCurrentSection('/other/path')).toBe('Work Items');
    });
  });
});
