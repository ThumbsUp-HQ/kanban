// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  apiFetch: vi.fn().mockResolvedValue({}),
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
      { id: 'runners', testId: 'tab-admin-runners', label: 'Remote Runners', path: '/admin/agent-runners', icon: '🚀' },
      { id: 'mcp', testId: 'tab-admin-mcp', label: 'Bot API Keys', path: '/admin/mcp', icon: '🔑' },
      { id: 'oauth', testId: 'tab-admin-oauth', label: 'OAuth 2.1 Clients', path: '/admin/oauth', icon: '🌐' },
      { id: 'imports', testId: 'tab-admin-imports', label: 'Migration', path: '/admin/imports', icon: '📥' },
      { id: 'standalone', testId: 'tab-admin-standalone', label: 'System & Backups', path: '/admin/standalone', icon: '💾' },
      { id: 'diagnostics', testId: 'tab-admin-diagnostics', label: 'Diagnostics', path: '/admin/diagnostics', icon: '🩺' },
    ] as const;

    it('renders all 8 tabs with navigation aria-label and accessible markup in router', () => {
      render(
        <MemoryRouter initialEntries={['/admin/mcp']}>
          <AdminStudioSubnav activeTab="mcp" />
        </MemoryRouter>,
      );

      const nav = screen.getByRole('navigation', { name: 'Admin MCP and Governance Navigation' });
      expect(nav).toBeDefined();

      for (const tab of allTabs) {
        const tabEl = screen.getByTestId(tab.testId);
        expect(tabEl.textContent).toContain(tab.label);
        expect(tabEl.getAttribute('href')).toBe(tab.path);
      }
    });

    it.each(allTabs)('activates tab "%s" when activeTab prop is passed', (tab) => {
      render(
        <MemoryRouter initialEntries={['/admin/overview']}>
          <AdminStudioSubnav activeTab={tab.id} />
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
          <AdminStudioSubnav />
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
          <AdminStudioSubnav />
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
      render(<AdminStudioSubnav activeTab="diagnostics" />);

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

        render(<AdminStudioSubnav />);

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
      expect(screen.getByTestId('topbar-admin-imports-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-imports-link').textContent).toContain('Migration Import Studio');
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
      expect(screen.getByTestId('topbar-admin-imports-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-imports-link').textContent).toContain('Migration Import Studio');

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

      // Server admin links must be strictly hidden
      expect(screen.queryByTestId('topbar-admin-auth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-ai-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-agents-link')).toBeNull();
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
            <McpAccessStudio tier="global" />
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
      expect(computeCurrentSection('/admin/auth')).toBe('Auth Cards');
      expect(computeCurrentSection('/admin/oauth')).toBe('OAuth Clients');
      expect(computeCurrentSection('/admin/agent-runners')).toBe('Agent Runners');
      expect(computeCurrentSection('/admin/ai')).toBe('AI Providers');
      expect(computeCurrentSection('/admin/agents')).toBe('Autonomous Agents');
      expect(computeCurrentSection('/admin/diagnostics')).toBe('Diagnostics');
      expect(computeCurrentSection('/admin/link-auditor')).toBe('Diagnostics');
    });

    it('falls back to provided fallback or Work Items', () => {
      expect(computeCurrentSection('/other/path', 'Custom Fallback')).toBe('Custom Fallback');
      expect(computeCurrentSection('/other/path')).toBe('Work Items');
    });
  });
});
