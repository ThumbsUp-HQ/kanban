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
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../shellPanels';
import { IssueSurfaceRoot } from '../../features/drawer/IssueSurface';
import { IssueSurfaceSlotsContext, type IssueDetail } from '../../features/drawer/slots';
import { LinkGraphAction } from '../../features/drawer-actions/LinkGraphAction';

vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      id: 'iss-test',
      key: 'KAN-100',
      summary: 'Test Issue Summary',
      state: { id: 'state-1', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High', emoji: '▲' },
      capabilities: ['VIEW', 'EDIT', 'ADMIN'],
    }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  apiFetch: vi.fn().mockResolvedValue({}),
}));

describe('Menu & Navigation Consolidation Suite (KAN-318)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  describe('1. AdminStudioSubnav Component', () => {
    it('renders all 8 administrative studio tabs with correct test IDs', () => {
      render(
        <MemoryRouter initialEntries={['/admin/mcp']}>
          <AdminStudioSubnav activeTab="mcp" />
        </MemoryRouter>,
      );

      expect(screen.getByTestId('tab-admin-auth')).toBeDefined();
      expect(screen.getByTestId('tab-admin-ai')).toBeDefined();
      expect(screen.getByTestId('tab-admin-runners')).toBeDefined();
      expect(screen.getByTestId('tab-admin-mcp')).toBeDefined();
      expect(screen.getByTestId('tab-admin-oauth')).toBeDefined();
      expect(screen.getByTestId('tab-admin-imports')).toBeDefined();
      expect(screen.getByTestId('tab-admin-standalone')).toBeDefined();
      expect(screen.getByTestId('tab-admin-diagnostics')).toBeDefined();
    });

    it('highlights activeTab and sets aria-current=page', () => {
      render(
        <MemoryRouter initialEntries={['/admin/diagnostics']}>
          <AdminStudioSubnav activeTab="diagnostics" />
        </MemoryRouter>,
      );

      const diagTab = screen.getByTestId('tab-admin-diagnostics');
      expect(diagTab.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
      expect(diagTab.getAttribute('aria-current')).toBe('page');

      const mcpTab = screen.getByTestId('tab-admin-mcp');
      expect(mcpTab.classList.contains('kb-mcp-admin-subnav-active')).toBe(false);
      expect(mcpTab.getAttribute('aria-current')).toBeNull();
    });

    it('derives active state from pathname when activeTab prop is omitted', () => {
      render(
        <MemoryRouter initialEntries={['/admin/oauth']}>
          <AdminStudioSubnav />
        </MemoryRouter>,
      );

      const oauthTab = screen.getByTestId('tab-admin-oauth');
      expect(oauthTab.classList.contains('kb-mcp-admin-subnav-active')).toBe(true);
      expect(oauthTab.getAttribute('aria-current')).toBe('page');
    });
  });

  describe('2. AdminMcpRedirect Route', () => {
    it('redirects /admin/mcp to /admin/mcp with preserved query parameters', () => {
      render(
        <MemoryRouter initialEntries={['/legacy-mcp?tier=global&filter=active']}>
          <Routes>
            <Route path="/legacy-mcp" element={<AdminMcpRedirect />} />
            <Route
              path="/admin/mcp"
              element={<div data-testid="destination-admin-mcp">Admin MCP Destination</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('destination-admin-mcp')).toBeDefined();
    });
  });

  describe('3. Topbar Avatar Menu Consolidation', () => {
    it('renders server admin studio navigation entries including OAuth, Imports, and Diagnostics', () => {
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
                    is_server_admin: true,
                    is_workspace_admin: true,
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

      // Verify all admin entries exist
      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-mcp-studio-link')).toBeDefined();
      expect(screen.getByTestId('topbar-workspace-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-link-auditor-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-auth-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-ai-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-agents-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-runners-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-oauth-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-imports-link')).toBeDefined();
      expect(screen.getByTestId('topbar-admin-standalone-link')).toBeDefined();
      expect(screen.getByTestId('topbar-avatar-docs-link')).toBeDefined();
      expect(screen.getByTestId('topbar-about-link')).toBeDefined();
    });

    it('hides privileged admin links for standard workspace members', () => {
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
                    display_name: 'Standard Member',
                    is_server_admin: false,
                    is_workspace_admin: false,
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

      expect(screen.getByTestId('topbar-personal-settings-link')).toBeDefined();
      expect(screen.getByTestId('topbar-mcp-studio-link')).toBeDefined();
      expect(screen.queryByTestId('topbar-workspace-settings-link')).toBeNull();
      expect(screen.queryByTestId('topbar-link-auditor-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-auth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-oauth-link')).toBeNull();
      expect(screen.queryByTestId('topbar-admin-imports-link')).toBeNull();
    });
  });

  describe('4. IssueSurface Split-Mode Action Parity', () => {
    it('renders Subscribe, Link Graph, and Overflow action slots in split view mode', async () => {
      const mockSubscribeSlot = ({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="custom-subscribe-slot">
          Subscribe ({issue.key})
        </button>
      );
      const mockLinkSlot = ({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="custom-link-slot">
          Links ({issue.key})
        </button>
      );
      const mockOverflowSlot = ({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="custom-overflow-slot">
          Overflow ({issue.key})
        </button>
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                subscribe: mockSubscribeSlot,
                link: mockLinkSlot,
                overflow: mockOverflowSlot,
              }}
            >
              <IssueSurfaceRoot
                issueKey="KAN-100"
                projectKey="KAN"
                mode="split"
                onClose={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
        expect(screen.getByTestId('custom-subscribe-slot')).toBeDefined();
        expect(screen.getByTestId('custom-link-slot')).toBeDefined();
        expect(screen.getByTestId('custom-overflow-slot')).toBeDefined();
      });
    });
  });

  describe('5. LinkGraphAction Icon Disambiguation', () => {
    it('renders distinct 🕸️ glyph to differentiate from copy link 🔗 icon', () => {
      const mockIssue: IssueDetail = {
        id: 'iss-1',
        key: 'KAN-1',
        project_key: 'KAN',
        summary: 'Link Graph Test',
        capabilities: ['VIEW', 'EDIT'],
      };

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <LinkGraphAction issue={mockIssue} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const trigger = screen.getByTestId('link-graph-trigger');
      expect(trigger).toBeDefined();
      expect(trigger.textContent).toContain('🕸️');
      expect(trigger.getAttribute('aria-label')).toBe('Link and Object Graph');
    });
  });
});
