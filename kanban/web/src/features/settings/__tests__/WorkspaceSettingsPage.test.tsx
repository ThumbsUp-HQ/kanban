// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { WorkspaceSettingsPage } from '../WorkspaceSettingsPage';
import * as clientModule from '../../../api/client';

describe('WorkspaceSettingsPage (KANBA-202)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/workspaces/settings']}>
          <WorkspaceSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('renders workspace settings page and updates workspace name and slug', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return {
          id: 'user-admin',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'SERVER_ADMIN',
        };
      }
      if (url.includes('/api/v1/workspaces/current') || url.includes('/api/v1/workspaces/ws-1')) {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
        };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
          default_project_visibility: 'workspace',
          session_idle_timeout_min: 120,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
        };
      }
      if (url.includes('/api/v1/workspaces') && m === 'GET') {
        return [
          {
            id: 'ws-1',
            name: 'Primary Workspace',
            slug: 'primary-workspace',
            is_current: true,
          },
        ];
      }
      if (m === 'PATCH') {
        return {
          id: 'ws-1',
          name: 'Updated Workspace',
          slug: 'updated-workspace',
        };
      }
      return {};
    });

    renderComponent();

    expect(await screen.findByTestId('workspace-settings-page')).toBeDefined();
    expect(screen.getByRole('heading', { level: 1 })).toBeDefined();

    // Verify tabs
    const generalTab = screen.getByTestId('tab-general');
    const membersTab = screen.getByTestId('tab-members');
    const mcpTab = screen.getByTestId('tab-mcp');

    expect(generalTab).toBeDefined();
    expect(membersTab).toBeDefined();
    expect(mcpTab).toBeDefined();

    // General tab inputs
    const nameInput = await screen.findByTestId('workspace-name-input');
    const slugInput = screen.getByTestId('workspace-slug-input');

    expect(nameInput).toBeDefined();
    expect(slugInput).toBeDefined();

    fireEvent.change(nameInput, { target: { value: 'Updated Workspace' } });
    fireEvent.change(slugInput, { target: { value: 'updated-workspace' } });

    const submitBtn = screen.getByTestId('save-workspace-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Workspace settings updated successfully.')).toBeDefined();
    });

    // Switch to Members tab
    fireEvent.click(membersTab);
    expect(screen.getByText('Workspace Users & Principals')).toBeDefined();

    // Switch to MCP keys tab
    fireEvent.click(mcpTab);
    expect(screen.getByText('Workspace MCP Access Keys')).toBeDefined();
    expect(screen.getByTestId('link-workspace-mcp')).toBeDefined();
  });

  it('renders 403 access denied when standard member visits workspace settings', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      if (url.includes('/api/v1/auth/me')) {
        return {
          id: 'user-member',
          is_server_admin: false,
          is_workspace_admin: false,
          workspace_role: 'WORKSPACE_MEMBER',
        };
      }
      if (url.includes('/api/v1/workspaces')) {
        return [
          {
            id: 'ws-1',
            name: 'Primary Workspace',
            slug: 'primary-workspace',
            is_current: true,
          },
        ];
      }
      return {};
    });

    renderComponent();

    expect(await screen.findByTestId('access-denied-message')).toBeDefined();
    expect(screen.getByText(/You do not have administrative privileges/)).toBeDefined();
  });
});
