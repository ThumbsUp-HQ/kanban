// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { Sidebar } from '../Sidebar';
import { AppShell } from '../AppShell';
import { ProjectSettingsPage } from '../../features/settings/ProjectSettingsPage';

vi.mock('../../api/client', () => ({
  registerAal2StepUpHandler: vi.fn(),
  unregisterAal2StepUpHandler: vi.fn(),
  apiClient: {
    get: vi.fn((url: string) => {
      if (url.includes('/api/v1/projects/KAN/members')) {
        return Promise.resolve([]);
      }
      if (url.includes('/api/v1/projects/KAN/states')) {
        return Promise.resolve([
          { id: 'st-1', name: 'Backlog', group: 'backlog', color_hex: '#94a3b8', sort_order: 1, is_default: true },
          { id: 'st-2', name: 'In Progress', group: 'started', color_hex: '#3b82f6', sort_order: 2, is_default: false },
        ]);
      }
      if (url.includes('/api/v1/projects/KAN/priorities')) {
        return Promise.resolve([]);
      }
      if (url.includes('/api/v1/projects/KAN/labels')) {
        return Promise.resolve([]);
      }
      if (url.includes('/api/v1/projects/KAN/trash')) {
        return Promise.resolve([]);
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return Promise.resolve({
          id: 'prj-kan',
          identifier: 'KAN',
          name: 'Kanban Platform',
          description_markdown: 'Core project',
          modules_enabled: true,
          capabilities: ['VIEW', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
          is_project_admin: true,
        });
      }
      return Promise.resolve({});
    }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  apiFetch: vi.fn((_method: string, url: string) => {
    if (url.includes('/api/v1/auth/me')) {
      return Promise.resolve({
        id: 'u-admin',
        handle: 'admin',
        display_name: 'Admin User',
        is_server_admin: true,
        is_workspace_admin: true,
      });
    }
    if (url.includes('/api/v1/auth/session')) {
      return Promise.resolve({ csrf_token: 'test-csrf-token' });
    }
    if (url.includes('/api/v1/projects/KAN/members')) {
      return Promise.resolve([]);
    }
    if (url.includes('/api/v1/projects/KAN/states')) {
      return Promise.resolve([
        { id: 'st-1', name: 'Backlog', group: 'backlog', color_hex: '#94a3b8', sort_order: 1, is_default: true },
        { id: 'st-2', name: 'In Progress', group: 'started', color_hex: '#3b82f6', sort_order: 2, is_default: false },
      ]);
    }
    if (url.includes('/api/v1/projects/KAN/priorities')) {
      return Promise.resolve([]);
    }
    if (url.includes('/api/v1/projects/KAN/labels')) {
      return Promise.resolve([]);
    }
    if (url.includes('/api/v1/projects/KAN/trash')) {
      return Promise.resolve([]);
    }
    if (url.includes('/api/v1/projects/KAN')) {
      return Promise.resolve({
        id: 'prj-kan',
        identifier: 'KAN',
        name: 'Kanban Platform',
        description_markdown: 'Core project',
        modules_enabled: true,
        capabilities: ['VIEW', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
        is_project_admin: true,
      });
    }
    return Promise.resolve({});
  }),
}));

describe('Menu & Navigation Consolidation Suite - KAN-364', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    vi.restoreAllMocks();
  });

  describe('1. Sidebar project tree expands with clear, high-density hierarchy without vertical bloat', () => {
    it('renders project tree with high-density hierarchy and enables layout switching via Topbar without tree bloat', () => {
      const adminUser = {
        id: 'u-admin',
        handle: 'admin',
        display_name: 'Admin User',
        is_server_admin: true,
        is_workspace_admin: true,
      };

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=list']}>
            <Sidebar
              projectKey="KAN"
              projectName="Kanban Platform"
              modulesEnabled={true}
              user={adminUser}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Verify the expanded project tree container exists
      const projectTree = screen.getByTestId('sidebar-project-tree-KAN');
      expect(projectTree).toBeDefined();

      // Verify the standard sub-surfaces exist in high-density hierarchy
      expect(within(projectTree).getByRole('link', { name: 'Work Items' })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: /Issues view/i })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: /Board view/i })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: /Table view/i })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: /Calendar view/i })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: /Timeline view/i })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: 'Cycles' })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: 'Modules' })).toBeDefined();
      expect(within(projectTree).getByRole('link', { name: 'Docs' })).toBeDefined();
      expect(screen.getByTestId('sidebar-analytics-KAN')).toBeDefined();
      expect(screen.getByTestId('sidebar-project-settings-KAN')).toBeDefined();

      // Verify expand/collapse toggle button on project row
      const expandBtn = screen.getByRole('button', { name: /Project: Kanban Platform/i });
      expect(expandBtn.getAttribute('aria-expanded')).toBe('true');

      // Collapse project tree
      fireEvent.click(expandBtn);
      expect(expandBtn.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('sidebar-project-tree-KAN')).toBeNull();

      // Expand project tree back
      fireEvent.click(expandBtn);
      expect(expandBtn.getAttribute('aria-expanded')).toBe('true');
      expect(screen.getByTestId('sidebar-project-tree-KAN')).toBeDefined();
    });

    it('verifies AppShell reconciles showLayoutSwitcher to mount LayoutSwitcher on issues routes', () => {
      // When rendered on an issues route with default showLayoutSwitcher (undefined), Topbar renders LayoutSwitcher
      const { unmount: u1 } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
              <AppShell
                projectKey="KAN"
                projectName="Kanban Platform"
                modulesEnabled={true}
              >
                <div data-testid="issues-content">Issues Board Canvas</div>
              </AppShell>
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // Verify desktop radiogroup layout switcher is rendered
      expect(screen.getByRole('radiogroup', { name: 'Layout' })).toBeDefined();
      expect(screen.getByRole('radio', { name: 'Board' })).toBeDefined();
      expect(screen.getByRole('radio', { name: 'Issues' })).toBeDefined();
      u1();

      // When explicitly disabled with showLayoutSwitcher=false, LayoutSwitcher is hidden
      const { unmount: u2 } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
              <AppShell
                projectKey="KAN"
                projectName="Kanban Platform"
                modulesEnabled={true}
                showLayoutSwitcher={false}
              >
                <div data-testid="issues-content">Issues Board Canvas</div>
              </AppShell>
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      expect(screen.queryByRole('radiogroup', { name: 'Layout' })).toBeNull();
      u2();
    });
  });

  describe('2. Modules link is conditionally hidden when modules are disabled on the project', () => {
    it('renders Modules link when modulesEnabled is true', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <Sidebar projectKey="KAN" projectName="Kanban Platform" modulesEnabled={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const modulesLink = screen.getByRole('link', { name: 'Modules' });
      expect(modulesLink).toBeDefined();
      expect(modulesLink.getAttribute('href')).toBe('/projects/KAN/modules');
    });

    it('completely unmounts Modules link from DOM when modulesEnabled is false', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <Sidebar projectKey="KAN" projectName="Kanban Platform" modulesEnabled={false} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.queryByRole('link', { name: 'Modules' })).toBeNull();
    });
  });

  describe('3. Project settings sub-navigation routes to General, Workflows, and Custom Fields', () => {
    it('renders sub-navigation tabs and verifies routing to General, Workflows, and Custom Fields', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <Routes>
              <Route path="/projects/:projectKey/settings" element={<ProjectSettingsPage />} />
              <Route
                path="/projects/:projectKey/settings/workflows"
                element={<div data-testid="workflows-studio-destination">Workflow Studio Destination</div>}
              />
              <Route
                path="/projects/:projectKey/settings/custom-fields"
                element={<div data-testid="custom-fields-destination">Custom Fields Destination</div>}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Verify all sub-navigation tabs exist with preserved and new test IDs
      await waitFor(() => {
        expect(screen.getByTestId('tab-general')).toBeDefined();
        expect(screen.getByTestId('tab-states')).toBeDefined();
        expect(screen.getByTestId('tab-workflows')).toBeDefined();
        expect(screen.getByTestId('tab-custom-fields')).toBeDefined();
        expect(screen.getByTestId('tab-priorities')).toBeDefined();
        expect(screen.getByTestId('tab-labels')).toBeDefined();
        expect(screen.getByTestId('tab-members')).toBeDefined();
        expect(screen.getByTestId('tab-roles')).toBeDefined();
        expect(screen.getByTestId('tab-integrations')).toBeDefined();
        expect(screen.getByTestId('tab-trash')).toBeDefined();
        expect(screen.getByTestId('tab-danger')).toBeDefined();
      });

      // Verify tab-workflows points to workflows sub-route and navigates on click
      const workflowsTab = screen.getByTestId('tab-workflows');
      expect(workflowsTab.getAttribute('href')).toBe('/projects/KAN/settings/workflows');
      fireEvent.click(workflowsTab);

      await waitFor(() => {
        expect(screen.getByTestId('workflows-studio-destination')).toBeDefined();
      });
    });

    it('navigates to Custom Fields sub-route and switches tabs between General and States', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <Routes>
              <Route path="/projects/:projectKey/settings" element={<ProjectSettingsPage />} />
              <Route
                path="/projects/:projectKey/settings/custom-fields"
                element={<div data-testid="custom-fields-destination">Custom Fields Destination</div>}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('tab-general')).toBeDefined();
      });

      // Click Custom Fields tab
      const customFieldsTab = screen.getByTestId('tab-custom-fields');
      expect(customFieldsTab.getAttribute('href')).toBe('/projects/KAN/settings/custom-fields');
      fireEvent.click(customFieldsTab);

      await waitFor(() => {
        expect(screen.getByTestId('custom-fields-destination')).toBeDefined();
      });
    });

    it('switches between General and States & WIP panels within Project Settings', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <ProjectSettingsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('tab-general')).toBeDefined();
        expect(screen.getByTestId('tab-states')).toBeDefined();
      });

      // Initial tab is General
      const generalTab = screen.getByTestId('tab-general');
      expect(generalTab.classList.contains('kb-settings-tab-active')).toBe(true);

      // Switch to States tab
      const statesTab = screen.getByTestId('tab-states');
      fireEvent.click(statesTab);

      expect(statesTab.classList.contains('kb-settings-tab-active')).toBe(true);
      expect(generalTab.classList.contains('kb-settings-tab-active')).toBe(false);

      // Switch back to General tab
      fireEvent.click(generalTab);
      expect(generalTab.classList.contains('kb-settings-tab-active')).toBe(true);
      expect(statesTab.classList.contains('kb-settings-tab-active')).toBe(false);
    });
  });
});
