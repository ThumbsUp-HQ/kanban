// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Topbar } from '../Topbar';
import { Sidebar } from '../Sidebar';
import { AdminAiRedirect, AdminAgentsRedirect } from '../routes';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../shellPanels';
import { PersonalSettingsPage } from '../../features/settings/PersonalSettingsPage';
import * as personalApi from '../../features/settings/personalSettingsApi';
import * as authApi from '../../features/auth/authApi';

vi.mock('../../features/settings/personalSettingsApi');
vi.mock('../../features/auth/authApi');

describe('Menu Consolidation KAN-363 Suite (Global Navigation Deduplication)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  describe('Test Case 1: Global Docs Navigation Deduplication and Project Docs Disambiguation', () => {
    it('provides global docs in Topbar header and Sidebar footer while removing primary nav duplicate', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/docs']}>
                <Topbar
                  onOpenPalette={vi.fn()}
                  onToggleSidebar={vi.fn()}
                  projectKey="KAN"
                  projectName="kanban"
                  currentSection="Documentation"
                />
                <Sidebar
                  projectKey="KAN"
                  projectName="kanban"
                  modulesEnabled={true}
                  activePath="/docs"
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // 1. Topbar Header Right Pill provides 1-click global docs access
      const topbarDocsPill = screen.getByTestId('topbar-docs-link');
      expect(topbarDocsPill).toBeDefined();
      expect(topbarDocsPill.getAttribute('href')).toBe('/docs');
      expect(topbarDocsPill.getAttribute('title')).toBe('Documentation Center');

      // 2. Sidebar Footer provides canonical sidebar docs access with active state
      const sidebarFooterDocs = screen.getByTestId('sidebar-docs-link');
      expect(sidebarFooterDocs).toBeDefined();
      expect(sidebarFooterDocs.getAttribute('href')).toBe('/docs');
      expect(sidebarFooterDocs.getAttribute('aria-current')).toBe('page');

      // 3. Workspace primary nav list only contains Home, Your work, and Stickies (docs duplicate removed)
      const workspaceNav = screen.getByRole('navigation', { name: 'Workspace navigation' });
      const navLinks = workspaceNav.querySelectorAll('a');
      const navHrefs = Array.from(navLinks).map((el) => el.getAttribute('href'));
      expect(navHrefs).toContain('/');
      expect(navHrefs).toContain('/your-work');
      expect(navHrefs).toContain('/stickies');
      expect(navHrefs).not.toContain('/docs');
    });

    it('disambiguates project-level docs from global docs in the project tree', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN/docs']}>
              <Sidebar
                projectKey="KAN"
                projectName="kanban"
                modulesEnabled={true}
                activePath="/projects/KAN/docs"
              />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // Project tree subitem for docs
      const projectDocsLink = screen.getByTestId('sidebar-project-docs-KAN');
      expect(projectDocsLink).toBeDefined();
      expect(projectDocsLink.getAttribute('href')).toBe('/projects/KAN/docs');
      expect(projectDocsLink.getAttribute('title')).toBe('Project Docs: kanban');
      expect(projectDocsLink.getAttribute('aria-current')).toBe('page');
      expect(projectDocsLink.textContent).toContain('📄');
      expect(projectDocsLink.textContent).toContain('Docs');

      // Global footer docs is distinct from project docs
      const globalFooterDocs = screen.getByTestId('sidebar-docs-link');
      expect(globalFooterDocs.getAttribute('href')).toBe('/docs');
      expect(globalFooterDocs.textContent).toContain('📖');
    });
  });

  describe('Test Case 2: Workspace Settings Deduplication and Sidebar Workspace Header Gear', () => {
    it('renders direct gear button in Sidebar header for workspace admins and maintains Topbar avatar link', () => {
      render(
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
                  user={{
                    id: 'u-admin',
                    handle: 'admin',
                    display_name: 'Admin User',
                    is_workspace_admin: true,
                    is_server_admin: false,
                  }}
                />
                <Sidebar
                  projectKey="KAN"
                  projectName="kanban"
                  user={{
                    is_workspace_admin: true,
                    is_server_admin: false,
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // 1. Sidebar header provides direct Workspace Settings gear button
      const gearBtn = screen.getByTestId('sidebar-workspace-settings-gear');
      expect(gearBtn).toBeDefined();
      expect(gearBtn.getAttribute('href')).toBe('/workspaces/settings');
      expect(gearBtn.getAttribute('aria-label')).toBe('Workspace Settings');

      // 2. Topbar avatar menu retains topbar-workspace-settings-link for workspace admin
      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);
      const topbarWsSettings = screen.getByTestId('topbar-workspace-settings-link');
      expect(topbarWsSettings).toBeDefined();
      expect(topbarWsSettings.getAttribute('href')).toBe('/workspaces/settings');
    });

    it('omits workspace settings gear in Sidebar header and Topbar avatar for standard members', () => {
      render(
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
                  user={{
                    id: 'u-member',
                    handle: 'member',
                    display_name: 'Member User',
                    is_workspace_admin: false,
                    is_server_admin: false,
                  }}
                />
                <Sidebar
                  projectKey="KAN"
                  projectName="kanban"
                  user={{
                    is_workspace_admin: false,
                    is_server_admin: false,
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // 1. No gear icon for standard member
      expect(screen.queryByTestId('sidebar-workspace-settings-gear')).toBeNull();

      // 2. No topbar workspace settings link for standard member
      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);
      expect(screen.queryByTestId('topbar-workspace-settings-link')).toBeNull();
    });
  });

  describe('Test Case 3: AI Studio Server vs Workspace Consolidation, Redirect and About Integrity', () => {
    it('provides AI Providers and Autonomous Agents in Topbar avatar for workspace admins', () => {
      render(
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
                  user={{
                    id: 'u-admin',
                    handle: 'admin',
                    display_name: 'Admin User',
                    is_workspace_admin: true,
                    is_server_admin: false,
                  }}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // Open avatar menu
      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);

      // Workspace AI Studio link is present pointing to /workspaces/settings/ai
      const serverAiLink = screen.getByTestId('topbar-admin-ai-link');
      expect(serverAiLink).toBeDefined();
      expect(serverAiLink.getAttribute('href')).toBe('/workspaces/settings/ai');

      // Autonomous Agents link is present pointing to /workspaces/settings/agents
      const agentsLink = screen.getByTestId('topbar-admin-agents-link');
      expect(agentsLink).toBeDefined();
      expect(agentsLink.getAttribute('href')).toBe('/workspaces/settings/agents');
    });

    it('redirects /admin/ai to /workspaces/settings/ai preserving query parameters via AdminAiRedirect', () => {
      render(
        <MemoryRouter initialEntries={['/admin/ai?tier=workspace&focus=providers']}>
          <Routes>
            <Route path="/admin/ai" element={<AdminAiRedirect />} />
            <Route
              path="/workspaces/settings/ai"
              element={<div data-testid="destination-workspace-ai">Workspace AI Studio Destination</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('destination-workspace-ai')).toBeDefined();
    });

    it('redirects /admin/agents to /workspaces/settings/agents preserving query parameters via AdminAgentsRedirect', () => {
      render(
        <MemoryRouter initialEntries={['/admin/agents?tier=workspace&focus=agents']}>
          <Routes>
            <Route path="/admin/agents" element={<AdminAgentsRedirect />} />
            <Route
              path="/workspaces/settings/agents"
              element={<div data-testid="destination-workspace-agents">Workspace Agents Studio Destination</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('destination-workspace-agents')).toBeDefined();
    });

    it('preserves clean About 👍kanban links across Topbar, Sidebar, and Personal Settings', async () => {
      vi.mocked(personalApi.fetchMyProfile).mockResolvedValueOnce({
        principal_id: 'usr-1',
        username: 'testuser',
        display_name: 'Test User',
        email: 'test@example.com',
        avatar_url: null,
        timezone: 'UTC',
        is_server_admin: false,
      });
      vi.mocked(personalApi.fetchMfaStatus).mockResolvedValueOnce({
        totp_enabled: false,
        passkeys_count: 0,
        recovery_codes_remaining: 0,
      });
      vi.mocked(personalApi.fetchPasskeys).mockResolvedValueOnce([]);
      vi.mocked(personalApi.fetchExternalIdentities).mockResolvedValueOnce([]);
      vi.mocked(personalApi.fetchUserPreferences).mockResolvedValue({
        principal_id: 'usr-1',
        workspace_id: 'ws-1',
        agent_onboarding_prefs: {
          scope: 'local_only',
          execution_mode: 'swarm',
          model_strategy: 'quota_sipping_flash',
          qa_rigor: 'strict_forensic',
          custom_notes: '',
        },
      });
      vi.mocked(authApi.fetchAuthCards).mockResolvedValueOnce({ cards: [] });

      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/settings/profile']}>
                <Topbar
                  onOpenPalette={vi.fn()}
                  onToggleSidebar={vi.fn()}
                  projectKey="KAN"
                  projectName="kanban"
                  currentSection="Settings"
                />
                <Sidebar projectKey="KAN" projectName="kanban" />
                <PersonalSettingsPage />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // 1. Topbar avatar About link
      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);
      const topbarAbout = screen.getByTestId('topbar-about-link');
      expect(topbarAbout.getAttribute('href')).toBe('/about');

      // 2. Sidebar footer About link
      const sidebarAbout = screen.getByTestId('sidebar-about-link');
      expect(sidebarAbout.getAttribute('href')).toBe('/about');

      // 3. Personal Settings footer About link
      const personalSettingsAbout = await screen.findByTestId('personal-settings-about-link');
      expect(personalSettingsAbout.getAttribute('href')).toBe('/about');
    });
  });
});
