// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
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

    // Change all other policy fields
    fireEvent.change(screen.getByTestId('workspace-visibility-select'), { target: { value: 'private' } });
    fireEvent.change(screen.getByTestId('workspace-idle-timeout-input'), { target: { value: '60' } });
    fireEvent.change(screen.getByTestId('workspace-abs-timeout-input'), { target: { value: '720' } });
    fireEvent.change(screen.getByTestId('workspace-trash-retention-input'), { target: { value: '14' } });

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

    // Switch back to General tab
    fireEvent.click(generalTab);
    expect(screen.getByTestId('workspace-general-form')).toBeDefined();
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

  it('allows creating a new workspace user with role binding in members tab', async () => {
    let principalsList: unknown[] = [];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return {
          id: 'user-admin',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
        };
      }
      if (url.includes('/api/v1/workspaces')) {
        return [{ id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace', is_current: true }];
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
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
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return principalsList;
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          handle: string;
          display_name: string;
          email?: string;
        };
        const newPrincipal = {
          id: 'p-new-1',
          type: 'USER',
          handle: body.handle,
          display_name: body.display_name,
          email: body.email ?? null,
          role_name: 'WORKSPACE_MEMBER',
          created_at: '2026-03-01T00:00:00Z',
        };
        principalsList = [newPrincipal];
        return newPrincipal;
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        return { ok: true };
      }
      return {};
    });

    renderComponent();

    // Switch to Members tab
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    expect(await screen.findByTestId('workspace-members-section')).toBeDefined();

    // Fill Create User form
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: 'alice_dev' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Alice Engineer' } });
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'alice@example.com' } });
    fireEvent.change(screen.getByTestId('new-user-password'), { target: { value: 'SecretPassword123' } });
    fireEvent.change(screen.getByTestId('new-user-role-select'), { target: { value: 'WORKSPACE_ADMIN' } });

    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('User Alice Engineer created successfully.')).toBeDefined();
    });

    expect(screen.getByText('Alice Engineer')).toBeDefined();
    expect(screen.getByText('alice@example.com')).toBeDefined();
  });

  it('handles workspace settings load failure gracefully', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValue(new Error('Network load timeout'));

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Network load timeout')).toBeDefined();
    });
  });

  it('handles PATCH error and non-Error rejection when saving general settings', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/workspaces')) {
        return [{ id: 'ws-1', name: 'Primary Workspace', slug: 'primary', is_current: true }];
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary',
          default_project_visibility: 'workspace',
          session_idle_timeout_min: 120,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
        };
      }
      if (m === 'PATCH') {
        throw new Error('Slug already taken');
      }
      return {};
    });

    renderComponent();

    const saveBtn = await screen.findByTestId('save-workspace-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Slug already taken')).toBeDefined();
    });
  });

  it('validates empty inputs and handles user creation error on members tab', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/workspaces')) {
        return [{ id: 'ws-1', name: 'Primary Workspace', slug: 'primary', is_current: true }];
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary' };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'p-no-name',
            principal_type: 'USER',
            handle: '@noname',
            display_name: null,
            email: null,
          },
        ];
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        throw new Error('Handle already registered');
      }
      return {};
    });

    renderComponent();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Empty submit does nothing
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    // Principal without display_name shows handle fallback
    expect(screen.getByText('@noname')).toBeDefined();

    // Fill form and trigger failure
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: 'existing_handle' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Existing User' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('Handle already registered')).toBeDefined();
    });

    // Switch to MCP tab
    const mcpTab = screen.getByTestId('tab-mcp');
    fireEvent.click(mcpTab);
    expect(screen.getByTestId('workspace-mcp-section')).toBeDefined();
  });

  it('covers handle with leading @, { items } principals object response, and string error on user creation', async () => {
    let returnItemsObject = false;
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
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        if (returnItemsObject) {
          return {
            items: [
              {
                id: 'p-item-1',
                principal_type: 'USER',
                handle: '@itemuser',
                display_name: 'Item User',
                email: 'item@example.com',
              },
            ],
          };
        }
        return [];
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        if (returnItemsObject) {
          return { id: 'p-item-1' };
        }
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String user creation error';
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        return { ok: true };
      }
      return {};
    });

    renderComponent();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // 1. Submit with leading @ and throw string error
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: '@string_user' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'String User' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('Failed to create workspace user.')).toBeDefined();
    });

    // 2. Submit with { items } response
    returnItemsObject = true;
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: '@itemuser' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Item User' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('User Item User created successfully.')).toBeDefined();
    });
    expect(screen.getByText('Item User')).toBeDefined();
  });

  it('covers fallback error on init and save, principal ID fallback, and empty user ID response', async () => {
    // 1. Init failure with empty error object
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      return {};
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Failed to load workspace settings.')).toBeDefined();
    });

    cleanup();
    queryClient.clear();

    // 2. Principal ID fallback (null display_name and null handle), empty save rejection, and user creation with no ID
    let roleBindingCalled = false;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return { is_workspace_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'WS One',
          slug: 'ws-one',
          default_project_visibility: 'workspace',
          session_idle_timeout_min: 120,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
        };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'PATCH') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'p-bare-id',
            principal_type: 'USER',
            handle: null,
            display_name: null,
            email: 'bare@example.com',
          },
        ];
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        return {}; // No ID returned
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        roleBindingCalled = true;
        return { ok: true };
      }
      return {};
    });

    renderComponent();

    // Verify general save empty error fallback
    const saveBtn = await screen.findByTestId('save-workspace-btn');
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByText('Failed to update workspace settings.')).toBeDefined();
    });

    // Switch to members tab
    const membersTab = screen.getByTestId('tab-members');
    fireEvent.click(membersTab);

    // Verify bare ID fallback and email
    expect(await screen.findByText('p-bare-id')).toBeDefined();
    expect(screen.getByText('bare@example.com')).toBeDefined();

    // Create user where response has no ID
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: 'noid_user' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'No ID User' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('User No ID User created successfully.')).toBeDefined();
    });
    expect(roleBindingCalled).toBe(false);
  });
});
