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

  it('supports Air-Gap mode, Display Name, and MCP Key Max TTL in general tab (KANBA-210)', async () => {
    let patchedBody: Record<string, unknown> = {};

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
          display_name: 'Acme Corp',
          default_project_visibility: 'workspace',
          session_idle_timeout_min: 120,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
          mcp_key_max_ttl_days: 90,
          air_gap_mode: false,
        };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'PATCH') {
        patchedBody = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return {
          id: 'ws-1',
          ...patchedBody,
        };
      }
      return {};
    });

    renderComponent();

    // Verify initial values
    const displayNameInput = await screen.findByTestId('workspace-display-name-input');
    const ttlInput = screen.getByTestId('workspace-mcp-key-max-ttl-input');
    const airGapToggle = screen.getByTestId<HTMLInputElement>('workspace-air-gap-toggle');

    expect(displayNameInput).toBeDefined();
    expect((displayNameInput as HTMLInputElement).value).toBe('Acme Corp');
    expect((ttlInput as HTMLInputElement).value).toBe('90');
    expect(airGapToggle.checked).toBe(false);

    // Edit values
    fireEvent.change(displayNameInput, { target: { value: 'Acme Global Security' } });
    fireEvent.change(ttlInput, { target: { value: '180' } });
    fireEvent.click(airGapToggle);

    expect(airGapToggle.checked).toBe(true);

    // Save
    fireEvent.click(screen.getByTestId('save-workspace-btn'));

    await waitFor(() => {
      expect(screen.getByText('Workspace settings updated successfully.')).toBeDefined();
    });

    expect(patchedBody.display_name).toBe('Acme Global Security');
    expect(patchedBody.mcp_key_max_ttl_days).toBe(180);
    expect(patchedBody.air_gap_mode).toBe(true);
  });

  it('supports inline role selection and remove member actions (KANBA-210)', async () => {
    let boundRole: string | null = null;
    let removedPrincipalId: string | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
        };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'p-mem-1',
            type: 'USER',
            principal_type: 'USER',
            handle: '@mem.one',
            display_name: 'Member One',
            email: 'mem1@example.com',
            role: 'WORKSPACE_MEMBER',
          },
          {
            id: 'p-untyped',
            handle: null,
            display_name: 'Untyped User',
            email: 'untyped@example.com',
            role: 'WORKSPACE_MEMBER',
          },
        ];
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          principal_id: string;
          role: string;
          role_name: string;
        };
        boundRole = body.role;
        return { ok: true };
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'DELETE') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          principal_id: string;
        };
        removedPrincipalId = body.principal_id;
        return { ok: true };
      }
      return {};
    });

    renderComponent();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Verify row and cells
    expect(await screen.findByTestId('principal-row-p-mem-1')).toBeDefined();
    expect(screen.getByTestId('member-name-p-mem-1').textContent).toBe('Member One');
    expect(screen.getByTestId('member-handle-p-mem-1').textContent).toBe('@mem.one');
    expect(screen.getByTestId('member-email-p-mem-1').textContent).toBe('mem1@example.com');
    expect(screen.getByTestId('type-pill-p-mem-1').textContent).toBe('User');

    // Change role error
    const roleSelect = screen.getByTestId('role-select-p-mem-1');
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Failed to bind role' });
    fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_MEMBER' } });
    await waitFor(() => {
      expect(screen.getByText('Failed to bind role')).toBeDefined();
    });

    // Change role success
    fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });

    await waitFor(() => {
      expect(boundRole).toBe('WORKSPACE_ADMIN');
      expect(screen.getByText('Member role updated.')).toBeDefined();
    });

    // Remove member error
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Cannot remove owner' });
    const removeBtn = screen.getByTestId('remove-member-btn-p-mem-1');
    fireEvent.click(removeBtn);
    await waitFor(() => {
      expect(screen.getByText('Cannot remove owner')).toBeDefined();
    });

    // Remove member success
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(removedPrincipalId).toBe('p-mem-1');
      expect(screen.getByText('Member removed from workspace.')).toBeDefined();
    });
  });

  it('supports Groups tab, creating groups, listing members, adding nested groups and cycle rejection (KANBA-210)', async () => {
    let createdGroupPayload: Record<string, unknown> = {};
    let addedMemberId: string | null = null;
    let removedGroupMemberId: string | null = null;
    let simulateCycle = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
        };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'grp-eng',
            type: 'GROUP',
            principal_type: 'GROUP',
            handle: '@engineers',
            display_name: 'Engineering Group',
          },
          {
            id: 'grp-core',
            type: 'GROUP',
            principal_type: 'GROUP',
            handle: '@core-team',
            display_name: 'Core Team',
          },
          {
            id: 'usr-dev',
            type: 'USER',
            principal_type: 'USER',
            handle: '@developer',
            display_name: 'Developer One',
          },
        ];
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        createdGroupPayload = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return { id: 'grp-new' };
      }
      if (url.includes('/api/v1/admin/groups/grp-eng/members') && m === 'GET') {
        return [
          {
            id: 'usr-dev',
            type: 'USER',
            principal_type: 'USER',
            handle: '@developer',
            display_name: 'Developer One',
          },
        ];
      }
      if (url.includes('/api/v1/admin/groups/grp-eng/members/grp-core') && m === 'POST') {
        if (simulateCycle) {
          const err = new Error('Adding member would introduce a cyclic group dependency.') as Error & {
            detail?: string;
            status?: number;
          };
          err.detail = 'Cannot nest group: would introduce a cyclic dependency.';
          err.status = 409;
          throw err;
        }
        addedMemberId = 'grp-core';
        return { ok: true };
      }
      if (url.includes('/api/v1/admin/groups/grp-eng/members/usr-dev') && m === 'DELETE') {
        removedGroupMemberId = 'usr-dev';
        return { ok: true };
      }
      return {};
    });

    renderComponent();

    // Switch to groups tab
    const groupsTab = await screen.findByTestId('tab-groups');
    fireEvent.click(groupsTab);

    expect(await screen.findByTestId('workspace-groups-section')).toBeDefined();
    expect(screen.getByTestId('selected-group-name').textContent).toBe('Engineering Group');

    // Verify existing member Developer One is listed
    expect(await screen.findByText('Developer One')).toBeDefined();
    expect(screen.getByTestId('group-member-type-usr-dev').textContent).toBe('User');

    // Create a new group
    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'Security Team' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: 'sec-team' } });
    fireEvent.click(screen.getByTestId('create-group-btn'));

    await waitFor(() => {
      expect(createdGroupPayload.type).toBe('GROUP');
      expect(createdGroupPayload.handle).toBe('@sec-team');
      expect(createdGroupPayload.display_name).toBe('Security Team');
      expect(screen.getByText('Group created successfully.')).toBeDefined();
    });

    // Create group failure branch
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Group creation rejected' });
    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'Faulty Team' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: '@faulty' } });
    fireEvent.click(screen.getByTestId('create-group-btn'));
    await waitFor(() => {
      expect(screen.getByText('Group creation rejected')).toBeDefined();
    });

    // Add nested group grp-core with cycle rejection
    simulateCycle = true;
    const addSelect = screen.getByTestId('add-group-member-select');
    // Early return on empty memberId
    fireEvent.change(addSelect, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('add-group-member-btn'));
    fireEvent.change(addSelect, { target: { value: 'grp-core' } });
    fireEvent.click(screen.getByTestId('add-group-member-btn'));

    await waitFor(() => {
      const alert = screen.getByTestId('group-cycle-alert');
      expect(alert.textContent).toContain('Cannot nest group: would introduce a cyclic dependency.');
    });

    // Successfully add nested group when no cycle
    simulateCycle = false;
    fireEvent.click(screen.getByTestId('add-group-member-btn'));

    await waitFor(() => {
      expect(addedMemberId).toBe('grp-core');
      expect(screen.getByText('Member added to group successfully.')).toBeDefined();
    });

    // Remove group member error handling first
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Cannot remove last owner' });
    const removeMemberBtn = screen.getByTestId('remove-group-member-usr-dev');
    fireEvent.click(removeMemberBtn);
    await waitFor(() => {
      expect(screen.getByText('Cannot remove last owner')).toBeDefined();
    });

    // Successfully remove group member
    fireEvent.click(removeMemberBtn);

    await waitFor(() => {
      expect(removedGroupMemberId).toBe('usr-dev');
      expect(screen.getByText('Member removed from group.')).toBeDefined();
    });

    // Select second group
    fireEvent.click(screen.getByTestId('group-item-grp-core'));
    await waitFor(() => {
      expect(screen.getByTestId('selected-group-name').textContent).toBe('Core Team');
    });

    // Group members load error handling
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Database error loading members' });
    fireEvent.click(screen.getByTestId('group-item-grp-eng'));
    await waitFor(() => {
      expect(screen.getByText('Database error loading members')).toBeDefined();
    });

    // Group creation error handling
    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'Bad Group' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: 'bad-group' } });
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({ detail: 'Handle already exists' });
    fireEvent.click(screen.getByTestId('create-group-btn'));
    await waitFor(() => {
      expect(screen.getByText('Handle already exists')).toBeDefined();
    });
  });

  it('covers empty groups list, null selected group, nested group rendering, and validation early returns', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({ is_server_admin: true, is_workspace_admin: true });
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return Promise.resolve({ id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' });
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return Promise.resolve([
          { id: 'usr-bare', type: 'USER', handle: '@bare', display_name: null },
        ]);
      }
      return Promise.resolve({});
    });

    renderComponent();

    // Switch to groups tab with empty groups list
    const groupsTab = await screen.findByTestId('tab-groups');
    fireEvent.click(groupsTab);

    expect(await screen.findByText('No groups created yet.')).toBeDefined();
    expect(screen.getByText('Select or create a group to view and manage membership.')).toBeDefined();

    // Early returns for empty inputs on create group and create user
    fireEvent.click(screen.getByTestId('create-group-btn'));

    // Switch to members tab and test empty user creation
    fireEvent.click(screen.getByTestId('tab-members'));
    expect(await screen.findByTestId('create-user-submit-btn')).toBeDefined();
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));
  });

  it('covers group selection, member table rendering (nested group, bare user, agent), member removal, and member addition cyclic rejection', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({ is_server_admin: true, is_workspace_admin: true });
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return Promise.resolve({ id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' });
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return Promise.resolve([
          { id: 'grp-devs', type: 'GROUP', handle: '@devs', display_name: 'Dev Team' },
          { id: 'grp-bare', type: 'GROUP', handle: null, display_name: null },
          { id: 'usr-alice', type: 'USER', handle: '@alice', display_name: 'Alice Cooper' },
          { id: 'bare-p' },
        ]);
      }
      if (url.includes('/api/v1/admin/groups/grp-bare/members') && m === 'GET') {
        return Promise.resolve([]);
      }
      if (url.includes('/api/v1/admin/groups/grp-devs/members') && m === 'GET') {
        return Promise.resolve([
          { id: 'm-nested', principal_type: 'GROUP', display_name: 'Sub Team', handle: '@subteam' },
          { id: 'm-bare', type: 'USER', display_name: null, handle: null },
          { id: 'm-agent', type: 'AGENT', display_name: 'Audit Bot', handle: '@audit' },
          { id: 'm-untyped', display_name: 'Untyped Member', handle: null },
        ]);
      }
      if (url.includes('/api/v1/admin/groups/grp-devs/members/m-nested') && m === 'DELETE') {
        return Promise.resolve({ ok: true });
      }
      if (url.includes('/api/v1/admin/groups/grp-devs/members/m-agent') && m === 'DELETE') {
        return Promise.reject(new Error('Failed to remove group member.'));
      }
      if (url.includes('/api/v1/admin/groups/grp-devs/members/usr-alice') && m === 'POST') {
        return Promise.reject(new Error('Cannot nest group: would introduce a cyclic dependency.'));
      }
      return Promise.resolve({});
    });

    renderComponent();

    const groupsTab = await screen.findByTestId('tab-groups');
    fireEvent.click(groupsTab);

    expect(await screen.findByTestId('group-member-row-m-nested')).toBeDefined();
    expect(screen.getByTestId('group-member-row-m-bare')).toBeDefined();
    expect(screen.getByTestId('group-member-row-m-agent')).toBeDefined();

    // Verify type pills
    expect(screen.getByTestId('group-member-type-m-nested').textContent).toBe('Nested Group');
    expect(screen.getByTestId('group-member-type-m-bare').textContent).toBe('User');
    expect(screen.getByTestId('group-member-type-m-agent').textContent).toBe('Agent');

    // Remove member
    fireEvent.click(screen.getByTestId('remove-group-member-m-nested'));

    // Remove member error
    fireEvent.click(screen.getByTestId('remove-group-member-m-agent'));
    await waitFor(() => {
      expect(screen.getByText('Failed to remove group member.')).toBeDefined();
    });

    // Add member with cyclic error
    const selectMember = screen.getByTestId('add-group-member-select');
    fireEvent.change(selectMember, { target: { value: 'usr-alice' } });
    fireEvent.click(screen.getByTestId('add-group-member-btn'));

    expect(await screen.findByText(/Cannot nest group: would introduce a cyclic dependency/i)).toBeDefined();

    // Select grp-bare to cover null display_name and handle fallbacks
    fireEvent.click(screen.getByText('grp-bare'));
    expect(screen.getByTestId('selected-group-name').textContent).toBe('');
    expect(screen.getByTestId('selected-group-handle').textContent).toBe('@grp-bare');
  });
});
