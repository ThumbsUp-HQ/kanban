// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { ProjectSettingsPage } from '../ProjectSettingsPage';
import * as clientModule from '../../../api/client';

describe('ProjectSettingsPage (KANBA-202)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = (projectKey = 'KAN') =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/projects/${projectKey}/settings`]}>
          <ProjectSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('renders project settings page tabs and switches between them', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [
          {
            id: 'member-1',
            principal_id: 'user-1',
            principal_type: 'USER',
            role: 'PROJECT_ADMIN',
            display_name: 'Alice Admin',
            handle: 'alice',
            avatar_url: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          description: 'Primary platform project',
          modules_enabled: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    expect(await screen.findByTestId('project-settings-page')).toBeDefined();
    expect(screen.getByRole('heading', { level: 1 })).toBeDefined();

    // Verify tabs
    const generalTab = screen.getByTestId('tab-general');
    const membersTab = screen.getByTestId('tab-members');
    const integrationsTab = screen.getByTestId('tab-integrations');
    const dangerTab = screen.getByTestId('tab-danger');

    expect(generalTab).toBeDefined();
    expect(membersTab).toBeDefined();
    expect(integrationsTab).toBeDefined();
    expect(dangerTab).toBeDefined();

    // General tab content
    expect(await screen.findByDisplayValue('Kanban Platform')).toBeDefined();

    // Switch to Members & Access
    fireEvent.click(membersTab);
    expect(await screen.findByText('Alice Admin')).toBeDefined();

    // Switch to Automation & Integrations
    fireEvent.click(integrationsTab);
    expect(screen.getByText('Workflows & States')).toBeDefined();

    // Switch to Danger Zone
    fireEvent.click(dangerTab);
    expect(screen.getByText('Move Project to Trash')).toBeDefined();
    expect(screen.getByTestId('request-delete-btn')).toBeDefined();
  });

  it('allows adding and removing project members with role selection', async () => {
    let membersList = [
      {
        id: 'member-1',
        principal_id: 'user-1',
        principal_type: 'USER',
        role: 'PROJECT_ADMIN',
        display_name: 'Alice Admin',
        handle: 'alice',
        avatar_url: null,
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return membersList;
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as { principal_id: string; role: string };
        const newMember = {
          id: 'member-2',
          principal_id: body.principal_id,
          principal_type: 'USER',
          role: body.role,
          display_name: 'Bob Builder',
          handle: 'bob',
          avatar_url: null,
        };
        membersList = [...membersList, newMember];
        return newMember;
      }
      if (url.includes('/api/v1/projects/KAN/members/') && m === 'DELETE') {
        membersList = membersList.filter((mem) => !url.includes(mem.principal_id));
        return {};
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    // Switch to members tab
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    expect(await screen.findByText('Alice Admin')).toBeDefined();

    // Add member
    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.change(input, { target: { value: 'user-2' } });

    const roleSelect = screen.getByTestId('member-role-select');
    fireEvent.change(roleSelect, { target: { value: 'VIEWER' } });

    const addBtn = screen.getByTestId('add-member-submit-btn');
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByText('Bob Builder')).toBeDefined();
    });

    // Remove member
    const removeBtn = screen.getByTestId('remove-member-user-2');
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(screen.queryByText('Bob Builder')).toBeNull();
    });
  });

  it('updates general project settings with form submission', async () => {
    let updatedPayload: Record<string, unknown> | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Old Project Name',
          description: 'Old Description',
          modules_enabled: false,
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'PATCH') {
        updatedPayload = JSON.parse(String((options as { body?: string }).body)) as Record<
          string,
          unknown
        >;
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: updatedPayload.name,
          description: updatedPayload.description_markdown,
          modules_enabled: updatedPayload.modules_enabled,
          auto_archive_days: updatedPayload.auto_archive_days,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    expect(await screen.findByDisplayValue('Old Project Name')).toBeDefined();

    // Modify form values
    const nameInput = screen.getByTestId('project-name-input');
    fireEvent.change(nameInput, { target: { value: 'New Platform Name' } });

    const descInput = screen.getByTestId('project-desc-input');
    fireEvent.change(descInput, { target: { value: 'Updated markdown description' } });

    const modulesCheckbox = screen.getByTestId('project-modules-checkbox');
    fireEvent.click(modulesCheckbox);

    const autoArchiveInput = screen.getByTestId('project-auto-archive-input');
    fireEvent.change(autoArchiveInput, { target: { value: '30' } });

    const saveBtn = screen.getByTestId('save-general-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Project settings saved successfully.')).toBeDefined();
    });

    expect(updatedPayload).toEqual({
      name: 'New Platform Name',
      description_markdown: 'Updated markdown description',
      modules_enabled: true,
      auto_archive_days: 30,
    });
  });

  it('triggers access inspector custom event', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({
      id: 'p-1',
      identifier: 'KAN',
      name: 'Kanban Platform',
      is_project_admin: true,
    });

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    renderComponent('KAN');

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    const inspectBtn = await screen.findByTestId('inspect-access-btn');
    fireEvent.click(inspectBtn);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'kb:open-access-inspector',
        detail: { objectId: 'p-1', title: 'Kanban Platform' },
      }),
    );
  });

  it('handles 2-stage project deletion with blast radius confirmation and cancellation', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        return {
          confirmation_token: 'token-xyz-123',
          confirm_phrase: 'DELETE KAN FOREVER',
          blast_hash: 'hash-abc-789',
          blast_summary: {
            issues_count: 42,
            pages_count: 5,
            stickies_count: 12,
          },
        };
      }
      if (url.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        return { ok: true, message: 'Deleted' };
      }
      return {};
    });

    renderComponent('KAN');

    // Switch to Danger Zone
    const dangerTab = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab);

    // Stage 1: Request Deletion
    const requestBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(requestBtn);

    // Verify blast radius and confirm phrase prompt
    expect(await screen.findByText('Stage 2: Confirm Project Deletion')).toBeDefined();
    expect(screen.getByText('Work Items: 42')).toBeDefined();
    expect(screen.getByText('Docs / Pages: 5')).toBeDefined();
    expect(screen.getByText('Stickies: 12')).toBeDefined();

    // Confirm button is initially disabled
    const executeBtn = screen.getByTestId('execute-delete-btn');
    expect(executeBtn.hasAttribute('disabled')).toBe(true);

    // Test Cancel button resets back to idle
    const cancelBtn = screen.getByTestId('cancel-delete-btn');
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('danger-confirm-card')).toBeNull();
    expect(screen.getByTestId('request-delete-btn')).toBeDefined();

    // Re-request and complete deletion
    fireEvent.click(screen.getByTestId('request-delete-btn'));
    expect(await screen.findByTestId('confirm-phrase-input')).toBeDefined();

    const phraseInput = screen.getByTestId('confirm-phrase-input');
    fireEvent.change(phraseInput, { target: { value: 'DELETE KAN FOREVER' } });

    const confirmExecuteBtn = screen.getByTestId('execute-delete-btn');
    expect(confirmExecuteBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmExecuteBtn);

    await waitFor(() => {
      expect(clientModule.apiFetch).toHaveBeenCalledWith(
        'POST',
        '/api/v1/admin/destructive:execute',
        expect.objectContaining({
          body: JSON.stringify({
            confirmation_token: 'token-xyz-123',
            confirm_phrase: 'DELETE KAN FOREVER',
            blast_hash: 'hash-abc-789',
          }),
        }),
      );
    });
  });

  it('handles project settings load failure gracefully', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValue(new Error('Project not found'));

    renderComponent('KAN');

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });
  });

  it('handles PATCH error and null auto_archive_days when saving general settings', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          auto_archive_days: 14,
        };
      }
      if (m === 'PATCH') {
        throw new Error('Project name invalid');
      }
      return {};
    });

    renderComponent('KAN');

    const saveBtn = await screen.findByTestId('save-general-btn');
    const autoArchiveInput = screen.getByTestId('project-auto-archive-input');
    fireEvent.change(autoArchiveInput, { target: { value: '' } });

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Project name invalid')).toBeDefined();
    });
  });

  it('handles empty input, add member error, and remove member error on members tab', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [
          {
            id: 'mem-fallback',
            principal_id: 'user-fallback-id',
            principal_type: 'USER',
            role: 'PROJECT_MEMBER',
            display_name: null,
            handle: null,
            email: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          capabilities: ['ADMIN'],
        };
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'POST') {
        throw new Error('User already in project');
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'DELETE') {
        throw new Error('Cannot remove last admin');
      }
      return {};
    });

    renderComponent('KAN');

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Fallback shows principal_id when display_name and handle are null
    expect(await screen.findByText('user-fallback-id')).toBeDefined();

    // Empty add does nothing
    fireEvent.click(screen.getByTestId('add-member-submit-btn'));

    // Fill principal ID and submit with error
    fireEvent.change(screen.getByTestId('member-principal-id-input'), { target: { value: 'user-colliding' } });
    fireEvent.click(screen.getByTestId('add-member-submit-btn'));

    await waitFor(() => {
      expect(screen.getByText('User already in project')).toBeDefined();
    });

    // Remove member error
    const removeBtn = screen.getByTestId('remove-member-user-fallback-id');
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(screen.getByText('Cannot remove last admin')).toBeDefined();
    });
  });

  it('handles destructive deletion errors on request and execution stages', async () => {
    let stage = 1;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return { id: 'p-1', identifier: 'KAN', name: 'Kanban Platform', is_project_admin: true };
      }
      if (url.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        if (stage === 1) {
          throw new Error('Insufficient permissions to delete');
        }
        return {
          confirmation_token: 'token-xyz-123',
          confirm_phrase: 'DELETE KAN FOREVER',
          blast_hash: 'hash-abc-789',
          blast_summary: { issues_count: 5, pages_count: 1, stickies_count: 2 },
        };
      }
      if (url.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        throw new Error('Confirmation phrase expired');
      }
      return {};
    });

    renderComponent('KAN');

    const dangerTab = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab);

    // Stage 1 error
    const requestBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(requestBtn);

    await waitFor(() => {
      expect(screen.getByText('Insufficient permissions to delete')).toBeDefined();
    });

    // Advance to stage 2 and trigger execute error
    stage = 2;
    fireEvent.click(screen.getByTestId('request-delete-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('confirm-phrase-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('confirm-phrase-input'), { target: { value: 'DELETE KAN FOREVER' } });
    fireEvent.click(screen.getByTestId('execute-delete-btn'));

    await waitFor(() => {
      expect(screen.getByText('Confirmation phrase expired')).toBeDefined();
    });
  });

  it('covers access inspector event dispatch, { items } members response, and fallback error messages', async () => {
    const inspectorListener = vi.fn();
    window.addEventListener('kb:open-access-inspector', inspectorListener);

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [
          {
            id: 'member-obj-1',
            principal_id: 'user-obj-1',
            principal_type: 'USER',
            role: 'PROJECT_ADMIN',
            display_name: 'Obj Admin',
            handle: 'objadmin',
            avatar_url: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return { id: 'p-1', identifier: 'KAN', name: 'Kanban Platform', is_project_admin: true };
      }
      if (m === 'PATCH') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String PATCH error';
      }
      if (url.includes('/members') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String POST member error';
      }
      if (url.includes('/members') && m === 'DELETE') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String DELETE member error';
      }
      if (url.includes('destructive:request') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'String destructive request error';
      }
      return {};
    });

    renderComponent('KAN');

    // Test General PATCH fallback error
    const saveBtn = await screen.findByTestId('save-general-btn');
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByText('Failed to update project settings.')).toBeDefined();
    });

    // Switch to Members tab
    const membersTab = screen.getByTestId('tab-members');
    fireEvent.click(membersTab);

    // Verify member loaded
    expect(await screen.findByText('Obj Admin')).toBeDefined();

    // Trigger access inspector
    const inspectorBtn = screen.getByTestId('inspect-access-btn');
    fireEvent.click(inspectorBtn);
    expect(inspectorListener).toHaveBeenCalled();

    // Add member with string rejection
    fireEvent.change(screen.getByTestId('member-principal-id-input'), { target: { value: 'user-new' } });
    fireEvent.click(screen.getByTestId('add-member-submit-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to add project member.')).toBeDefined();
    });

    // Remove member with string rejection
    const removeBtn = screen.getByTestId('remove-member-user-obj-1');
    fireEvent.click(removeBtn);
    await waitFor(() => {
      expect(screen.getByText('Failed to remove project member.')).toBeDefined();
    });

    // Switch to Danger tab and test string request error
    const dangerTab = screen.getByTestId('tab-danger');
    fireEvent.click(dangerTab);
    const requestBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(requestBtn);
    await waitFor(() => {
      expect(screen.getByText('Failed to initiate project deletion.')).toBeDefined();
    });

    window.removeEventListener('kb:open-access-inspector', inspectorListener);
  });

  it('covers init failure fallback, empty principal add-member guard, items response, and execute delete fallback', async () => {
    // 1. Init failure with empty errObj.message
    vi.mocked(clientModule.apiFetch).mockRejectedValueOnce({});

    render(
      <MemoryRouter initialEntries={['/projects/FAIL/settings']}>
        <ProjectSettingsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });

    cleanup();

    // 2. Members tab with empty principal ID submit and object { items: [...] } response
    vi.mocked(clientModule.apiFetch).mockImplementation((method, path) => {
      if (path.includes('/api/v1/projects/') && !path.includes('/members')) {
        return Promise.resolve({
          id: 'p-prj',
          identifier: 'PRJ',
          name: 'Success Project',
          description_markdown: '',
          modules_enabled: true,
          default_view: 'board',
          is_project_admin: true,
        });
      }
      if (path.includes('/members')) {
        if (method === 'POST') {
          return Promise.resolve({});
        }
        // Return object with items
        return Promise.resolve({
          items: [
            {
              id: 'mem-item-1',
              principal_id: 'user-added',
              principal_type: 'USER',
              display_name: 'Added User',
              handle: 'addeduser',
              role: 'MEMBER',
            },
          ],
        });
      }
      if (path.includes('/destructive:request')) {
        return Promise.resolve({
          confirmation_token: 'token-abc',
          confirm_phrase: 'delete me',
          blast_hash: 'hash-123',
          blast_summary: { issues_count: 5, pages_count: 1, stickies_count: 2 },
          expires_in_sec: 300,
        });
      }
      if (path.includes('/destructive:execute')) {
        // Reject with empty error object (no message property)
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject({});
      }
      return Promise.resolve({});
    });

    render(
      <MemoryRouter initialEntries={['/projects/PRJ/settings']}>
        <ProjectSettingsPage />
      </MemoryRouter>,
    );

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Empty principal ID click is a no-op
    const addBtn = screen.getByTestId('add-member-submit-btn');
    fireEvent.click(addBtn);

    // Type principal ID and submit to exercise { items: [...] } branch
    fireEvent.change(screen.getByTestId('member-principal-id-input'), { target: { value: 'user-added' } });
    fireEvent.click(addBtn);
    await waitFor(() => {
      expect(screen.getByText('Added User')).toBeDefined();
    });

    // Switch to danger tab, request deletion, then execute with empty message rejection
    const dangerTab = screen.getByTestId('tab-danger');
    fireEvent.click(dangerTab);

    const requestBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(requestBtn);

    const phraseInput = await screen.findByTestId('confirm-phrase-input');
    fireEvent.change(phraseInput, { target: { value: 'delete me' } });

    const executeBtn = screen.getByTestId('execute-delete-btn');
    fireEvent.click(executeBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to execute project deletion.')).toBeDefined();
    });
  });
});
