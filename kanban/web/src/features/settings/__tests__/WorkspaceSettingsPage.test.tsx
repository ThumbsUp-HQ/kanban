// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { WorkspaceSettingsPage, formatHandle, parseTabFromHash } from '../WorkspaceSettingsPage';
import * as clientModule from '../../../api/client';
import * as sessionGuardModule from '../../auth/useSessionGuard';

describe('WorkspaceSettingsPage (KANBA-202)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    window.location.hash = '';
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

    expect(generalTab).toBeDefined();
    expect(membersTab).toBeDefined();
    expect(screen.getByTestId('link-workspace-mcp')).toBeDefined();

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

    // Switch back to General tab
    fireEvent.click(generalTab);
    expect(screen.getByTestId('workspace-general-form')).toBeDefined();
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

  it('hydrates default_skip_loaded_sequence_numbers, allows toggling, and submits in PATCH payload', async () => {
    let patchPayload: Record<string, unknown> | null = null;
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
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          slug: 'primary-workspace',
          default_skip_loaded_sequence_numbers: true,
        };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'PATCH') {
        const rawBody = (options as { body?: string } | undefined)?.body;
        patchPayload = typeof rawBody === 'string' ? (JSON.parse(rawBody) as Record<string, unknown>) : null;
        return {
          id: 'ws-1',
          name: 'Primary Workspace',
          default_skip_loaded_sequence_numbers: false,
        };
      }
      return {};
    });

    renderComponent();

    const checkbox = await screen.findByTestId<HTMLInputElement>('workspace-default-skip-loaded-seq-checkbox');
    expect(checkbox.checked).toBe(true);

    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);

    fireEvent.click(screen.getByTestId('save-workspace-btn'));

    await waitFor(() => {
      expect(patchPayload).not.toBeNull();
      expect(patchPayload?.default_skip_loaded_sequence_numbers).toBe(false);
    });
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
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'existing@example.com' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('Handle already registered')).toBeDefined();
    });

    // Switch back to general tab and verify workspace-mcp-section
    const generalTab = screen.getByTestId('tab-general');
    fireEvent.click(generalTab);
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
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'string_user@example.com' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('Failed to create workspace user.')).toBeDefined();
    });

    // 2. Submit with { items } response
    returnItemsObject = true;
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: '@itemuser' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Item User' } });
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'itemuser@example.com' } });
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
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'noid@example.com' } });
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
    await waitFor(() => {
      expect(screen.getByText('Member removed from group.')).toBeDefined();
    });

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
    expect(await screen.findByTestId('empty-group-members')).toBeDefined();
  });

  it('covers early return guards and error fallbacks for members, users, and groups', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { id: 'admin-1', is_server_admin: true, is_workspace_admin: true, workspace_role: 'SERVER_ADMIN' };
      }
      if (url.includes('/api/v1/workspaces/current') || url.includes('/api/v1/workspaces/ws-1')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          { id: 'usr-1', type: 'USER', display_name: 'User 1', handle: '@u1', role: 'MEMBER' },
          { id: 'grp-1', type: 'GROUP', display_name: 'Group 1', handle: '@g1' },
        ];
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        return Promise.reject(Object.assign(new Error('Principal creation failed'), { detail: 'Principal creation failed' }));
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        return Promise.reject(Object.assign(new Error('Role binding update failed'), { detail: 'Role binding update failed' }));
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'DELETE') {
        return Promise.reject(Object.assign(new Error('Role binding delete failed'), { detail: 'Role binding delete failed' }));
      }
      if (url.includes('/api/v1/admin/groups/grp-1/members') && m === 'GET') {
        return [{ id: 'm-1', display_name: 'Member 1', handle: '@m1', type: 'USER' }];
      }
      if (url.includes('/api/v1/admin/groups/grp-1/members/m-1') && m === 'DELETE') {
        return Promise.reject(Object.assign(new Error('Custom group member delete detail'), { detail: 'Custom group member delete detail' }));
      }
      if (url.includes('/api/v1/admin/groups/grp-1/members') && m === 'POST') {
        return Promise.reject(Object.assign(new Error('Custom cycle detail error'), { detail: 'Custom cycle detail error' }));
      }
      return {};
    });

    renderComponent();

    // 1. Members Tab: early return on empty user form inputs
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Click submit with empty inputs
    const addUserBtn = screen.getByTestId('create-user-submit-btn');
    fireEvent.click(addUserBtn);

    // Fill inputs and trigger error rejection
    const handleInput = screen.getByTestId('new-user-handle');
    const nameInput = screen.getByTestId('new-user-name');
    fireEvent.change(handleInput, { target: { value: 'newbie' } });
    fireEvent.change(nameInput, { target: { value: 'Newbie Name' } });
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'newbie@example.com' } });
    fireEvent.click(addUserBtn);
    await waitFor(() => {
      expect(screen.getByText('Principal creation failed')).toBeDefined();
    });

    // Update role error rejection
    const roleSelect = screen.getByTestId('role-select-usr-1');
    fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });
    await waitFor(() => {
      expect(screen.getByText('Role binding update failed')).toBeDefined();
    });

    // Remove member error rejection
    const removeBtn = screen.getByTestId('remove-member-btn-usr-1');
    fireEvent.click(removeBtn);
    await waitFor(() => {
      expect(screen.getByText('Role binding delete failed')).toBeDefined();
    });

    // 2. Groups Tab: early return on empty group form inputs
    const groupsTab = screen.getByTestId('tab-groups');
    fireEvent.click(groupsTab);

    const createGroupBtn = screen.getByTestId('create-group-btn');
    fireEvent.click(createGroupBtn);

    const groupNameInput = screen.getByTestId('new-group-name');
    const groupHandleInput = screen.getByTestId('new-group-handle');
    fireEvent.change(groupNameInput, { target: { value: 'Alpha Group' } });
    fireEvent.change(groupHandleInput, { target: { value: 'alphagroup' } });
    fireEvent.click(createGroupBtn);
    await waitFor(() => {
      expect(screen.getByText('Principal creation failed')).toBeDefined();
    });

    // Empty memberId early return on add group member
    const addMemberBtn = screen.getByTestId('add-group-member-btn');
    fireEvent.click(addMemberBtn);

    // Remove group member with custom detail error
    const removeGroupMemberBtn = screen.getByTestId('remove-group-member-m-1');
    fireEvent.click(removeGroupMemberBtn);
    await waitFor(() => {
      expect(screen.getByText('Custom group member delete detail')).toBeDefined();
    });
  });

  it('covers nullish settings fallbacks, empty principals object, and string error fallbacks', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/auth/me')) {
        return null;
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return {};
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return { items: undefined };
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'PATCH') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      return {};
    });

    const { unmount } = renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('workspace-settings-page')).toBeDefined();
    });

    // Check defaults rendered from nullish fallbacks
    const trashInput = screen.getByTestId<HTMLInputElement>('workspace-trash-retention-input');
    expect(trashInput.value).toBe('30');

    // Trigger general settings save error fallback
    const form = document.querySelector('form.kb-settings-form');
    if (form) fireEvent.submit(form);
    await waitFor(() => {
      expect(screen.getByText('Failed to update workspace settings.')).toBeDefined();
    });

    unmount();
  });

  it('covers csrf token injection and empty input validations across members and groups', async () => {
    vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue('csrf-token-valid-xyz');

    const mockPrincipals = [
      { id: 'usr-1', handle: 'alice', display_name: 'Alice User', role: 'MEMBER', type: 'USER', principal_type: 'USER' },
      { id: 'grp-1', handle: '@engineers', display_name: 'Engineers Group', type: 'GROUP', principal_type: 'GROUP' },
    ];

    const csrfTokensRecorded: string[] = [];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, init) => {
      const url = path;
      const m = method.toUpperCase();
      const headers = (init as { headers?: Record<string, string> } | undefined)?.headers;
      if (headers?.['X-CSRF-Token']) {
        csrfTokensRecorded.push(headers['X-CSRF-Token']);
      }
      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({ is_server_admin: true, is_workspace_admin: true });
      }
      if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
        return Promise.resolve({ name: 'WS', slug: 'ws', trash_retention_days: 30 });
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return Promise.resolve(mockPrincipals);
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        return Promise.resolve({ id: 'grp-new', handle: '@designers', display_name: 'Designers', type: 'GROUP' });
      }
      if (url.includes('/members') && m === 'GET') {
        return Promise.resolve([{ id: 'usr-1', handle: 'alice', display_name: 'Alice User' }]);
      }
      return Promise.resolve({ success: true });
    });

    const { unmount } = renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('workspace-settings-page')).toBeDefined();
    });

    // 1. General save with csrf
    const form = document.querySelector('form.kb-settings-form');
    if (form) fireEvent.submit(form);
    await waitFor(() => {
      expect(csrfTokensRecorded).toContain('csrf-token-valid-xyz');
    });

    // 2. Switch to Members tab
    fireEvent.click(screen.getByTestId('tab-members'));
    await waitFor(() => {
      expect(screen.getByTestId('new-user-handle')).toBeDefined();
    });

    // Submit empty user form (hits line 241: if (!newHandle.trim() || !newDisplayName.trim()) return)
    const createUserForm = screen.getByTestId('create-user-form');
    fireEvent.submit(createUserForm);

    // Fill valid user and submit with csrf
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: 'bob' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Bob Builder' } });
    fireEvent.submit(createUserForm);

    // Update role with csrf
    const roleSelect = screen.getByTestId('role-select-usr-1');
    fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });

    // Remove member with csrf
    const removeBtn = screen.getByTestId('remove-member-btn-usr-1');
    fireEvent.click(removeBtn);

    // 3. Switch to Groups tab
    fireEvent.click(screen.getByTestId('tab-groups'));
    await waitFor(() => {
      expect(screen.getByTestId('new-group-name')).toBeDefined();
    });

    // Submit empty group form (hits line 343: if (!newGroupName.trim() || !newGroupHandle.trim()) return)
    const createGroupForm = screen.getByTestId('create-group-form');
    fireEvent.submit(createGroupForm);

    // Create group with handle starting with @
    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'Designers' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: '@designers' } });
    fireEvent.submit(createGroupForm);

    await waitFor(() => {
      expect(csrfTokensRecorded.length).toBeGreaterThanOrEqual(4);
    });

    unmount();
  });

  it('covers role update / member remove in members tab', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({ id: 'admin-1', is_server_admin: true, is_workspace_admin: true, workspace_role: 'SERVER_ADMIN' });
      }
      if (url.includes('/api/v1/workspaces/current') || url.includes('/api/v1/workspaces/ws-1')) {
        return Promise.resolve({ id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' });
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return Promise.resolve([
          { id: 'usr-bob', type: 'USER', handle: '@bob', display_name: 'Bob Ross', role: 'WORKSPACE_MEMBER' },
          { id: 'usr-charlie', type: 'USER', handle: '@charlie', display_name: 'Charlie', role: 'WORKSPACE_GUEST' },
        ]);
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        return Promise.resolve({ ok: true });
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'DELETE') {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({});
    });

    renderComponent();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // 1. Role update success
    const roleSelect = await screen.findByTestId('role-select-usr-bob');
    fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });
    expect(await screen.findByText('Member role updated.')).toBeDefined();

    // 2. Member remove success
    const removeBtn = screen.getByTestId('remove-member-btn-usr-bob');
    fireEvent.click(removeBtn);
    expect(await screen.findByText('Member removed from workspace.')).toBeDefined();

    // 3. Role update error
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      if (path.includes('/api/v1/admin/role-bindings')) {
        return Promise.reject(Object.assign(new Error(''), { detail: 'Custom detail role error' }));
      }
      return Promise.resolve({});
    });
    const charlieRoleSelect = screen.getByTestId('role-select-usr-charlie');
    fireEvent.change(charlieRoleSelect, { target: { value: 'WORKSPACE_ADMIN' } });
    expect(await screen.findByText('Custom detail role error')).toBeDefined();

    // 4. Member remove error
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      if (path.includes('/api/v1/admin/role-bindings')) {
        return Promise.reject(Object.assign(new Error(''), { detail: 'Custom detail remove error' }));
      }
      return Promise.resolve({});
    });
    const charlieRemoveBtn = screen.getByTestId('remove-member-btn-usr-charlie');
    fireEvent.click(charlieRemoveBtn);
    expect(await screen.findByText('Custom detail remove error')).toBeDefined();
  });

  it('covers formatHandle edge cases', () => {
    expect(formatHandle(null)).toBe('');
    expect(formatHandle(undefined)).toBe('');
    expect(formatHandle('')).toBe('');
    expect(formatHandle('@')).toBe('');
    expect(formatHandle('@@@')).toBe('');
    expect(formatHandle('alice')).toBe('@alice');
    expect(formatHandle('@bob')).toBe('@bob');
    expect(formatHandle('@@charlie')).toBe('@charlie');
  });

  it('KAN-14: renders live principal payload without handle and resolves p.handle ?? p.principal in members and groups tabs', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return {
          id: 'user-admin',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'SERVER_ADMIN',
        };
      }
      if (url.includes('/api/v1/workspaces/current')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'u-live-1',
            principal: '@alice', // Note: backend returns 'principal', no 'handle'
            display_name: 'Alice Live',
            type: 'USER',
            role: 'WORKSPACE_MEMBER',
            email: 'alice@live.test',
          },
          {
            id: 'grp-live-1',
            principal: '@core-team',
            display_name: 'Core Team',
            type: 'GROUP',
            role: 'WORKSPACE_MEMBER',
          },
        ];
      }
      if (url.includes('/api/v1/admin/groups/grp-live-1/members') && m === 'GET') {
        return [
          {
            id: 'm-live-1',
            principal: '@bob-member', // Group member without handle
            display_name: 'Bob GroupMember',
            type: 'USER',
          },
        ];
      }
      return {};
    });

    renderComponent();
    expect(await screen.findByTestId('workspace-settings-page')).toBeDefined();

    // 1. Members Tab: verify p.principal is used as handle
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    expect(await screen.findByTestId('member-name-u-live-1')).toBeDefined();
    expect(screen.getByTestId('member-handle-u-live-1').textContent).toBe('@alice');
    expect(screen.getByTestId('role-select-u-live-1').getAttribute('aria-label')).toBe('Role for Alice Live');

    // 2. Groups Tab: verify group item, detail header, select options, and group members render p.principal
    const groupsTab = screen.getByTestId('tab-groups');
    fireEvent.click(groupsTab);

    expect(await screen.findByTestId('group-item-grp-live-1')).toBeDefined();
    expect(screen.getAllByText('@core-team').length).toBeGreaterThan(0);

    // Select group
    fireEvent.click(screen.getByTestId('group-item-grp-live-1'));
    expect(await screen.findByTestId('selected-group-name')).toBeDefined();
    expect(screen.getByTestId('selected-group-handle').textContent).toBe('@core-team');

    // Verify Add to Group option displays formatted principal
    const option = screen.getByText(/Alice Live \(@alice\)/);
    expect(option).toBeDefined();

    // Verify group member displays formatted principal
    expect(await screen.findByText('Bob GroupMember')).toBeDefined();
    expect(screen.getByText('@bob-member')).toBeDefined();
  });

  it('KAN-14: sends bound role in DELETE /api/v1/admin/role-bindings and validates required email before creating user', async () => {
    let deletePayload: Record<string, unknown> | null = null;
    let createPayload: Record<string, unknown> | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return {
          id: 'user-admin',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'SERVER_ADMIN',
        };
      }
      if (url.includes('/api/v1/workspaces/current')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return { id: 'ws-1', name: 'Primary Workspace', slug: 'primary-workspace' };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'u-bound-1',
            principal: '@charlie',
            display_name: 'Charlie Member',
            type: 'USER',
            role: 'WORKSPACE_ADMIN',
          },
        ];
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'DELETE') {
        const bodyStr = (options as { body?: string }).body ?? '{}';
        deletePayload = JSON.parse(bodyStr) as Record<string, unknown>;
        return { ok: true };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        const bodyStr = (options as { body?: string }).body ?? '{}';
        createPayload = JSON.parse(bodyStr) as Record<string, unknown>;
        return { id: 'new-user-123' };
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'POST') {
        return { ok: true };
      }
      return {};
    });

    renderComponent();
    expect(await screen.findByTestId('workspace-settings-page')).toBeDefined();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // 1. Test DELETE role-bindings passes bound role
    expect(await screen.findByTestId('remove-member-btn-u-bound-1')).toBeDefined();
    fireEvent.click(screen.getByTestId('remove-member-btn-u-bound-1'));

    await waitFor(() => {
      expect(screen.getByText('Member removed from workspace.')).toBeDefined();
    });
    expect(deletePayload).toEqual({
      principal_id: 'u-bound-1',
      role: 'WORKSPACE_ADMIN',
      scope_type: 'workspace',
    });

    // 2. Test user creation email validation inline
    fireEvent.change(screen.getByTestId('new-user-handle'), { target: { value: 'testuser' } });
    fireEvent.change(screen.getByTestId('new-user-name'), { target: { value: 'Test User' } });
    // Empty email
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    expect(await screen.findByText('Email is required for user provisioning.')).toBeDefined();
    expect(createPayload).toBeNull();

    // Now fill email and submit successfully
    fireEvent.change(screen.getByTestId('new-user-email'), { target: { value: 'test@user.org' } });
    fireEvent.click(screen.getByTestId('create-user-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('User Test User created successfully.')).toBeDefined();
    });
    expect(createPayload).toEqual({
      type: 'USER',
      handle: '@testuser',
      display_name: 'Test User',
      email: 'test@user.org',
    });
  });

  it('KAN-14: covers role fallback branches, null display_name/handle member formatting, and group error branches', async () => {
    let removeBody: Record<string, unknown> | null = null;
    let createGroupFailMode: 'none' | 'detail' | 'message' | 'fallback' = 'none';
    let groupAddFailWithMessage = false;
    let groupRemoveFailMode: 'none' | 'detail' | 'message' | 'fallback' = 'none';

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { id: 'admin-1', is_server_admin: true, is_workspace_admin: true };
      }
      if (url.includes('/api/v1/workspaces/current') || url.includes('/api/v1/admin/workspace-settings')) {
        return { id: 'ws-1', name: 'WS 1' };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'p-bare-uuid',
            display_name: null,
            handle: null,
            principal: null,
            type: 'USER',
            role: null,
            role_name: null,
          },
          {
            id: 'p-handle-only',
            display_name: null,
            handle: 'handleonly',
            principal: null,
            type: 'USER',
            role: 'WORKSPACE_MEMBER',
          },
          {
            id: 'p-princ-only',
            display_name: null,
            handle: null,
            principal: 'princonly',
            type: 'USER',
            role: 'WORKSPACE_MEMBER',
          },
          {
            id: 'p-name-only',
            display_name: 'Name Only',
            handle: null,
            principal: null,
            type: 'USER',
            role: null,
            role_name: 'WORKSPACE_GUEST',
          },
          {
            id: 'grp-test-1',
            display_name: 'Test Group',
            principal: '@testgrp',
            type: 'GROUP',
          },
        ];
      }
      if (url.includes('/api/v1/admin/role-bindings') && m === 'DELETE') {
        const bodyStr = (options as { body?: string }).body ?? '{}';
        removeBody = JSON.parse(bodyStr) as Record<string, unknown>;
        return { ok: true };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'POST') {
        if (createGroupFailMode === 'detail') {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw { detail: 'Group detail failure' };
        }
        if (createGroupFailMode === 'message') {
          throw new Error('Group message failure');
        }
        if (createGroupFailMode === 'fallback') {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw {};
        }
        return { id: '' }; // empty created ID to hit if (created.id) false branch
      }
      if (url.includes('/api/v1/admin/groups/grp-test-1/members') && m === 'POST') {
        if (groupAddFailWithMessage) {
          throw new Error('Group add message failure');
        }
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {}; // neither detail nor message to hit fallback cyclic error
      }
      if (url.includes('/api/v1/admin/groups/grp-test-1/members') && m === 'DELETE') {
        if (groupRemoveFailMode === 'detail') {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw { detail: 'Group remove detail failure' };
        }
        if (groupRemoveFailMode === 'message') {
          throw new Error('Group remove message failure');
        }
        if (groupRemoveFailMode === 'fallback') {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw {};
        }
        return {};
      }
      if (url.includes('/api/v1/admin/groups/grp-test-1/members') && m === 'GET') {
        return [
          { id: 'm-to-remove', display_name: 'Member In Group', type: 'USER' },
        ];
      }
      return {};
    });

    renderComponent();
    expect(await screen.findByTestId('workspace-settings-page')).toBeDefined();

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // 1. Verify bare UUID fallback when display_name, handle, and principal are null
    expect(await screen.findByTestId('member-name-p-bare-uuid')).toBeDefined();
    expect(screen.getByTestId('member-name-p-bare-uuid').textContent).toBe('p-bare-uuid');
    expect(screen.queryByTestId('member-handle-p-bare-uuid')).toBeNull();

    // Verify formatHandle fallback for null display_name with handle or principal
    expect(screen.getByTestId('member-name-p-handle-only').textContent).toBe('@handleonly');
    expect(screen.getByTestId('member-name-p-princ-only').textContent).toBe('@princonly');

    // 2. Remove member with null role and null role_name -> falls back to WORKSPACE_MEMBER
    const removeBareBtn = screen.getByTestId('remove-member-btn-p-bare-uuid');
    fireEvent.click(removeBareBtn);
    await waitFor(() => {
      expect(removeBody).toEqual({
        principal_id: 'p-bare-uuid',
        role: 'WORKSPACE_MEMBER',
        scope_type: 'workspace',
      });
    });

    // 3. Remove member with null role but role_name = WORKSPACE_GUEST
    const removeNameOnlyBtn = screen.getByTestId('remove-member-btn-p-name-only');
    fireEvent.click(removeNameOnlyBtn);
    await waitFor(() => {
      expect(removeBody).toEqual({
        principal_id: 'p-name-only',
        role: 'WORKSPACE_GUEST',
        scope_type: 'workspace',
      });
    });

    // 4. Test group creation with empty ID response
    const groupsTab = screen.getByTestId('tab-groups');
    fireEvent.click(groupsTab);

    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'No ID Group' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: 'noidgrp' } });
    fireEvent.click(screen.getByTestId('create-group-btn'));

    await waitFor(() => {
      expect(screen.getByText('Group created successfully.')).toBeDefined();
    });

    // 5. Test group creation error branches (detail, message, fallback)
    createGroupFailMode = 'detail';
    fireEvent.change(screen.getByTestId('new-group-name'), { target: { value: 'Fail Group' } });
    fireEvent.change(screen.getByTestId('new-group-handle'), { target: { value: 'failgrp' } });
    fireEvent.click(screen.getByTestId('create-group-btn'));
    await waitFor(() => {
      expect(screen.getByText('Group detail failure')).toBeDefined();
    });

    createGroupFailMode = 'message';
    fireEvent.click(screen.getByTestId('create-group-btn'));
    await waitFor(() => {
      expect(screen.getByText('Group message failure')).toBeDefined();
    });

    createGroupFailMode = 'fallback';
    fireEvent.click(screen.getByTestId('create-group-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to create group.')).toBeDefined();
    });

    // 6. Select group and test add/remove group member error branches
    fireEvent.click(screen.getByTestId('group-item-grp-test-1'));
    expect(await screen.findByTestId('add-group-member-select')).toBeDefined();

    // Group add error with message
    groupAddFailWithMessage = true;
    fireEvent.change(screen.getByTestId('add-group-member-select'), { target: { value: 'p-bare-uuid' } });
    fireEvent.click(screen.getByTestId('add-group-member-btn'));
    await waitFor(() => {
      expect(screen.getByText('Group add message failure')).toBeDefined();
    });

    // Group add error fallback
    groupAddFailWithMessage = false;
    fireEvent.click(screen.getByTestId('add-group-member-btn'));
    await waitFor(() => {
      expect(screen.getByText('Cannot nest group: would introduce a cyclic dependency.')).toBeDefined();
    });

    // Group remove error branches (detail, message, fallback)
    expect(await screen.findByTestId('remove-group-member-m-to-remove')).toBeDefined();

    groupRemoveFailMode = 'detail';
    fireEvent.click(screen.getByTestId('remove-group-member-m-to-remove'));
    await waitFor(() => {
      expect(screen.getByText('Group remove detail failure')).toBeDefined();
    });

    groupRemoveFailMode = 'message';
    fireEvent.click(screen.getByTestId('remove-group-member-m-to-remove'));
    await waitFor(() => {
      expect(screen.getByText('Group remove message failure')).toBeDefined();
    });

    groupRemoveFailMode = 'fallback';
    fireEvent.click(screen.getByTestId('remove-group-member-m-to-remove'));
    await waitFor(() => {
      expect(screen.getByText('Failed to remove group member.')).toBeDefined();
    });
  });

  it('renders id="tab-*" attributes on all settings tab buttons', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', default_project_visibility: 'workspace' };
      }
      return [];
    });

    renderComponent();

    const generalTab = await screen.findByTestId('tab-general');
    const membersTab = await screen.findByTestId('tab-members');
    const groupsTab = await screen.findByTestId('tab-groups');

    expect(generalTab.getAttribute('id')).toBe('tab-general');
    expect(membersTab.getAttribute('id')).toBe('tab-members');
    expect(groupsTab.getAttribute('id')).toBe('tab-groups');
  });

  it('synchronizes active tab with window.location.hash on initial mount, click, and hashchange', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', default_project_visibility: 'workspace' };
      }
      if (path.includes('/api/v1/admin/principals')) {
        return [];
      }
      return [];
    });

    // 1. Initial mount with #tab-members in hash
    window.location.hash = '#tab-members';

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/workspaces/settings#tab-members']}>
          <WorkspaceSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('tab-members').getAttribute('aria-selected')).toBe('true');
    });

    // 2. Click on #tab-groups updates window.location.hash
    const groupsTab = screen.getByTestId('tab-groups');
    fireEvent.click(groupsTab);

    expect(window.location.hash).toBe('#tab-groups');
    expect(groupsTab.getAttribute('aria-selected')).toBe('true');

    // 3. hashchange event to #tab-general
    window.location.hash = '#tab-general';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.getByTestId('tab-general').getAttribute('aria-selected')).toBe('true');
    });

    // 4. Reset hash
    window.location.hash = '';
  });

  it('resets activeTab to general when window.location.hash becomes empty or hash-only on browser back navigation', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', air_gap_mode: false };
      }
      return [];
    });

    window.location.hash = '#tab-members';

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/workspaces/settings#tab-members']}>
          <WorkspaceSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('tab-members').getAttribute('aria-selected')).toBe('true');
    });

    // Simulate browser Back button navigating to base URL with empty hash ""
    window.location.hash = '';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.getByTestId('tab-general').getAttribute('aria-selected')).toBe('true');
    });

    // Switch back to groups
    window.location.hash = '#tab-groups';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.getByTestId('tab-groups').getAttribute('aria-selected')).toBe('true');
    });

    // Simulate browser Back button navigating to '#'
    window.location.hash = '#';
    fireEvent(window, new HashChangeEvent('hashchange'));

    await waitFor(() => {
      expect(screen.getByTestId('tab-general').getAttribute('aria-selected')).toBe('true');
    });

    window.location.hash = '';
  });

  it('parseTabFromHash handles hash variations and defaults to null', () => {
    expect(parseTabFromHash('#tab-general')).toBe('general');
    expect(parseTabFromHash('#general')).toBe('general');
    expect(parseTabFromHash('tab-general')).toBe('general');
    expect(parseTabFromHash('#tab-members')).toBe('members');
    expect(parseTabFromHash('#members')).toBe('members');
    expect(parseTabFromHash('#tab-groups')).toBe('groups');
    expect(parseTabFromHash('#groups')).toBe('groups');
    expect(parseTabFromHash('#tab-trash')).toBe('trash');
    expect(parseTabFromHash('#trash')).toBe('trash');
    expect(parseTabFromHash('#unknown')).toBeNull();
    expect(parseTabFromHash('')).toBeNull();
    expect(parseTabFromHash(null)).toBeNull();
    expect(parseTabFromHash(undefined)).toBeNull();
  });

  it('dispatches CustomEvent kb:system-status-changed on air gap mode update', async () => {
    let patchedBody: Record<string, unknown> | null = null;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        if (method.toUpperCase() === 'PATCH') {
          const bodyVal = options && 'body' in options ? options.body : undefined;
          patchedBody = typeof bodyVal === 'string'
            ? (JSON.parse(bodyVal) as Record<string, unknown>)
            : ((bodyVal as Record<string, unknown> | undefined) ?? {});
          return {
            name: 'WS',
            slug: 'ws',
            air_gap_mode: true,
          };
        }
        return { name: 'WS', slug: 'ws', air_gap_mode: false, default_project_visibility: 'workspace' };
      }
      return [];
    });

    const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent');

    renderComponent();

    const airGapCheckbox = await screen.findByTestId('workspace-air-gap-toggle');
    fireEvent.click(airGapCheckbox);

    const submitBtn = screen.getByTestId('save-workspace-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(patchedBody?.air_gap_mode).toBe(true);
    });

    expect(dispatchEventSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'kb:system-status-changed' }),
    );
  });

  it('supports Trash & Retention tab navigation, retention policy update, and filterable table (KAN-30)', async () => {
    let patchedRetention: number | null = null;
    let requestedKind: string | null = null;
    let requestedQuery: string | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        if (m === 'PATCH') {
          const bodyVal = options && 'body' in options ? options.body : undefined;
          const parsed = typeof bodyVal === 'string'
            ? (JSON.parse(bodyVal) as Record<string, unknown>)
            : ((bodyVal as Record<string, unknown> | undefined) ?? {});
          if (typeof parsed.trash_retention_days === 'number') {
            patchedRetention = parsed.trash_retention_days;
          }
          return { name: 'WS', slug: 'ws', trash_retention_days: patchedRetention ?? 45 };
        }
        return { name: 'WS', slug: 'ws', trash_retention_days: 30 };
      }
      if (path.includes('/api/v1/admin/trash')) {
        const url = new URL(`http://localhost${path}`);
        requestedKind = url.searchParams.get('kind');
        requestedQuery = url.searchParams.get('q');
        return {
          items: [
            {
              id: 'trash-item-1',
              kind: 'issue',
              key: 'KAN-99',
              title: 'Expired Issue',
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 28,
              project_id: 'proj-1',
            },
            {
              id: 'trash-item-2',
              kind: 'doc',
              key: 'DOC-1',
              title: 'Architecture Doc',
              deleted_at: '2026-11-18T10:00:00Z',
              remaining_days: 27,
              project_id: null,
            },
            {
              id: 'trash-item-3',
              kind: 'sticky',
              key: null,
              title: 'Expired Sticky',
              deleted_at: '2026-11-17T10:00:00Z',
              remaining_days: 0,
              project_id: null,
            },
            {
              id: 'trash-item-4',
              kind: 'unknown_kind',
              key: 'UNK-1',
              title: null,
              deleted_at: '2026-11-16T10:00:00Z',
              remaining_days: 2,
              project_id: null,
            },
          ],
          retention_days: 30,
          total: 4,
        };
      }
      return [];
    });

    renderComponent();

    const trashTab = await screen.findByTestId('tab-trash');
    expect(trashTab).toBeDefined();

    // Click trash tab
    fireEvent.click(trashTab);
    expect(window.location.hash).toBe('#tab-trash');

    // Studio rendered
    expect(await screen.findByTestId('workspace-trash-studio')).toBeDefined();
    expect(screen.getByTestId('workspace-trash-retention-card')).toBeDefined();
    expect(screen.getByTestId('trash-items-table')).toBeDefined();

    // Update retention policy
    const retentionInput = screen.getByTestId('workspace-trash-retention-input-trash-tab');
    fireEvent.change(retentionInput, { target: { value: '45' } });
    const saveRetentionBtn = screen.getByTestId('save-trash-retention-btn');
    fireEvent.click(saveRetentionBtn);

    await waitFor(() => {
      expect(patchedRetention).toBe(45);
      expect(screen.getByText('Trash retention policy updated to 45 days.')).toBeDefined();
    });

    // Test filter pills
    expect(screen.getByTestId('trash-filter-sticky').textContent).toBe('Stickies');
    expect(screen.getByTestId('trash-filter-all').textContent).toBe('All Items');
    expect(screen.getByTestId('trash-filter-issue').textContent).toBe('Issues');
    expect(screen.getByTestId('trash-filter-doc').textContent).toBe('Docs');
    expect(screen.getByTestId('trash-filter-page').textContent).toBe('Pages');
    expect(screen.getByTestId('trash-filter-cycle').textContent).toBe('Cycles');
    expect(screen.getByTestId('trash-filter-module').textContent).toBe('Modules');
    expect(screen.getByTestId('trash-filter-view').textContent).toBe('Views');
    expect(screen.getByTestId('trash-filter-project').textContent).toBe('Projects');

    const docFilter = screen.getByTestId('trash-filter-doc');
    fireEvent.click(docFilter);
    await waitFor(() => {
      expect(requestedKind).toBe('doc');
    });

    // Click trash tab again to cover hash equality branch
    fireEvent.click(trashTab);

    // Test search box
    const searchInput = screen.getByTestId('trash-search-input');
    fireEvent.change(searchInput, { target: { value: 'Architecture' } });
    fireEvent.keyDown(searchInput, { key: 'Enter' });
    const searchBtn = screen.getByTestId('trash-search-btn');
    fireEvent.click(searchBtn);
    await waitFor(() => {
      expect(requestedQuery).toBe('Architecture');
    });
  });

  it('handles item restoration and 2-stage permanent purge in Workspace Trash Studio (KAN-30)', async () => {
    let restoredId: string | null = null;
    let purgeRequestedId: string | null = null;
    let purgeExecutedToken: string | null = null;
    let lastStage1Body: Record<string, unknown> | null = null;
    let lastStage2Body: Record<string, unknown> | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', trash_retention_days: 30 };
      }
      if (path.includes('/api/v1/admin/trash') && path.includes(':restore') && m === 'POST') {
        const match = /\/admin\/trash\/([^:]+):restore/.exec(path);
        restoredId = match ? (match[1] ?? null) : null;
        return { status: 'restored', target_id: restoredId };
      }
      if (path.includes('/api/v1/admin/trash') && m === 'GET') {
        return {
          items: [
            {
              id: 'trash-item-1',
              kind: 'project',
              key: 'PROJ',
              title: 'Project To Purge',
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 28,
            },
          ],
          retention_days: 30,
          total: 1,
        };
      }
      if (path.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        const bodyVal = options && 'body' in options ? options.body : undefined;
        const parsed = typeof bodyVal === 'string'
          ? (JSON.parse(bodyVal) as Record<string, unknown>)
          : ((bodyVal as Record<string, unknown> | undefined) ?? {});
        lastStage1Body = parsed;
        purgeRequestedId = String(parsed.target);
        return {
          stage: 'requested',
          target: String(parsed.target),
          target_kind: String(parsed.target_kind),
          target_id: String(parsed.target),
          mode: 'permanent_purge',
          blast_summary: 'Target permanently deleted',
          blast_hash: 'blast-hash-789',
          confirm_phrase: 'PURGE PROJECT PROJ',
          confirmation_token: 'token-xyz-123',
          expires_in_sec: 300,
        };
      }
      if (path.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        const bodyVal = options && 'body' in options ? options.body : undefined;
        const parsed = typeof bodyVal === 'string'
          ? (JSON.parse(bodyVal) as Record<string, unknown>)
          : ((bodyVal as Record<string, unknown> | undefined) ?? {});
        lastStage2Body = parsed;
        purgeExecutedToken = String(parsed.confirmation_token);
        return {
          status: 'purged',
          target: String(parsed.target),
          target_kind: String(parsed.target_kind),
          target_id: String(parsed.target),
          mode: 'permanent_purge',
          reason: String(parsed.reason),
          blast_hash: 'blast-hash-789',
        };
      }
      return [];
    });

    renderComponent();

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByTestId('trash-items-table')).toBeDefined();

    // 1. Restore item
    const restoreBtn = screen.getByTestId('restore-btn-trash-item-1');
    fireEvent.click(restoreBtn);

    await waitFor(() => {
      expect(restoredId).toBe('trash-item-1');
      expect(screen.getByText('Restored Project To Purge successfully.')).toBeDefined();
    });

    // 2. Permanent Purge (Stage 1 Request)
    const purgeBtn = screen.getByTestId('permanent-purge-btn-trash-item-1');
    fireEvent.click(purgeBtn);

    await waitFor(() => {
      expect(purgeRequestedId).toBe('trash-item-1');
      expect(screen.getByTestId('permanent-purge-confirmation-dialog')).toBeDefined();
    });

    // Assert exact Stage 1 body (DestructiveRequestIn)
    expect(lastStage1Body).toEqual({
      target_kind: 'project',
      target: 'trash-item-1',
      mode: 'permanent_purge',
    });
    expect(screen.getByTestId('permanent-purge-confirm-phrase').textContent).toContain('PURGE PROJECT PROJ');

    // 3. Permanent Purge (Stage 2 Confirm)
    const confirmPurgeBtn = screen.getByTestId('confirm-permanent-purge-btn');
    expect(confirmPurgeBtn.hasAttribute('disabled')).toBe(true);

    // Attempt premature click while empty (covers line 485 guard)
    fireEvent.click(confirmPurgeBtn);

    const phraseInput = screen.getByTestId('permanent-purge-confirm-phrase-input');
    fireEvent.change(phraseInput, { target: { value: 'PURGE PROJECT PROJ' } });
    expect(confirmPurgeBtn.hasAttribute('disabled')).toBe(true);

    // Attempt click with short reason < 8 chars (covers line 485 second branch)
    const reasonInput = screen.getByTestId('permanent-purge-reason-input');
    fireEvent.change(reasonInput, { target: { value: 'short' } });
    fireEvent.click(confirmPurgeBtn);
    expect(confirmPurgeBtn.hasAttribute('disabled')).toBe(true);

    fireEvent.change(reasonInput, { target: { value: 'Compliance retention expired' } });
    expect(confirmPurgeBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmPurgeBtn);

    await waitFor(() => {
      expect(purgeExecutedToken).toBe('token-xyz-123');
      expect(screen.getByText('Permanently purged Project To Purge.')).toBeDefined();
    });

    // Assert exact Stage 2 body (DestructiveExecuteIn)
    expect(lastStage2Body).toEqual({
      target_kind: 'project',
      target: 'trash-item-1',
      mode: 'permanent_purge',
      confirmation_token: 'token-xyz-123',
      confirm_phrase: 'PURGE PROJECT PROJ',
      reason: 'Compliance retention expired',
    });
  });

  it('handles trash error states, empty search results, and purge cancellation (KAN-30)', async () => {
    let shouldFailRetention = false;
    let shouldFailRestore = false;
    let shouldFailPurgeRequest = false;
    let shouldFailPurgeExecute = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        if (m === 'PATCH' && shouldFailRetention) {
          throw Object.assign(new Error('Retention save failed.'), { detail: 'Retention save failed.' });
        }
        return { name: 'WS', slug: 'ws', trash_retention_days: 30 };
      }
      if (path.includes('/api/v1/admin/trash') && path.includes(':restore') && m === 'POST') {
        if (shouldFailRestore) {
          throw Object.assign(new Error('Restore failed.'), { detail: 'Restore failed.' });
        }
        return { status: 'restored' };
      }
      if (path.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        if (shouldFailPurgeRequest) {
          throw Object.assign(new Error('Purge request failed.'), { detail: 'Purge request failed.' });
        }
        return {
          confirmation_token: 'token-err-1',
          blast_hash: 'blast-err-1',
          target_id: 'trash-err-1',
        };
      }
      if (path.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        if (shouldFailPurgeExecute) {
          throw Object.assign(new Error('Purge execute failed.'), { detail: 'Purge execute failed.' });
        }
        return { status: 'purged' };
      }
      if (path.includes('/api/v1/admin/trash') && m === 'GET') {
        return {
          items: [
            {
              id: 'trash-err-1',
              kind: 'issue',
              key: 'ERR-1',
              title: 'Error Test Item',
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 10,
            },
          ],
          retention_days: 30,
          total: 1,
        };
      }
      return [];
    });

    renderComponent();

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByTestId('trash-items-table')).toBeDefined();

    // 1. Retention update error
    shouldFailRetention = true;
    const saveRetentionBtn = screen.getByTestId('save-trash-retention-btn');
    fireEvent.click(saveRetentionBtn);
    await waitFor(() => {
      expect(screen.getByText('Retention save failed.')).toBeDefined();
    });

    // 2. Restore error
    shouldFailRestore = true;
    const restoreBtn = screen.getByTestId('restore-btn-trash-err-1');
    fireEvent.click(restoreBtn);
    await waitFor(() => {
      expect(screen.getByText('Restore failed.')).toBeDefined();
    });

    // 3. Purge request error
    shouldFailPurgeRequest = true;
    const purgeBtn = screen.getByTestId('permanent-purge-btn-trash-err-1');
    fireEvent.click(purgeBtn);
    await waitFor(() => {
      expect(screen.getByText('Purge request failed.')).toBeDefined();
    });

    // 4. Purge cancellation
    shouldFailPurgeRequest = false;
    fireEvent.click(purgeBtn);
    expect(await screen.findByTestId('permanent-purge-confirmation-dialog')).toBeDefined();
    const cancelPurgeBtn = screen.getByTestId('cancel-permanent-purge-btn');
    fireEvent.click(cancelPurgeBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('permanent-purge-confirmation-dialog')).toBeNull();
    });

    // 5. Purge execute error
    shouldFailPurgeExecute = true;
    fireEvent.click(purgeBtn);
    expect(await screen.findByTestId('permanent-purge-confirmation-dialog')).toBeDefined();
    fireEvent.change(screen.getByTestId('permanent-purge-confirm-phrase-input'), {
      target: { value: 'PURGE ISSUE ERR-1' },
    });
    fireEvent.change(screen.getByTestId('permanent-purge-reason-input'), {
      target: { value: 'Reason for error test execution' },
    });
    const confirmPurgeBtn = screen.getByTestId('confirm-permanent-purge-btn');
    expect(confirmPurgeBtn.hasAttribute('disabled')).toBe(false);
    fireEvent.click(confirmPurgeBtn);
    await waitFor(() => {
      expect(screen.getByText('Purge execute failed.')).toBeDefined();
    });
  });

  it('handles empty trash items response and load failure (KAN-30)', async () => {
    let shouldFailTrashLoad = false;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', trash_retention_days: 30 };
      }
      if (path.includes('/api/v1/admin/trash') && m === 'GET') {
        if (shouldFailTrashLoad) {
          throw Object.assign(new Error(''), { detail: undefined, message: undefined });
        }
        return { items: [], total: 0 };
      }
      return [];
    });

    renderComponent();

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    // Empty state rendered
    expect(await screen.findByTestId('trash-empty-state')).toBeDefined();
    expect(screen.getByText('No trashed items in this workspace.')).toBeDefined();

    // Trigger load error with empty error object (covers fallback error string)
    shouldFailTrashLoad = true;
    const searchBtn = screen.getByTestId('trash-search-btn');
    fireEvent.click(searchBtn);
    await waitFor(() => {
      expect(screen.getByText('Failed to load trashed items.')).toBeDefined();
    });
  });

  it('covers remaining defensive branches in WorkspaceSettingsPage (KAN-30)', async () => {
    // 1. Hash change with invalid tab
    window.location.hash = '#invalid-tab-xyz';
    fireEvent(window, new HashChangeEvent('hashchange'));

    // 2. ensureSessionCsrfToken returning null
    vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue(null);

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: true, is_workspace_admin: true };
      }
      if (path.includes('/api/v1/admin/workspace-settings')) {
        return { name: 'WS', slug: 'ws', trash_retention_days: 30 };
      }
      if (path.includes('/api/v1/admin/trash') && path.includes(':restore') && m === 'POST') {
        return { status: 'restored' };
      }
      if (path.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        return { confirmation_token: 'tok-1', blast_hash: 'hash-1' };
      }
      if (path.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        return { status: 'purged' };
      }
      if (path.includes('/api/v1/admin/trash') && m === 'GET') {
        return {
          items: [
            {
              id: 'trash-bare-1',
              kind: 'issue',
              key: 'BARE-1',
              title: null,
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 5,
            },
            {
              id: 'trash-bare-2',
              kind: 'doc',
              key: null,
              title: null,
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 5,
            },
          ],
          retention_days: 30,
          total: 2,
        };
      }
      return [];
    });

    renderComponent();

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByTestId('trash-items-table')).toBeDefined();

    // Search input keydown non-Enter (e.g. Tab)
    const searchInput = screen.getByTestId('trash-search-input');
    fireEvent.keyDown(searchInput, { key: 'Tab' });

    // Restore item with key only (no title)
    const restoreBtn1 = screen.getByTestId('restore-btn-trash-bare-1');
    fireEvent.click(restoreBtn1);
    await waitFor(() => {
      expect(screen.getByText('Restored BARE-1 successfully.')).toBeDefined();
    });

    // Restore item with neither title nor key (falls back to kind)
    const restoreBtn2 = screen.getByTestId('restore-btn-trash-bare-2');
    fireEvent.click(restoreBtn2);
    await waitFor(() => {
      expect(screen.getByText('Restored doc successfully.')).toBeDefined();
    });

    // Purge item with key only (no title)
    const purgeBtn1 = screen.getByTestId('permanent-purge-btn-trash-bare-1');
    fireEvent.click(purgeBtn1);
    expect(await screen.findByTestId('permanent-purge-confirmation-dialog')).toBeDefined();
    fireEvent.change(screen.getByTestId('permanent-purge-confirm-phrase-input'), {
      target: { value: 'PURGE ISSUE BARE-1' },
    });
    fireEvent.change(screen.getByTestId('permanent-purge-reason-input'), {
      target: { value: 'Permanent purge reason 1' },
    });
    const confirmBtn = screen.getByTestId('confirm-permanent-purge-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(screen.getByText('Permanently purged BARE-1.')).toBeDefined();
    });

    // Purge item with neither title nor key
    const purgeBtn2 = screen.getByTestId('permanent-purge-btn-trash-bare-2');
    fireEvent.click(purgeBtn2);
    expect(await screen.findByTestId('permanent-purge-confirmation-dialog')).toBeDefined();
    fireEvent.change(screen.getByTestId('permanent-purge-confirm-phrase-input'), {
      target: { value: 'PURGE DOC trash-bare-2' },
    });
    fireEvent.change(screen.getByTestId('permanent-purge-reason-input'), {
      target: { value: 'Permanent purge reason 2' },
    });
    fireEvent.click(screen.getByTestId('confirm-permanent-purge-btn'));
    await waitFor(() => {
      expect(screen.getByText('Permanently purged doc.')).toBeDefined();
    });
  });

  it('allows PROJECT_ADMIN users scoped access to Workspace Trash Studio (KAN-30)', async () => {
    let restoredId: string | null = null;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const m = method.toUpperCase();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: false, is_workspace_admin: false, is_project_admin: true };
      }
      if (path.includes('/api/v1/admin/trash') && path.includes(':restore') && m === 'POST') {
        restoredId = 'proj-item-1';
        return { status: 'restored' };
      }
      if (path.includes('/api/v1/admin/trash') && m === 'GET') {
        return {
          items: [
            {
              id: 'proj-item-1',
              kind: 'issue',
              key: 'PROJ-1',
              title: 'Project Admin Trashed Item',
              deleted_at: '2026-11-19T10:00:00Z',
              remaining_days: 15,
            },
          ],
          retention_days: 30,
          total: 1,
        };
      }
      return [];
    });

    renderComponent();

    // Studio rendered without access denied
    expect(await screen.findByTestId('workspace-trash-studio')).toBeDefined();
    expect(screen.queryByTestId('access-denied-message')).toBeNull();

    // Only trash tab rendered; general, members, groups are hidden
    expect(screen.getByTestId('tab-trash')).toBeDefined();
    expect(screen.queryByTestId('tab-general')).toBeNull();
    expect(screen.queryByTestId('tab-members')).toBeNull();
    expect(screen.queryByTestId('tab-groups')).toBeNull();

    // Retention policy card is visible, but edit controls (input and save button) are hidden
    expect(screen.getByTestId('workspace-trash-retention-card')).toBeDefined();
    expect(screen.queryByTestId('workspace-trash-retention-input-trash-tab')).toBeNull();
    expect(screen.queryByTestId('save-trash-retention-btn')).toBeNull();

    // Trashed items table and restore button are available
    expect(await screen.findByTestId('trash-items-table')).toBeDefined();
    expect(screen.getByText('Project Admin Trashed Item')).toBeDefined();
    const restoreBtn = screen.getByTestId('restore-btn-proj-item-1');
    expect(restoreBtn).toBeDefined();

    // Permanent Purge button is strictly forbidden (SERVER_ADMIN only)
    expect(screen.queryByTestId('permanent-purge-btn-proj-item-1')).toBeNull();

    // Can restore item
    fireEvent.click(restoreBtn);
    await waitFor(() => {
      expect(restoredId).toBe('proj-item-1');
      expect(screen.getByText('Restored Project Admin Trashed Item successfully.')).toBeDefined();
    });
  });

  it('denies access to standard non-project-admin members (KAN-30)', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: false, is_workspace_admin: false, is_project_admin: false };
      }
      if (path.includes('/api/v1/admin/trash')) {
        throw Object.assign(new Error('Forbidden'), { detail: 'Forbidden' });
      }
      return [];
    });

    renderComponent();

    expect(await screen.findByTestId('access-denied-message')).toBeDefined();
    expect(screen.getByText('You do not have administrative privileges to manage this workspace.')).toBeDefined();
    expect(screen.queryByTestId('workspace-trash-studio')).toBeNull();
  });

  it('covers probe GET /api/v1/admin/trash on #tab-trash for project admins and probe rejection (KAN-30)', async () => {
    // 1. Probe succeeds
    window.location.hash = '#tab-trash';
    let probed = false;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: false, is_workspace_admin: false };
      }
      if (path.includes('/api/v1/admin/trash')) {
        probed = true;
        return { items: [], retention_days: 20 };
      }
      return [];
    });

    const { unmount } = renderComponent();
    expect(await screen.findByTestId('workspace-trash-studio')).toBeDefined();
    expect(probed).toBe(true);

    // Click tab-trash while isProjectAdminOnly is true
    fireEvent.click(screen.getByTestId('tab-trash'));
    unmount();

    // 2. Probe throws on #tab-trash
    window.location.hash = '#tab-trash';
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: false, is_workspace_admin: false };
      }
      if (path.includes('/api/v1/admin/trash')) {
        throw Object.assign(new Error('Forbidden'), { detail: 'Forbidden' });
      }
      return [];
    });

    const { unmount: unmount2 } = renderComponent();
    expect(await screen.findByTestId('access-denied-message')).toBeDefined();
    unmount2();

    // 3. Probe returns empty object (neither items array nor retention_days)
    window.location.hash = '#tab-trash';
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/api/v1/auth/me')) {
        return { is_server_admin: false, is_workspace_admin: false };
      }
      if (path.includes('/api/v1/admin/trash')) {
        return {};
      }
      return [];
    });

    renderComponent();
    expect(await screen.findByTestId('access-denied-message')).toBeDefined();
  });

  it('collapses TTL overrides and field-level override rules under AdvancedSection (KAN-370)', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
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
          name: 'Acme Corp',
          slug: 'acme-corp',
          display_name: 'Acme Public',
          default_project_visibility: 'workspace',
          session_idle_timeout_min: 120,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
          mcp_key_max_ttl_days: 90,
          air_gap_mode: false,
          issue_export_enabled: true,
          issue_export_allowed_roles: ['workspace_admin', 'project_admin'],
        };
      }
      return [];
    });

    renderComponent();

    // Click roles tab to verify role matrix and cover tab navigation
    const rolesTab = await screen.findByTestId('tab-roles');
    fireEvent.click(rolesTab);
    expect(await screen.findByTestId('workspace-roles-section')).toBeDefined();

    // Switch back to general tab
    fireEvent.click(screen.getByTestId('tab-general'));

    // Primary fields remain visible by default
    expect(await screen.findByTestId('workspace-name-input')).toBeDefined();
    expect(screen.getByTestId('workspace-slug-input')).toBeDefined();
    expect(screen.getByTestId('workspace-display-name-input')).toBeDefined();
    expect(screen.getByTestId('workspace-visibility-select')).toBeDefined();

    // AdvancedSection is present and collapsed by default
    const advSection = await screen.findByTestId('workspace-advanced-security-section');
    expect(advSection).toBeDefined();
    expect(advSection.hasAttribute('open')).toBe(false);

    // TTL overrides and field-level override rules exist inside AdvancedSection
    expect(within(advSection).getByTestId('workspace-field-level-overrides')).toBeDefined();
    expect(within(advSection).getByTestId('workspace-idle-timeout-input')).toBeDefined();
    expect(within(advSection).getByTestId('workspace-abs-timeout-input')).toBeDefined();
    expect(within(advSection).getByTestId('workspace-webhook-restrictions')).toBeDefined();

    // Toggle button expands the section
    const toggleBtn = screen.getByTestId('workspace-advanced-security-section-toggle');
    fireEvent.click(toggleBtn);
    expect(advSection.hasAttribute('open')).toBe(true);

    // Toggle again collapses the section
    fireEvent.click(toggleBtn);
    expect(advSection.hasAttribute('open')).toBe(false);
  });

  it('renders trademark-free copy for CSV and password-protected ZIP export/import governance toggles (KAN-373)', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return {
          id: 'ws-123',
          name: 'Main Workspace',
          slug: 'main-ws',
          issue_export_enabled: true,
          issue_import_enabled: true,
        };
      }
      return [];
    });

    renderComponent();

    expect(
      await screen.findByText(
        'Enable Issue Export (Allow exporting issues to CSV / Password-Protected ZIP)',
      ),
    ).toBeDefined();
    expect(
      screen.getByText(
        'Enable Issue Import (Allow importing issues from CSV / Password-Protected ZIP)',
      ),
    ).toBeDefined();
    expect(screen.queryByText(/WinZip/i)).toBeNull();
  });
});
