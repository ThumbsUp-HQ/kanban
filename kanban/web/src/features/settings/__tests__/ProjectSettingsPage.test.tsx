// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { ProjectSettingsPage, formatPrincipalHandle } from '../ProjectSettingsPage';
import * as clientModule from '../../../api/client';
import { ApiProblem } from '../../../api/problem';

let csrfToggle = false;
vi.mock('../../auth/useSessionGuard', () => ({
  ensureSessionCsrfToken: vi.fn().mockImplementation(() => {
    csrfToggle = !csrfToggle;
    return csrfToggle ? 'csrf-mock-token-xyz' : null;
  }),
}));

describe('ProjectSettingsPage (KANBA-202)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    HTMLDivElement.prototype.scrollIntoView = vi.fn();
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
      const url: string = path;
      if (url.includes('/api/v1/workspaces') && (url.includes('/ai-providers') || url.includes('/agent-definitions'))) {
        return [];
      }
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

    // Switch back to General
    fireEvent.click(generalTab);
    expect(await screen.findByDisplayValue('Kanban Platform')).toBeDefined();

    // Switch to Automation & Integrations
    fireEvent.click(integrationsTab);
    expect(screen.getByText('Workflows & States')).toBeDefined();

    // Switch to Danger Zone
    fireEvent.click(dangerTab);
    expect(screen.getByText('Move Project to Trash')).toBeDefined();
    expect(screen.getByTestId('request-delete-btn')).toBeDefined();

    // Switch to AI & Agents Tab
    const aiAgentsTab = screen.getByTestId('tab-ai-agents');
    expect(aiAgentsTab).toBeDefined();
    fireEvent.click(aiAgentsTab);
    expect(await screen.findByTestId('project-ai-agents-section')).toBeDefined();
    expect(screen.getByTestId('ai-studio-page')).toBeDefined();
    expect(screen.getByTestId('agent-studio-page')).toBeDefined();
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
      const url: string = path;
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
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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
      skip_loaded_sequence_numbers: false,
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
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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
            target_kind: 'project',
            target: 'KAN',
            mode: 'trash',
            confirmation_token: 'token-xyz-123',
            confirm_phrase: 'DELETE KAN FOREVER',
            reason: 'Project KAN moved to trash via project settings',
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
      const url: string = path;
      const m = method.toUpperCase();
      if (url.includes('/api/v1/workspaces') && (url.includes('/ai-providers') || url.includes('/agent-definitions'))) {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [];
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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
      const url: string = path;
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
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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
      const url: string = path;
      const m = method.toUpperCase();
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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
      const url: string = path;
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
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

  it('covers inspect effective access button and request delete failure', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      if (path.includes('/api/v1/projects/KAN/members')) {
        return Promise.resolve([]);
      }
      if (path.includes('/api/v1/projects/KAN')) {
        return Promise.resolve({
          id: 'prj-1',
          identifier: 'KAN',
          name: 'Project KAN',
          is_project_admin: true,
          capabilities: ['ADMIN', 'PROJECT_ADMIN'],
        });
      }
      if (path.includes('/destructive:request')) {
        return Promise.reject(new Error('Destructive request rejected'));
      }
      return Promise.resolve({});
    });

    const accessEventSpy = vi.fn();
    window.addEventListener('kb:open-access-inspector', accessEventSpy);

    renderComponent('KAN');

    // 1. Members tab -> inspect effective access
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    const inspectBtn = await screen.findByTestId('inspect-access-btn');
    fireEvent.click(inspectBtn);
    expect(accessEventSpy).toHaveBeenCalled();

    // 2. Danger tab -> request delete error
    const dangerTab = screen.getByTestId('tab-danger');
    fireEvent.click(dangerTab);

    const requestBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(requestBtn);

    await waitFor(() => {
      expect(screen.getByText('Destructive request rejected')).toBeDefined();
    });

    window.removeEventListener('kb:open-access-inspector', accessEventSpy);
  });

  it('handles permanent purge flow for server admin with custom reason and string blast summary', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          deleted_at: '2026-11-20T00:00:00Z',
          status: 'trashed',
        };
      }
      if (url.includes('/api/v1/auth/me') && m === 'GET') {
        return { is_server_admin: true };
      }
      if (url.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        return {
          confirmation_token: 'purge-token-999',
          confirm_phrase: 'PURGE KAN FOREVER',
          mode: 'permanent_purge',
          blast_summary: 'All 50 records in project KAN will be irrevocably destroyed',
        };
      }
      if (url.includes('/api/v1/admin/destructive:execute') && m === 'POST') {
        return { ok: true };
      }
      return {};
    });

    renderComponent('KAN');

    const dangerTab = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab);

    // Verify permanent purge button visible for server admin
    const purgeBtn = await screen.findByTestId('request-purge-btn');
    expect(purgeBtn).toBeDefined();

    fireEvent.click(purgeBtn);

    // Verify Stage 2 UI with string summary
    expect(
      await screen.findByText('Stage 2: Confirm PERMANENT Project Purge (IRREVERSIBLE)'),
    ).toBeDefined();
    expect(
      screen.getByText('All 50 records in project KAN will be irrevocably destroyed'),
    ).toBeDefined();

    // Fill phrase and custom reason
    const phraseInput = screen.getByTestId('confirm-phrase-input');
    fireEvent.change(phraseInput, { target: { value: 'PURGE KAN FOREVER' } });

    const reasonInput = screen.getByTestId('danger-reason-input');
    fireEvent.change(reasonInput, {
      target: { value: 'Server admin decommissioned project permanently' },
    });

    const executeBtn = screen.getByTestId('execute-delete-btn');
    expect(executeBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(executeBtn);

    await waitFor(() => {
      expect(clientModule.apiFetch).toHaveBeenCalledWith(
        'POST',
        '/api/v1/admin/destructive:execute',
        expect.objectContaining({
          body: JSON.stringify({
            target_kind: 'project',
            target: 'KAN',
            mode: 'permanent_purge',
            confirmation_token: 'purge-token-999',
            confirm_phrase: 'PURGE KAN FOREVER',
            reason: 'Server admin decommissioned project permanently',
          }),
        }),
      );
    });
  });

  it('manages workflow states: list, add with WIP limits, soft > hard validation, reorder up/down, delete', async () => {
    let stateList: Record<string, unknown>[] = [
      {
        id: 'st-1',
        name: 'Backlog',
        group: 'backlog',
        sort_order: 1,
        color_hex: '#64748b',
        is_default: true,
        wip_soft_limit: 5,
        wip_hard_limit: 10,
      },
      {
        id: 'st-2',
        name: 'In Progress',
        group: 'started',
        sort_order: 2,
        color_hex: '#3b82f6',
        is_default: false,
        wip_soft_limit: null,
        wip_hard_limit: null,
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          name: string;
          group: string;
          color_hex: string;
          sort_order: number;
          is_default: boolean;
          wip_soft_limit: number | null;
          wip_hard_limit: number | null;
        };
        const created = {
          id: 'st-3',
          ...body,
        };
        stateList = [...stateList, created];
        return created;
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'PATCH') {
        const body = JSON.parse(String((options as { body?: string }).body)) as { sort_order: number };
        const id = url.split('/').pop();
        stateList = stateList.map((s) => (s.id === id ? { ...s, sort_order: body.sort_order } : s));
        return { ok: true };
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'DELETE') {
        const id = url.split('/').pop();
        stateList = stateList.filter((s) => s.id !== id);
        return { ok: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    // Verify initial states rendered
    expect(await screen.findByTestId('state-row-st-1')).toBeDefined();
    expect(screen.getByText('In Progress')).toBeDefined();
    expect(screen.getByText('Soft: 5')).toBeDefined();
    expect(screen.getByText('Hard: 10')).toBeDefined();

    // Test Soft WIP > Hard WIP validation
    const nameInput = screen.getByTestId('state-name-input');
    fireEvent.change(nameInput, { target: { value: 'Review' } });

    const softInput = screen.getByTestId('state-wip-soft-input');
    const hardInput = screen.getByTestId('state-wip-hard-input');
    fireEvent.change(softInput, { target: { value: '15' } });
    fireEvent.change(hardInput, { target: { value: '10' } });

    const submitBtn = screen.getByTestId('create-state-btn');
    fireEvent.click(submitBtn);

    expect(await screen.findByTestId('wip-limit-error')).toBeDefined();
    expect(screen.getByText('Soft WIP limit cannot exceed Hard WIP limit')).toBeDefined();

    // Fix WIP limits and submit
    fireEvent.change(softInput, { target: { value: '3' } });
    fireEvent.change(hardInput, { target: { value: '6' } });
    const colorInput = screen.getByTestId('state-color-input');
    fireEvent.change(colorInput, { target: { value: '#10b981' } });
    const orderInput = screen.getByTestId('state-sort-order-input');
    fireEvent.change(orderInput, { target: { value: '3' } });
    const defaultCheckbox = screen.getByTestId('state-default-checkbox');
    fireEvent.click(defaultCheckbox);

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Review')).toBeDefined();
      expect(screen.getByText('Workflow state "Review" created.')).toBeDefined();
    });

    // Test reorder up on st-2
    const upBtn = screen.getByTestId('state-up-st-2');
    fireEvent.click(upBtn);

    // Test reorder down on st-1
    const downBtn = screen.getByTestId('state-down-st-1');
    fireEvent.click(downBtn);

    // Test delete state
    const deleteBtn = screen.getByTestId('delete-state-btn-st-3');
    fireEvent.click(deleteBtn);
    const confirmDeleteBtn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(screen.queryByText('Review')).toBeNull();
      expect(screen.getByText('Workflow state deleted.')).toBeDefined();
    });
  });

  it('manages priorities: list, add, delete, and error handling', async () => {
    let prioList: Record<string, unknown>[] = [
      {
        id: 'prio-1',
        slug: 'high',
        label: 'High Priority',
        emoji: '🔥',
        color_hex: '#dc2626',
        sort_order: 1,
        is_default: true,
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
        return prioList;
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          slug: string;
          label: string;
          emoji: string | null;
          color_hex: string;
          sort_order: number;
          is_default: boolean;
        };
        const created = { id: 'prio-2', ...body };
        prioList = [...prioList, created];
        return created;
      }
      if (url.includes('/api/v1/projects/KAN/priorities/') && m === 'DELETE') {
        prioList = prioList.filter((p) => !url.includes(String(p.id)));
        return { ok: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

    const prioritiesTab = await screen.findByTestId('tab-priorities');
    fireEvent.click(prioritiesTab);

    expect(await screen.findByText('High Priority')).toBeDefined();
    expect(screen.getByText('🔥')).toBeDefined();

    // Empty fields guard
    const submitBtn = screen.getByTestId('create-priority-btn');
    fireEvent.click(submitBtn);

    // Fill valid priority
    fireEvent.change(screen.getByTestId('priority-slug-input'), { target: { value: 'urgent' } });
    fireEvent.change(screen.getByTestId('priority-label-input'), { target: { value: 'Urgent' } });
    fireEvent.change(screen.getByTestId('priority-emoji-input'), { target: { value: '⚡' } });
    fireEvent.change(screen.getByTestId('priority-color-input'), { target: { value: '#f59e0b' } });
    fireEvent.change(screen.getByTestId('priority-sort-order-input'), { target: { value: '2' } });
    fireEvent.click(screen.getByTestId('priority-default-checkbox'));

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Urgent')).toBeDefined();
      expect(screen.getByText('Priority "Urgent" created.')).toBeDefined();
    });

    // Delete priority
    const deleteBtn = screen.getByTestId('delete-priority-btn-prio-1');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.queryByText('High Priority')).toBeNull();
      expect(screen.getByText('Priority deleted.')).toBeDefined();
    });
  });

  it('manages labels: list, add with exclusive group, delete, and error handling', async () => {
    let labelList: Record<string, unknown>[] = [
      {
        id: 'lbl-1',
        name: 'frontend',
        color_hex: '#3b82f6',
        exclusive_group: 'layer',
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return labelList;
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          name: string;
          color_hex: string;
          exclusive_group: string | null;
        };
        const created = { id: 'lbl-2', ...body };
        labelList = [...labelList, created];
        return created;
      }
      if (url.includes('/api/v1/projects/KAN/labels/') && m === 'DELETE') {
        labelList = labelList.filter((l) => !url.includes(String(l.id)));
        return { ok: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

    const labelsTab = await screen.findByTestId('tab-labels');
    fireEvent.click(labelsTab);

    expect(await screen.findByText('frontend')).toBeDefined();
    expect(screen.getByText('layer')).toBeDefined();

    // Empty name guard
    const submitBtn = screen.getByTestId('create-label-btn');
    fireEvent.click(submitBtn);

    // Add label with exclusive group
    fireEvent.change(screen.getByTestId('label-name-input'), { target: { value: 'backend' } });
    fireEvent.change(screen.getByTestId('label-color-input'), { target: { value: '#10b981' } });
    fireEvent.change(screen.getByTestId('label-exclusive-group-input'), {
      target: { value: 'layer' },
    });

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('backend')).toBeDefined();
      expect(screen.getByText('Label "backend" created.')).toBeDefined();
    });

    // Delete label
    const deleteBtn = screen.getByTestId('delete-label-btn-lbl-1');
    fireEvent.click(deleteBtn);
    const confirmDeleteBtn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(screen.queryByText('frontend')).toBeNull();
      expect(screen.getByText('Label deleted.')).toBeDefined();
    });
  });

  it('supports searchable principal picker autocomplete and selection', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'user-uuid-1',
            display_name: 'Carol Danvers',
            handle: 'carol',
            principal_type: 'USER',
          },
          {
            id: 'group-uuid-1',
            display_name: 'Security Ops',
            handle: 'secops',
            principal_type: 'GROUP',
          },
          {
            id: 'agent-uuid-1',
            display_name: 'CI Guard Bot',
            handle: 'cibot',
            principal_type: 'AGENT',
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [];
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'cibot' } });
    expect(await screen.findByTestId('principal-option-agent-uuid-1')).toBeDefined();

    fireEvent.change(input, { target: { value: 'Security' } });

    // Dropdown should be open and filter to Security Ops
    expect(await screen.findByTestId('principal-picker-dropdown')).toBeDefined();
    const groupOption = screen.getByTestId('principal-option-group-uuid-1');
    expect(groupOption).toBeDefined();
    expect(screen.getByText('👥')).toBeDefined();

    // Click option
    fireEvent.click(groupOption);

    // Verify input updated with selected principal
    expect((input as HTMLInputElement).value).toBe('Security Ops');
    expect(screen.queryByTestId('principal-picker-dropdown')).toBeNull();
  });

  it('manages default modules selection in general tab and persists to endpoint', async () => {
    let savedModuleDefaults: string[] = [];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/modules') && m === 'GET') {
        return [
          { id: 'mod-1', name: 'Auth Module', status: 'in_progress' },
          { id: 'mod-2', name: 'Billing Module', status: 'planned' },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/module-defaults') && m === 'PUT') {
        const body = JSON.parse(String((options as { body?: string }).body)) as {
          module_ids: string[];
        };
        savedModuleDefaults = body.module_ids;
        return { ok: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          modules_enabled: true,
          default_module_ids: ['mod-1'],
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'PATCH') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          modules_enabled: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    expect(await screen.findByTestId('default-modules-section')).toBeDefined();
    expect(screen.getByText('🧩 Auth Module')).toBeDefined();

    const mod1Checkbox = screen.getByTestId<HTMLInputElement>('default-module-mod-1');
    const mod2Checkbox = screen.getByTestId<HTMLInputElement>('default-module-mod-2');

    expect(mod1Checkbox.checked).toBe(true);
    expect(mod2Checkbox.checked).toBe(false);

    // Toggle mod-2 on, mod-1 off
    fireEvent.click(mod2Checkbox);
    fireEvent.click(mod1Checkbox);

    expect(mod1Checkbox.checked).toBe(false);
    expect(mod2Checkbox.checked).toBe(true);

    // Save
    const saveBtn = screen.getByTestId('save-general-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(savedModuleDefaults).toEqual(['mod-2']);
    });
  });

  it('manages project trash & retention: list, filter by kind, 1-click restore, and fallback endpoint', async () => {
    let trashList = [
      {
        id: 'tr-issue-1',
        key: 'KAN-99',
        kind: 'issue',
        title: 'Broken Pipeline Bug',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-12-10T12:00:00Z',
        remaining_days: 15,
      },
      {
        id: 'tr-cycle-1',
        key: 'cycle-uuid-1',
        kind: 'cycle',
        title: '',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-11-12T12:00:00Z',
        remaining_days: 2,
      },
      {
        id: 'tr-mod-1',
        key: 'mod-uuid-1',
        kind: 'module',
        title: 'Payment Gateway',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-11-10T12:00:00Z',
        remaining_days: 0,
      },
      {
        id: 'tr-stk-1',
        key: 'stk-uuid-1',
        kind: 'sticky',
        title: 'Meeting Notes',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-12-10T12:00:00Z',
        remaining_days: 20,
      },
      {
        id: 'tr-doc-1',
        key: 'doc-uuid-1',
        kind: 'doc',
        title: 'Architecture Spec',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-12-10T12:00:00Z',
        remaining_days: 25,
      },
      {
        id: 'tr-oth-1',
        key: 'view-uuid-1',
        kind: 'view',
        title: 'Backlog Grid View',
        deleted_at: '2026-11-10T12:00:00Z',
        purge_after: '2026-12-10T12:00:00Z',
        remaining_days: 10,
      },
    ];

    let issueRestoreCalled = false;
    let destructiveRestoreCalled = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/trash-items') && m === 'GET') {
        return { items: trashList };
      }
      if (url.includes('/api/v1/issues/KAN-99/restore') && m === 'POST') {
        issueRestoreCalled = true;
        trashList = trashList.filter((t) => t.key !== 'KAN-99');
        return { ok: true };
      }
      if (url.includes('/api/v1/admin/destructive:restore') && m === 'POST') {
        destructiveRestoreCalled = true;
        trashList = trashList.filter((t) => t.key !== 'cycle-uuid-1');
        return { ok: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
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

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    // Verify all items rendered
    expect(await screen.findByText('Broken Pipeline Bug')).toBeDefined();
    expect(screen.getByText('cycle-uuid-1')).toBeDefined();
    expect(screen.getByText('Payment Gateway')).toBeDefined();
    expect(screen.getByText('Meeting Notes')).toBeDefined();
    expect(screen.getByText('Architecture Spec')).toBeDefined();
    expect(screen.getByText('Backlog Grid View')).toBeDefined();

    // Verify expired pill
    expect(screen.getByText('Expires today')).toBeDefined();
    expect(screen.getByText('15 days remaining')).toBeDefined();

    // Test filtering by kind
    const filterCycle = screen.getByTestId('trash-filter-cycle');
    fireEvent.click(filterCycle);

    expect(screen.getByText('cycle-uuid-1')).toBeDefined();
    expect(screen.queryByText('Broken Pipeline Bug')).toBeNull();

    const filterAll = screen.getByTestId('trash-filter-all');
    fireEvent.click(filterAll);
    expect(screen.getByText('Broken Pipeline Bug')).toBeDefined();

    // 1-Click Restore issue
    const restoreIssueBtn = screen.getByTestId('restore-btn-tr-issue-1');
    fireEvent.click(restoreIssueBtn);

    await waitFor(() => {
      expect(issueRestoreCalled).toBe(true);
      expect(screen.getByText('Successfully restored Broken Pipeline Bug.')).toBeDefined();
    });

    // 1-Click Restore cycle (exercises destructive:restore)
    const restoreCycleBtn = screen.getByTestId('restore-btn-tr-cycle-1');
    fireEvent.click(restoreCycleBtn);

    await waitFor(() => {
      expect(destructiveRestoreCalled).toBe(true);
      expect(screen.getByText('Successfully restored cycle-uuid-1.')).toBeDefined();
    });
  });

  it('handles error states on workflow states, priorities, labels, and trash restore', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return [
          {
            id: 'st-fail',
            name: 'Failing State',
            group: 'started',
            sort_order: 1,
            color_hex: '#111',
          },
          {
            id: 'st-other',
            name: 'Other State',
            group: 'started',
            sort_order: 2,
            color_hex: '#222',
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
        return [
          {
            id: 'prio-fail',
            slug: 'fail',
            label: 'Failing Prio',
            color_hex: '#111',
            sort_order: 1,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return [{ id: 'lbl-fail', name: 'fail-lbl', color_hex: '#111' }];
      }
      if (url.includes('/api/v1/projects/KAN/trash-items') && m === 'GET') {
        return {
          items: [
            {
              id: 'tr-fail',
              key: 'KAN-FAIL',
              kind: 'issue',
              title: 'Fail Item',
              deleted_at: '2026-11-10T12:00:00Z',
              purge_after: '2026-12-10T12:00:00Z',
              remaining_days: 5,
            },
          ],
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'POST') {
        throw new Error('State limit reached');
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'PATCH') {
        throw new Error('Reorder conflict');
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'DELETE') {
        throw new Error('Cannot delete active state');
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'POST') {
        throw new Error('Duplicate priority slug');
      }
      if (url.includes('/api/v1/projects/KAN/priorities/') && m === 'DELETE') {
        throw new Error('Cannot delete default priority');
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'POST') {
        throw new Error('Label already exists');
      }
      if (url.includes('/api/v1/projects/KAN/labels/') && m === 'DELETE') {
        throw new Error('Cannot delete label');
      }
      if (url.includes('restore')) {
        throw new Error('Retention expired');
      }
      return {};
    });

    renderComponent('KAN');

    // 1. Workflow states errors
    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    fireEvent.change(screen.getByTestId('state-name-input'), { target: { value: 'New State' } });
    fireEvent.click(screen.getByTestId('create-state-btn'));
    await waitFor(() => {
      expect(screen.getByText('State limit reached')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('state-down-st-fail'));
    await waitFor(() => {
      expect(screen.getByText('Reorder conflict')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-state-btn-st-fail'));
    const confirmStateDeleteBtn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmStateDeleteBtn);
    await waitFor(() => {
      expect(screen.getByText('Cannot delete active state')).toBeDefined();
    });

    // 2. Priorities errors
    const prioritiesTab = screen.getByTestId('tab-priorities');
    fireEvent.click(prioritiesTab);

    fireEvent.change(screen.getByTestId('priority-slug-input'), { target: { value: 'dup' } });
    fireEvent.change(screen.getByTestId('priority-label-input'), { target: { value: 'Duplicate' } });
    fireEvent.click(screen.getByTestId('create-priority-btn'));
    await waitFor(() => {
      expect(screen.getByText('Duplicate priority slug')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-priority-btn-prio-fail'));
    await waitFor(() => {
      expect(screen.getByText('Cannot delete default priority')).toBeDefined();
    });

    // 3. Labels errors
    const labelsTab = screen.getByTestId('tab-labels');
    fireEvent.click(labelsTab);

    fireEvent.change(screen.getByTestId('label-name-input'), { target: { value: 'dup-lbl' } });
    fireEvent.click(screen.getByTestId('create-label-btn'));
    await waitFor(() => {
      expect(screen.getByText('Label already exists')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-label-btn-lbl-fail'));
    const confirmLabelDeleteBtn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmLabelDeleteBtn);
    await waitFor(() => {
      expect(screen.getByText('Cannot delete label')).toBeDefined();
    });

    // 4. Trash restore error
    const trashTab = screen.getByTestId('tab-trash');
    fireEvent.click(trashTab);

    fireEvent.click(screen.getByTestId('restore-btn-tr-fail'));
    await waitFor(() => {
      expect(screen.getByText('Retention expired')).toBeDefined();
    });
  });

  it('covers fallback trash endpoint and empty trash state', async () => {
    let callCount = 0;
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/trash-items')) {
        throw new Error('Not implemented');
      }
      if (url.includes('/api/v1/projects/KAN/trash')) {
        callCount++;
        return {
          items: [
            {
              id: 'fallback-1',
              key: 'KAN-OLD-1',
              summary: 'Old Issue from fallback with summary',
              deleted_at: new Date().toISOString(),
              purge_after: new Date(Date.now() + 86400000 * 5).toISOString(),
            },
            {
              id: 'fallback-2',
              key: 'KAN-OLD-2',
              title: 'Old Issue from fallback with title',
              deleted_at: new Date().toISOString(),
              purge_after: new Date(Date.now() + 86400000 * 5).toISOString(),
            },
            {
              id: 'fallback-3',
              key: 'KAN-OLD-3',
              deleted_at: new Date().toISOString(),
              purge_after: new Date(Date.now() + 86400000 * 5).toISOString(),
            },
          ],
        };
      }
      return {};
    });

    renderComponent('KAN');

    const trashTab = await screen.findByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByText('Old Issue from fallback with summary')).toBeDefined();
    expect(screen.getByText('Old Issue from fallback with title')).toBeDefined();
    expect(screen.getAllByText('KAN-OLD-3').length).toBe(2);
    expect(callCount).toBe(1);
  });

  it('covers all remaining corner cases, null fallbacks, and boundary conditions', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: '',
          description_markdown: null,
          modules_enabled: false,
          auto_archive_days: null,
          capabilities: ['ADMIN'],
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return [
          {
            id: 'st-no-color',
            name: 'No Color State',
            group: 'started',
            sort_order: 1,
            color_hex: null,
          },
          {
            id: 'st-second',
            name: 'Second State',
            group: 'started',
            sort_order: 2,
            color_hex: '#123456',
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
        return [
          {
            id: 'prio-no-color',
            slug: 'prio-nc',
            label: 'No Color Prio',
            emoji: null,
            color_hex: null,
            sort_order: 1,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return [
          {
            id: 'lbl-no-color',
            name: 'No Color Label',
            color_hex: null,
            exclusive_group: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [
          {
            principal_id: 'user-no-id',
            role: 'MEMBER',
            display_name: 'No Id Member',
            handle: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/trash-items') && m === 'GET') {
        return { items: [] };
      }
      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          { id: 'u-1', display_name: 'User One', principal_type: 'USER', handle: 'u1' },
          { id: 'g-1', display_name: 'Group One', principal_type: 'GROUP', handle: null },
          { id: 'a-1', display_name: 'Agent One', principal_type: 'AGENT', handle: 'a1' },
        ];
      }
      if (url.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        return {
          confirmation_token: 'token-empty-counts',
          confirm_phrase: 'CONFIRM DELETE',
          mode: 'trash',
          blast_summary: {},
        };
      }
      return {};
    });

    renderComponent('KAN');

    // 1. Header fallback when project name is empty
    expect(await screen.findByText('Project Settings: KAN')).toBeDefined();

    // 2. States Tab: group change, boundary reorder, no-color fallback
    const statesTab = screen.getByTestId('tab-states');
    fireEvent.click(statesTab);

    // Group select onChange
    const groupSelect = screen.getByTestId('state-group-select');
    fireEvent.change(groupSelect, { target: { value: 'completed' } });

    // Empty stateName submit guard
    const stateForm = screen.getByTestId('state-name-input').closest('form');
    if (stateForm) fireEvent.submit(stateForm);
    fireEvent.click(screen.getByTestId('create-state-btn'));

    // Boundary reorder: move top item up (targetIdx < 0)
    const upBtn = screen.getByTestId('state-up-st-no-color');
    fireEvent.click(upBtn);

    // Boundary reorder: move bottom item down (targetIdx >= states.length)
    const downBtn = screen.getByTestId('state-down-st-second');
    fireEvent.click(downBtn);

    // Verify color fallback rendered
    expect(screen.getByText('No Color State')).toBeDefined();

    // 3. Priorities Tab: empty submit guard, no-color fallback
    const prioritiesTab = screen.getByTestId('tab-priorities');
    fireEvent.click(prioritiesTab);

    const prioForm = screen.getByTestId('priority-slug-input').closest('form');
    if (prioForm) fireEvent.submit(prioForm);
    fireEvent.click(screen.getByTestId('create-priority-btn'));
    expect(screen.getByText('No Color Prio')).toBeDefined();

    // 4. Labels Tab: empty submit guard, no-color fallback
    const labelsTab = screen.getByTestId('tab-labels');
    fireEvent.click(labelsTab);

    const labelForm = screen.getByTestId('label-name-input').closest('form');
    if (labelForm) fireEvent.submit(labelForm);
    fireEvent.click(screen.getByTestId('create-label-btn'));
    expect(screen.getByText('No Color Label')).toBeDefined();

    // 5. Members Tab: empty submit guard, member with no id
    const membersTab = screen.getByTestId('tab-members');
    fireEvent.click(membersTab);

    const memberForm = screen.getByTestId('member-principal-id-input').closest('form');
    if (memberForm) fireEvent.submit(memberForm);
    expect(screen.getByText('No Id Member')).toBeDefined();

    // Principal picker onMouseDown preventDefault
    const memberInput = screen.getByTestId('member-principal-id-input');
    fireEvent.focus(memberInput);
    fireEvent.change(memberInput, { target: { value: 'Group' } });

    const dropdown = await screen.findByTestId('principal-picker-dropdown');
    fireEvent.mouseDown(dropdown);

    // 6. Trash Tab: empty trash state
    const trashTab = screen.getByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByTestId('trash-empty-state')).toBeDefined();
    expect(screen.getByText('No trashed items in this project.')).toBeDefined();

    // 7. Danger Tab: blast summary with undefined counts (0 fallback)
    const dangerTab = screen.getByTestId('tab-danger');
    fireEvent.click(dangerTab);

    const reqBtn = await screen.findByTestId('request-delete-btn');
    fireEvent.click(reqBtn);

    expect(await screen.findByText('Work Items: 0')).toBeDefined();
    expect(screen.getByText('Docs / Pages: 0')).toBeDefined();
    expect(screen.getByText('Stickies: 0')).toBeDefined();
  });

  it('covers fallback error messages when error object has no message property', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return [
          { id: 'st-e1', name: 'State E1', group: 'started', sort_order: 1, color_hex: '#111' },
          { id: 'st-e2', name: 'State E2', group: 'started', sort_order: 2, color_hex: '#222' },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
        return [{ id: 'prio-e1', slug: 'p-e1', label: 'Prio E1', color_hex: '#111', sort_order: 1 }];
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return [{ id: 'lbl-e1', name: 'lbl-e1', color_hex: '#111' }];
      }
      if (url.includes('/api/v1/projects/KAN/trash-items') && m === 'GET') {
        return {
          items: [
            {
              id: 'tr-e1',
              key: 'KAN-E1',
              kind: 'issue',
              deleted_at: '2026-11-10T12:00:00Z',
              purge_after: '2026-12-10T12:00:00Z',
              remaining_days: 3,
            },
          ],
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'PATCH') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'DELETE') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/priorities/') && m === 'DELETE') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'POST') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('/api/v1/projects/KAN/labels/') && m === 'DELETE') {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      if (url.includes('restore')) {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {};
      }
      return {};
    });

    renderComponent('KAN');

    // 1. States Tab fallback errors
    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    fireEvent.change(screen.getByTestId('state-name-input'), { target: { value: 'State X' } });
    fireEvent.click(screen.getByTestId('create-state-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to create workflow state.')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('state-down-st-e1'));
    await waitFor(() => {
      expect(screen.getByText('Failed to reorder state.')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-state-btn-st-e1'));
    const confirmStateE1Btn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmStateE1Btn);
    await waitFor(() => {
      expect(screen.getByText('Failed to delete workflow state.')).toBeDefined();
    });

    // 2. Priorities Tab fallback errors
    const prioritiesTab = screen.getByTestId('tab-priorities');
    fireEvent.click(prioritiesTab);

    fireEvent.change(screen.getByTestId('priority-slug-input'), { target: { value: 'px' } });
    fireEvent.change(screen.getByTestId('priority-label-input'), { target: { value: 'Prio X' } });
    fireEvent.click(screen.getByTestId('create-priority-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to create priority.')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-priority-btn-prio-e1'));
    await waitFor(() => {
      expect(screen.getByText('Failed to delete priority.')).toBeDefined();
    });

    // 3. Labels Tab fallback errors
    const labelsTab = screen.getByTestId('tab-labels');
    fireEvent.click(labelsTab);

    fireEvent.change(screen.getByTestId('label-name-input'), { target: { value: 'label-x' } });
    fireEvent.click(screen.getByTestId('create-label-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to create label.')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-label-btn-lbl-e1'));
    const confirmLabelE1Btn = await screen.findByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmLabelE1Btn);
    await waitFor(() => {
      expect(screen.getByText('Failed to delete label.')).toBeDefined();
    });

    // 4. Trash restore fallback error
    const trashTab = screen.getByTestId('tab-trash');
    fireEvent.click(trashTab);

    fireEvent.click(screen.getByTestId('restore-btn-tr-e1'));
    await waitFor(() => {
      expect(screen.getByText('Failed to restore item.')).toBeDefined();
    });
  });

  it('handles principal list response wrapped in items object and filters autocomplete', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      if (url.includes('/api/v1/admin/principals')) {
        return {
          items: [
            {
              id: 'p-wrap-1',
              type: 'USER',
              display_name: 'Wrapped Principal',
              handle: 'wrapped',
            },
          ],
        };
      }
      if (url.includes('/api/v1/workspaces') && (url.includes('/ai-providers') || url.includes('/agent-definitions'))) {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          modules_enabled: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');
    expect(await screen.findByTestId('project-settings-page')).toBeDefined();

    const membersTab = screen.getByTestId('tab-members');
    fireEvent.click(membersTab);

    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Wrapped' } });

    expect(await screen.findByTestId('principal-picker-dropdown')).toBeDefined();
    expect(screen.getByText('Wrapped Principal')).toBeDefined();

    fireEvent.click(screen.getByTestId('principal-option-p-wrap-1'));
    expect(screen.getByDisplayValue('Wrapped Principal')).toBeDefined();
  });

  it('KAN-14: guards nullable display_name, trash kind, and member role without throwing in .toLowerCase()', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      if (url.includes('/api/v1/admin/principals')) {
        return [
          {
            id: 'p-null-name',
            principal_type: 'USER',
            display_name: null,
            handle: 'nullname',
          },
        ];
      }
      if (url.includes('/api/v1/workspaces') && (url.includes('/ai-providers') || url.includes('/agent-definitions'))) {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [
          {
            id: 'm-null-role',
            principal_id: 'p-null-role',
            role: null,
            display_name: 'Member Null Role',
            handle: 'nullrole',
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/trash-items') || url.includes('/api/v1/projects/KAN/trash')) {
        return {
          items: [
            {
              id: 'tr-null-kind',
              key: 'KAN-99',
              kind: null,
              title: 'Item with null kind',
              deleted_at: new Date().toISOString(),
              purge_after: new Date().toISOString(),
              remaining_days: 14,
            },
          ],
        };
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          modules_enabled: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');
    expect(await screen.findByTestId('project-settings-page')).toBeDefined();

    // 1. Members tab: check member with null role and search with null display_name
    const membersTab = screen.getByTestId('tab-members');
    fireEvent.click(membersTab);

    // Verify member with null role rendered badge without crash
    expect(await screen.findByText('Member Null Role')).toBeDefined();
    const roleBadge = screen.getByTestId('member-role-badge');
    expect(roleBadge.className).toContain('kb-role-badge kb-role-');

    // Autocomplete search filtering principal with null display_name
    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'nullname' } });
    expect(await screen.findByTestId('principal-picker-dropdown')).toBeDefined();
    expect(screen.getByTestId('principal-option-p-null-name')).toBeDefined();

    // 2. Trash tab: filter trashed item with null kind
    const trashTab = screen.getByTestId('tab-trash');
    fireEvent.click(trashTab);

    expect(await screen.findByTestId('trash-section')).toBeDefined();
    // Default filter is 'all'
    expect(screen.getByText('Item with null kind')).toBeDefined();

    // Switch filter to 'issue' - null kind does not crash and gets filtered out
    const filterBtn = screen.getByTestId('trash-filter-issue');
    fireEvent.click(filterBtn);
    expect(screen.queryByText('Item with null kind')).toBeNull();
  });

  it('KAN-14: normalizes principal handles to single @ prefix, preventing @@ in picker and table', async () => {
    expect(formatPrincipalHandle('@alice')).toBe('@alice');
    expect(formatPrincipalHandle('alice')).toBe('@alice');
    expect(formatPrincipalHandle('@@@alice')).toBe('@alice');
    expect(formatPrincipalHandle(null, '@alice')).toBe('@alice');
    expect(formatPrincipalHandle(null, null)).toBeNull();
    expect(formatPrincipalHandle('', '')).toBeNull();

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/admin/principals') && m === 'GET') {
        return [
          {
            id: 'user-alice',
            display_name: 'Alice QA',
            handle: '@alice',
            principal: '@alice',
            principal_type: 'USER',
          },
          {
            id: 'user-bob',
            display_name: 'Bob Plain',
            handle: 'bob',
            principal_type: 'USER',
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [
          {
            id: 'mem-1',
            principal_id: 'user-alice',
            role: 'MEMBER',
            display_name: 'Alice QA',
            handle: '@alice',
            principal: '@alice',
          },
        ];
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      return {};
    });

    const { container } = renderComponent('KAN');

    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    // Verify Members table renders single @alice and 0 @@ strings
    expect(await screen.findByText('(@alice)')).toBeDefined();
    expect(screen.queryByText(/@@/)).toBeNull();
    expect(container.textContent).not.toContain('@@');

    // Open principal picker dropdown and verify autocomplete option renders @alice with 0 @@ strings
    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Alice' } });

    expect(await screen.findByTestId('principal-picker-dropdown')).toBeDefined();
    const aliceOption = screen.getByTestId('principal-option-user-alice');
    expect(aliceOption).toBeDefined();
    expect(within(aliceOption).getByText('@alice')).toBeDefined();
    expect(container.textContent).not.toContain('@@');
    expect((container.innerHTML.match(/@@/g) ?? []).length).toBe(0);
  });

  it('invalidates project query and projects query on saving general settings (KAN-11 Problem 1)', async () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const setQueryDataSpy = vi.spyOn(queryClient, 'setQueryData');

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          modules_enabled: true,
        };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'PATCH'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform Updated',
          is_project_admin: true,
          modules_enabled: false,
        };
      }
      return {};
    });

    queryClient.setQueryData(['project', 'KAN'], {
      id: 'p-1',
      identifier: 'KAN',
      name: 'Old Cache',
      modules_enabled: true,
    });

    renderComponent('KAN');

    // Toggle modules_enabled
    const modulesToggle = await screen.findByTestId('project-modules-checkbox');
    fireEvent.click(modulesToggle);

    // Click Save General Settings
    const saveBtn = screen.getByTestId('save-general-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Project settings saved successfully.')).toBeDefined();
    });

    expect(setQueryDataSpy).toHaveBeenCalledWith(['project', 'KAN'], expect.any(Function));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['projects'] });
  });

  it('disables permanent purge button with inline guidance caption when project is active and enables when trashed (KAN-11 Problem 2)', async () => {
    let mockProjectIsTrashed = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Active Project',
          is_project_admin: true,
          deleted_at: mockProjectIsTrashed ? '2026-11-20T00:00:00Z' : null,
          trashed_at: null,
          status: mockProjectIsTrashed ? 'trashed' : 'active',
        };
      }
      if (url.includes('/api/v1/auth/me') && m === 'GET') {
        return { is_server_admin: true };
      }
      if (url.includes('/api/v1/admin/destructive:request') && m === 'POST') {
        return {
          confirmation_token: 'purge-token-active-guard',
          confirm_phrase: 'PURGE KAN FOREVER',
          mode: 'permanent_purge',
          blast_summary: 'All records will be destroyed',
        };
      }
      return {};
    });

    const { unmount } = renderComponent('KAN');

    const dangerTab = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab);

    // 1. When project is active (non-trashed):
    const purgeBtn = await screen.findByTestId('request-purge-btn');
    expect(purgeBtn.hasAttribute('disabled')).toBe(true);
    expect(purgeBtn.getAttribute('aria-disabled')).toBe('true');

    const hint = await screen.findByTestId('purge-disabled-hint');
    expect(hint.textContent).toContain('Stage 1 (Move Project to Trash) must be completed before permanent purge.');

    // Attempting to invoke handleRequestDelete when not trashed sets dangerError
    purgeBtn.removeAttribute('disabled');
    fireEvent.click(purgeBtn);
    expect(
      await screen.findByText('Stage 1 (Move Project to Trash) must be completed before permanent purge.'),
    ).toBeDefined();
    expect(screen.queryByTestId('danger-confirm-card')).toBeNull();

    unmount();

    // 2. When project is soft-trashed:
    mockProjectIsTrashed = true;
    renderComponent('KAN');

    const dangerTab2 = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab2);

    const purgeBtn2 = await screen.findByTestId('request-purge-btn');
    expect(purgeBtn2.hasAttribute('disabled')).toBe(false);
    expect(purgeBtn2.getAttribute('aria-disabled')).toBe('false');
    expect(screen.queryByTestId('purge-disabled-hint')).toBeNull();

    // Clicking enabled button proceeds to Stage 2 confirmation
    fireEvent.click(purgeBtn2);
    expect(
      await screen.findByText('Stage 2: Confirm PERMANENT Project Purge (IRREVERSIBLE)'),
    ).toBeDefined();
  });

  it('covers handleSaveGeneral catch block without message property', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'PATCH'
      ) {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw {}; // No message property
      }
      return {};
    });

    renderComponent('KAN');

    const saveBtn = await screen.findByTestId('save-general-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to update project settings.')).toBeDefined();
    });
  });

  it('supports inline row edit for workflow states and labels (KAN-29 Problem 1)', async () => {
    const stateList: Record<string, unknown>[] = [
      {
        id: 'st-edit-1',
        name: 'Initial State',
        group: 'unstarted',
        sort_order: 1,
        color_hex: '#64748b',
        is_default: false,
        wip_soft_limit: 2,
        wip_hard_limit: 5,
      },
    ];

    const labelList: Record<string, unknown>[] = [
      {
        id: 'lbl-edit-1',
        name: 'initial-label',
        color_hex: '#2563eb',
        exclusive_group: null,
      },
    ];

    interface PatchedState {
      name?: string;
      group?: string;
      wip_soft_limit?: number | null;
      wip_hard_limit?: number | null;
    }
    interface PatchedLabel {
      name?: string;
      color_hex?: string;
      exclusive_group?: string | null;
    }
    let patchedStateBody: PatchedState | null = null;
    let patchedLabelBody: PatchedLabel | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return labelList;
      }
      if (url.includes('/api/v1/projects/KAN/states/st-edit-1') && m === 'PATCH') {
        patchedStateBody = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return {
          ...stateList[0],
          ...patchedStateBody,
        };
      }
      if (url.includes('/api/v1/projects/KAN/labels/lbl-edit-1') && m === 'PATCH') {
        patchedLabelBody = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return {
          ...labelList[0],
          ...patchedLabelBody,
        };
      }
      return {};
    });

    renderComponent('KAN');

    // 1. Test Workflow State Inline Edit
    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    expect(await screen.findByTestId('state-pill-st-edit-1')).toBeDefined();
    const editStateBtn = screen.getByTestId('edit-state-btn-st-edit-1');
    fireEvent.click(editStateBtn);

    // Editing inputs appear
    const nameInput = screen.getByTestId('state-edit-name-st-edit-1');
    fireEvent.change(nameInput, { target: { value: 'Updated State' } });

    // Change group select
    const groupSelect = screen.getByTestId('state-edit-group-st-edit-1');
    fireEvent.change(groupSelect, { target: { value: 'completed' } });

    // Test soft > hard validation
    const softInput = screen.getByTestId('state-edit-wip-soft-st-edit-1');
    const hardInput = screen.getByTestId('state-edit-wip-hard-st-edit-1');
    fireEvent.change(softInput, { target: { value: '10' } });
    fireEvent.change(hardInput, { target: { value: '5' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));

    expect(await screen.findByText('Soft WIP limit cannot exceed Hard WIP limit')).toBeDefined();

    // Test empty name guard (does not save)
    fireEvent.change(nameInput, { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));

    // Fix name and soft limit and save
    fireEvent.change(nameInput, { target: { value: 'Updated State' } });
    fireEvent.change(softInput, { target: { value: '4' } });
    fireEvent.change(hardInput, { target: { value: '8' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Workflow state "Updated State" updated.')).toBeDefined();
    });
    expect(patchedStateBody).toBeDefined();
    const statePayload = patchedStateBody as unknown as PatchedState;
    expect(statePayload.name).toBe('Updated State');
    expect(statePayload.group).toBe('completed');
    expect(statePayload.wip_soft_limit).toBe(4);
    expect(statePayload.wip_hard_limit).toBe(8);

    // Test Cancel on state edit
    fireEvent.click(screen.getByTestId('edit-state-btn-st-edit-1'));
    expect(screen.getByTestId('cancel-state-btn-st-edit-1')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-state-btn-st-edit-1'));
    expect(screen.queryByTestId('cancel-state-btn-st-edit-1')).toBeNull();

    // 2. Test Label Inline Edit
    const labelsTab = screen.getByTestId('tab-labels');
    fireEvent.click(labelsTab);

    expect(await screen.findByTestId('label-pill-lbl-edit-1')).toBeDefined();
    const editLabelBtn = screen.getByTestId('edit-label-btn-lbl-edit-1');
    fireEvent.click(editLabelBtn);

    const labelNameInput = screen.getByTestId('label-edit-name-lbl-edit-1');
    fireEvent.change(labelNameInput, { target: { value: 'updated-label' } });
    const labelGroupInput = screen.getByTestId('label-edit-group-lbl-edit-1');
    fireEvent.change(labelGroupInput, { target: { value: 'prio' } });
    const labelColorInput = screen.getByTestId('label-edit-color-lbl-edit-1-input');
    fireEvent.change(labelColorInput, { target: { value: '#dc2626' } });

    // Test empty name guard on label
    fireEvent.change(labelNameInput, { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('save-label-btn-lbl-edit-1'));

    // Fix name and save
    fireEvent.change(labelNameInput, { target: { value: 'updated-label' } });
    fireEvent.click(screen.getByTestId('save-label-btn-lbl-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Label "updated-label" updated.')).toBeDefined();
    });
    expect(patchedLabelBody).toBeDefined();
    const labelPayload = patchedLabelBody as unknown as PatchedLabel;
    expect(labelPayload.name).toBe('updated-label');
    expect(labelPayload.color_hex).toBe('#dc2626');
    expect(labelPayload.exclusive_group).toBe('prio');

    // Test Cancel on label edit
    fireEvent.click(screen.getByTestId('edit-label-btn-lbl-edit-1'));
    expect(screen.getByTestId('cancel-label-btn-lbl-edit-1')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-label-btn-lbl-edit-1'));
    expect(screen.queryByTestId('cancel-label-btn-lbl-edit-1')).toBeNull();
  });

  it('performs pre-delete reverse audit and passes migration options (KAN-29 Problems 2, 3, 4)', async () => {
    let capturedDeleteUrl = '';

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET' && !url.includes('audit-impact')) {
        return [
          {
            id: 'st-audit-1',
            name: 'State To Delete',
            group: 'started',
            sort_order: 1,
            color_hex: '#ea580c',
            is_default: false,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/states/st-audit-1/audit-impact') && m === 'GET') {
        return {
          state_id: 'st-audit-1',
          state_name: 'State To Delete',
          issues_count: 3,
          sample_issue_keys: ['KAN-10', 'KAN-11'],
          workflow_hooks: [
            {
              id: 'hook-100',
              name: 'Deploy Hook',
              from_state_id: 'st-audit-1',
              to_state_id: 'st-audit-2',
              is_enabled: true,
            },
          ],
          pending_executions_count: 0,
          historical_executions_count: 4,
          saved_views: [{ id: 'v-10', name: 'Roadmap View' }],
          is_default: false,
          blocking_reasons: [],
          valid_replacement_states: [
            { id: 'st-audit-2', name: 'Fallback State', group: 'started', color_hex: '#2563eb' },
          ],
        };
      }
      if (url.includes('/api/v1/projects/KAN/states/st-audit-1') && m === 'DELETE') {
        capturedDeleteUrl = url;
        return { status: 'deleted' };
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET' && !url.includes('audit-impact')) {
        return [
          {
            id: 'lbl-audit-1',
            name: 'label-to-delete',
            color_hex: '#10b981',
            exclusive_group: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN/labels/lbl-audit-1/audit-impact') && m === 'GET') {
        return {
          label_id: 'lbl-audit-1',
          label_name: 'label-to-delete',
          issues_count: 2,
          sample_issue_keys: ['KAN-20'],
          saved_views: [],
          blocking_reasons: [],
          valid_replacement_labels: [
            { id: 'lbl-audit-2', name: 'fallback-label', color_hex: '#64748b' },
          ],
        };
      }
      if (url.includes('/api/v1/projects/KAN/labels/lbl-audit-1') && m === 'DELETE') {
        capturedDeleteUrl = url;
        return { status: 'deleted' };
      }
      return {};
    });

    renderComponent('KAN');

    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    const deleteBtn = await screen.findByTestId('delete-state-btn-st-audit-1');
    fireEvent.click(deleteBtn);

    // Verify modal opens with blast radius and controls
    expect(await screen.findByTestId('delete-audit-modal')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByTestId('audit-issues-count').textContent).toBe('3');
    });

    expect(screen.getByTestId('audit-sample-keys').textContent).toContain('KAN-10');
    expect(screen.getByTestId('audit-hooks-count').textContent).toBe('1');
    expect(screen.getByTestId('audit-historical-count').textContent).toBe('4');

    // Confirm deletion
    const confirmBtn = screen.getByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText('Workflow state deleted.')).toBeDefined();
    });

    expect(capturedDeleteUrl).toContain('replacement_state_id=st-audit-2');
    expect(capturedDeleteUrl).toContain('migrate_hooks=true');

    // Now test Label deletion with audit modal
    const labelsTab = screen.getByTestId('tab-labels');
    fireEvent.click(labelsTab);

    const deleteLabelBtn = await screen.findByTestId('delete-label-btn-lbl-audit-1');
    fireEvent.click(deleteLabelBtn);

    expect(await screen.findByTestId('delete-audit-modal')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByTestId('audit-issues-count').textContent).toBe('2');
    });

    const confirmLabelBtn = screen.getByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmLabelBtn);

    await waitFor(() => {
      expect(screen.getByText('Label deleted.')).toBeDefined();
    });

    expect(capturedDeleteUrl).toContain('replacement_label_id=lbl-audit-2');
  });

  it('supports inline row editing of workflow states: start, edit fields, cancel, save, error, soft>hard validation', async () => {
    let stateList: Record<string, unknown>[] = [
      {
        id: 'st-edit-1',
        name: 'Backlog Item',
        group: 'backlog',
        sort_order: 1,
        color_hex: '',
        is_default: true,
        wip_soft_limit: null,
        wip_hard_limit: null,
      },
      {
        id: 'st-edit-2',
        name: 'Second Item',
        group: 'started',
        sort_order: 2,
        color_hex: '#2563eb',
        is_default: false,
        wip_soft_limit: 5,
        wip_hard_limit: 10,
      },
    ];

    let failPatch = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'PATCH') {
        if (failPatch) {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw {};
        }
        const body = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        stateList = stateList.map((s) => (s.id === 'st-edit-1' ? { ...s, ...body } : s));
        return { ...stateList[0], ...body };
      }
      return {};
    });

    renderComponent('KAN');

    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    expect(await screen.findByText('Backlog Item')).toBeDefined();

    // Start inline edit
    const editBtn = screen.getByTestId('edit-state-btn-st-edit-1');
    fireEvent.click(editBtn);

    const softInput = screen.getByTestId('state-edit-wip-soft-st-edit-1');
    const hardInput = screen.getByTestId('state-edit-wip-hard-st-edit-1');
    const saveBtn = screen.getByTestId('save-state-btn-st-edit-1');
    const cancelBtn = screen.getByTestId('cancel-state-btn-st-edit-1');

    // Soft > Hard validation
    fireEvent.change(softInput, { target: { value: '25' } });
    fireEvent.change(hardInput, { target: { value: '10' } });
    fireEvent.click(saveBtn);
    expect(await screen.findByText('Soft WIP limit cannot exceed Hard WIP limit')).toBeDefined();

    // Cancel edit
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('state-edit-name-st-edit-1')).toBeNull();

    // Re-enter edit, test empty name guard
    fireEvent.click(screen.getByTestId('edit-state-btn-st-edit-1'));
    const nameInput2 = screen.getByTestId('state-edit-name-st-edit-1');
    fireEvent.change(nameInput2, { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    // Should not save
    expect(screen.getByTestId('state-edit-name-st-edit-1')).toBeDefined();

    // Test error branch
    failPatch = true;
    fireEvent.change(nameInput2, { target: { value: 'Valid Name' } });
    fireEvent.change(screen.getByTestId('state-edit-wip-soft-st-edit-1'), { target: { value: '' } });
    fireEvent.change(screen.getByTestId('state-edit-wip-hard-st-edit-1'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(await screen.findByText('Failed to update workflow state.')).toBeDefined();

    // Test successful patch
    failPatch = false;
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    await waitFor(() => {
      expect(screen.getByText('Workflow state "Valid Name" updated.')).toBeDefined();
    });
  });

  it('supports inline row editing of labels: start, edit fields, cancel, save, error handling, and empty guard', async () => {
    let labelList: Record<string, unknown>[] = [
      {
        id: 'lbl-edit-1',
        name: 'backend',
        color_hex: '',
        exclusive_group: null,
      },
      {
        id: 'lbl-edit-2',
        name: 'frontend',
        color_hex: '#3b82f6',
        exclusive_group: 'layer',
      },
    ];

    let failPatch = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
        return labelList;
      }
      if (url.includes('/api/v1/projects/KAN/labels/') && m === 'PATCH') {
        if (failPatch) {
          // eslint-disable-next-line @typescript-eslint/only-throw-error
          throw {};
        }
        const body = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        labelList = labelList.map((l) => (l.id === 'lbl-edit-1' ? { ...l, ...body } : l));
        return { ...labelList[0], ...body };
      }
      return {};
    });

    renderComponent('KAN');

    const labelsTab = await screen.findByTestId('tab-labels');
    fireEvent.click(labelsTab);

    expect(await screen.findByText('backend')).toBeDefined();

    // Start inline edit
    const editBtn = screen.getByTestId('edit-label-btn-lbl-edit-1');
    fireEvent.click(editBtn);

    const nameInput = screen.getByTestId('label-edit-name-lbl-edit-1');
    const groupInput = screen.getByTestId('label-edit-group-lbl-edit-1');
    const cancelBtn = screen.getByTestId('cancel-label-btn-lbl-edit-1');

    // Cancel edit
    fireEvent.change(nameInput, { target: { value: 'cancelled-name' } });
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('label-edit-name-lbl-edit-1')).toBeNull();

    // Re-enter edit, test empty name guard
    fireEvent.click(screen.getByTestId('edit-label-btn-lbl-edit-1'));
    const nameInput2 = screen.getByTestId('label-edit-name-lbl-edit-1');
    fireEvent.change(nameInput2, { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('save-label-btn-lbl-edit-1'));
    // Should not save
    expect(screen.getByTestId('label-edit-name-lbl-edit-1')).toBeDefined();

    // Test error branch
    failPatch = true;
    fireEvent.change(nameInput2, { target: { value: 'backend-v2' } });
    fireEvent.change(groupInput, { target: { value: 'core' } });
    fireEvent.click(screen.getByTestId('save-label-btn-lbl-edit-1'));
    expect(await screen.findByText('Failed to update label.')).toBeDefined();

    // Test successful patch
    failPatch = false;
    fireEvent.click(screen.getByTestId('save-label-btn-lbl-edit-1'));
    await waitFor(() => {
      expect(screen.getByText('Label "backend-v2" updated.')).toBeDefined();
    });
  });

  it('covers permanent purge guard when project is not trashed and delete modal error handling', async () => {
    const stateList: Record<string, unknown>[] = [
      {
        id: 'st-err-1',
        name: 'Ready',
        group: 'unstarted',
        sort_order: 1,
        color_hex: '#64748b',
        is_default: false,
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          status: 'active',
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/audit-impact') && m === 'GET') {
        return {
          state_id: 'st-err-1',
          project_id: 'p-1',
          issues_count: 0,
          sample_issue_keys: [],
          workflow_hooks: [],
          pending_executions_count: 0,
          saved_views: [],
          is_default: false,
          blocking_reasons: [],
          valid_replacement_states: [],
        };
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'DELETE') {
        throw new Error('Deletion rejected by server invariant');
      }
      return {};
    });

    renderComponent('KAN');

    // Test danger zone permanent purge guard when project is not trashed
    const dangerTab = await screen.findByTestId('tab-danger');
    fireEvent.click(dangerTab);

    const purgeBtn = await screen.findByTestId('request-purge-btn');
    (purgeBtn as HTMLButtonElement).disabled = false;
    purgeBtn.removeAttribute('disabled');
    fireEvent.click(purgeBtn);

    expect(
      await screen.findByText(
        'Stage 1 (Move Project to Trash) must be completed before permanent purge.',
      ),
    ).toBeDefined();

    // Now test state delete modal error handling
    const statesTab = screen.getByTestId('tab-states');
    fireEvent.click(statesTab);

    const deleteBtn = await screen.findByTestId('delete-state-btn-st-err-1');
    fireEvent.click(deleteBtn);

    expect(await screen.findByTestId('delete-audit-modal')).toBeDefined();
    const confirmBtn = screen.getByTestId('audit-confirm-delete-btn');
    fireEvent.click(confirmBtn);

    expect(await screen.findByText('Deletion rejected by server invariant')).toBeDefined();
  });

  it('supports full workflow state editing UI, live StateBadge preview, and cache invalidation (KAN-43 Problem 1)', async () => {
    const stateList: Record<string, unknown>[] = [
      {
        id: 'st-edit-1',
        name: 'Backlog',
        group: 'backlog',
        sort_order: 1,
        color_hex: '#64748b',
        is_default: false,
        wip_soft_limit: null,
        wip_hard_limit: null,
      },
      {
        id: 'st-edit-2',
        name: 'In Progress',
        group: 'started',
        sort_order: 2,
        color_hex: '#4f46e5',
        is_default: true,
        wip_soft_limit: 3,
        wip_hard_limit: 5,
      },
    ];

    let patchedStateBody: Record<string, unknown> | null = null;
    let mockErrorType: 'TAKEN' | 'LAST_GROUP' | 'DEFAULT_REQ' | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          status: 'active',
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/api/v1/projects/KAN/states/st-edit-1') && m === 'PATCH') {
        if (mockErrorType === 'TAKEN') {
          throw new ApiProblem(409, { code: 'STATE_NAME_TAKEN', title: 'State Name Taken' });
        }
        if (mockErrorType === 'LAST_GROUP') {
          throw new ApiProblem(409, {
            code: 'LAST_STATE_IN_GROUP',
            title: 'Cannot Move Last State Out Of Group',
          });
        }
        if (mockErrorType === 'DEFAULT_REQ') {
          throw new ApiProblem(409, {
            code: 'DEFAULT_STATE_REQUIRED',
            title: 'Default State Required',
          });
        }
        patchedStateBody = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return {
          ...stateList[0],
          ...patchedStateBody,
        };
      }
      return {};
    });

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    renderComponent('KAN');

    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    // Click edit state button
    const editBtn = await screen.findByTestId('edit-state-btn-st-edit-1');
    fireEvent.click(editBtn);

    // Live preview badge should be present
    expect(await screen.findByTestId('state-edit-preview-st-edit-1')).toBeDefined();

    // Verify empty name and Preview fallback
    const nameInput = screen.getByTestId('state-edit-name-st-edit-1');
    fireEvent.change(nameInput, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(await screen.findByText('Workflow state name is required.')).toBeDefined();

    // Verify name length validation: > 64 chars
    const longName = 'A'.repeat(65);
    fireEvent.change(nameInput, { target: { value: longName } });
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(await screen.findByText('Workflow state name cannot exceed 64 characters.')).toBeDefined();

    // Set valid fields
    fireEvent.change(nameInput, { target: { value: 'Purple Backlog' } });
    const groupSelect = screen.getByTestId('state-edit-group-st-edit-1');
    fireEvent.change(groupSelect, { target: { value: 'unstarted' } });
    const colorInput = screen.getByTestId('state-edit-color-st-edit-1-input');
    fireEvent.change(colorInput, { target: { value: '#7c3aed' } });
    const defaultCheck = screen.getByTestId('state-edit-default-st-edit-1');
    fireEvent.click(defaultCheck);
    const softWip = screen.getByTestId('state-edit-wip-soft-st-edit-1');
    fireEvent.change(softWip, { target: { value: '5' } });
    const hardWip = screen.getByTestId('state-edit-wip-hard-st-edit-1');
    fireEvent.change(hardWip, { target: { value: '10' } });

    // Test STATE_NAME_TAKEN error mapping
    mockErrorType = 'TAKEN';
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(
      await screen.findByText('A workflow state with this name already exists in this project.'),
    ).toBeDefined();

    // Test LAST_STATE_IN_GROUP error mapping
    mockErrorType = 'LAST_GROUP';
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(
      await screen.findByText('Cannot move the last remaining state out of this lifecycle group.'),
    ).toBeDefined();

    // Test DEFAULT_STATE_REQUIRED error mapping
    mockErrorType = 'DEFAULT_REQ';
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));
    expect(
      await screen.findByText(
        'A default state is required. Designate another default state before removing this one.',
      ),
    ).toBeDefined();

    // Successful save without is_default: true to exercise return s
    mockErrorType = null;
    fireEvent.click(screen.getByTestId('state-edit-default-st-edit-1'));
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Workflow state "Purple Backlog" updated.')).toBeDefined();
    });

    // Reopen and save with updated sort_order and is_default: true
    fireEvent.click(screen.getByTestId('edit-state-btn-st-edit-1'));
    const orderInput = screen.getByTestId('state-edit-order-st-edit-1');
    expect(orderInput).toBeDefined();
    fireEvent.change(orderInput, { target: { value: '7' } });
    fireEvent.click(screen.getByTestId('state-edit-default-st-edit-1'));
    fireEvent.click(screen.getByTestId('save-state-btn-st-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Workflow state "Purple Backlog" updated.')).toBeDefined();
    });

    expect(patchedStateBody).toEqual({
      name: 'Purple Backlog',
      group: 'unstarted',
      color_hex: '#7c3aed',
      sort_order: 7,
      wip_soft_limit: 5,
      wip_hard_limit: 10,
      is_default: true,
    });

    // Invalidation assertions
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project-states', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['issues', 'KAN', {}] });
  });

  it('persists both swapped sort orders on state reorder and invalidates caches (KAN-43 Problem 1)', async () => {
    const stateList: Record<string, unknown>[] = [
      {
        id: 'st-re-1',
        name: 'State One',
        group: 'backlog',
        sort_order: 10,
        color_hex: '#64748b',
        is_default: false,
      },
      {
        id: 'st-re-2',
        name: 'State Two',
        group: 'started',
        sort_order: 10,
        color_hex: '#4f46e5',
        is_default: true,
      },
      {
        id: 'st-re-3',
        name: 'State Three',
        group: 'completed',
        sort_order: 10,
        color_hex: '#10b981',
        is_default: false,
      },
    ];

    const patchCalls: { url: string; body: Record<string, unknown> }[] = [];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          status: 'active',
        };
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
        return stateList;
      }
      if (url.includes('/api/v1/projects/KAN/states') && m === 'POST') {
        throw new ApiProblem(409, { code: 'STATE_NAME_TAKEN', title: 'State Name Taken' });
      }
      if (url.includes('/api/v1/projects/KAN/states/') && m === 'PATCH') {
        const bodyStr = typeof (options as { body?: unknown }).body === 'string'
          ? (options as { body: string }).body
          : '{}';
        const body = JSON.parse(bodyStr) as Record<string, unknown>;
        patchCalls.push({ url, body });
        return { id: 'ok' };
      }
      return {};
    });

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    renderComponent('KAN');

    const statesTab = await screen.findByTestId('tab-states');
    fireEvent.click(statesTab);

    // Test STATE_NAME_TAKEN in handleCreateState
    const nameInput = screen.getByTestId('state-name-input');
    fireEvent.change(nameInput, { target: { value: 'State One' } });
    fireEvent.click(screen.getByTestId('create-state-btn'));
    expect(
      await screen.findByText('A workflow state with this name already exists in this project.'),
    ).toBeDefined();

    // Reorder st-re-2 down first (current is st-re-2: 10, target is st-re-3: 10 -> down sets target.sort_order + 1 = 11)
    const downBtn = await screen.findByTestId('state-down-st-re-2');
    fireEvent.click(downBtn);

    await waitFor(() => {
      expect(patchCalls.length).toBe(2);
    });

    // Reorder st-re-3 up (target is st-re-1: 10 -> up sets target.sort_order - 1 = 9)
    const upBtn = await screen.findByTestId('state-up-st-re-3');
    fireEvent.click(upBtn);

    await waitFor(() => {
      expect(patchCalls.length).toBe(4);
    });

    // Check that PATCH calls occurred with updated sort orders
    const call2 = patchCalls.find((c) => c.url.includes('st-re-2'));
    expect(call2?.body).toEqual({ sort_order: 11 });

    // Cache invalidation checks
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project-states', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['issues', 'KAN', {}] });
  });

  it('supports inline priority editing, saving, and cache invalidation (KAN-43 Problem 1)', async () => {
    const priorityList: Record<string, unknown>[] = [
      {
        id: 'prio-edit-1',
        slug: 'urgent',
        label: 'Urgent',
        emoji: '🔥',
        color_hex: '#dc2626',
        sort_order: 1,
        is_default: false,
      },
      {
        id: 'prio-edit-2',
        slug: 'normal',
        label: 'Normal',
        emoji: '⚡',
        color_hex: '#2563eb',
        sort_order: 2,
        is_default: true,
      },
    ];

    let patchedPriorityBody: Record<string, unknown> | null = null;
    let failPriorityPatch = false;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/auth/me')) {
        return { is_server_admin: true };
      }
      if (
        (url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) &&
        m === 'GET'
      ) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
          status: 'active',
        };
      }
      if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
        return priorityList;
      }
      if (url.includes('/api/v1/projects/KAN/priorities/prio-edit-1') && m === 'PATCH') {
        if (failPriorityPatch) {
          throw new Error('Failed to update priority.');
        }
        const bodyStr = typeof (options as { body?: unknown }).body === 'string'
          ? (options as { body: string }).body
          : '{}';
        patchedPriorityBody = JSON.parse(bodyStr) as Record<string, unknown>;
        return {
          ...priorityList[0],
          ...patchedPriorityBody,
        };
      }
      return {};
    });

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    renderComponent('KAN');

    const prioritiesTab = await screen.findByTestId('tab-priorities');
    fireEvent.click(prioritiesTab);

    // Click edit priority
    const editBtn = await screen.findByTestId('edit-priority-btn-prio-edit-1');
    fireEvent.click(editBtn);

    // Inputs appear
    const slugInput = screen.getByTestId('priority-edit-slug-prio-edit-1');
    const labelInput = screen.getByTestId('priority-edit-label-prio-edit-1');
    const emojiInput = screen.getByTestId('priority-edit-emoji-prio-edit-1');
    const colorInput = screen.getByTestId('priority-edit-color-prio-edit-1-input');
    const sortInput = screen.getByTestId('priority-edit-sort-prio-edit-1');
    const defaultCheck = screen.getByTestId('priority-edit-default-prio-edit-1');

    fireEvent.change(slugInput, { target: { value: 'critical' } });
    fireEvent.change(labelInput, { target: { value: 'Critical Issue' } });
    fireEvent.change(emojiInput, { target: { value: '🚨' } });
    fireEvent.change(colorInput, { target: { value: '#7c3aed' } });
    fireEvent.change(sortInput, { target: { value: '0' } });
    fireEvent.click(defaultCheck);

    // Test cancel
    const cancelBtn = screen.getByTestId('cancel-priority-btn-prio-edit-1');
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('save-priority-btn-prio-edit-1')).toBeNull();

    // Reopen and test empty guard
    fireEvent.click(screen.getByTestId('edit-priority-btn-prio-edit-1'));
    fireEvent.change(screen.getByTestId('priority-edit-label-prio-edit-1'), { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('save-priority-btn-prio-edit-1'));

    // Test error handling
    fireEvent.change(screen.getByTestId('priority-edit-label-prio-edit-1'), { target: { value: 'Critical Issue' } });
    fireEvent.change(screen.getByTestId('priority-edit-slug-prio-edit-1'), { target: { value: 'critical' } });
    failPriorityPatch = true;
    fireEvent.click(screen.getByTestId('save-priority-btn-prio-edit-1'));
    expect(await screen.findByText('Failed to update priority.')).toBeDefined();

    // Fix and save without is_default: true to exercise return p
    failPriorityPatch = false;
    fireEvent.click(screen.getByTestId('save-priority-btn-prio-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Priority "Critical Issue" updated.')).toBeDefined();
    });

    // Now edit and save with is_default: true to exercise default de-duplication
    fireEvent.click(screen.getByTestId('edit-priority-btn-prio-edit-1'));
    fireEvent.click(screen.getByTestId('priority-edit-default-prio-edit-1'));
    fireEvent.click(screen.getByTestId('save-priority-btn-prio-edit-1'));

    await waitFor(() => {
      expect(screen.getByText('Priority "Critical Issue" updated.')).toBeDefined();
    });

    expect(patchedPriorityBody).toEqual({
      slug: 'critical',
      label: 'Critical Issue',
      emoji: '🔥',
      color_hex: '#dc2626',
      sort_order: 1,
      is_default: true,
    });

    // Invalidation checks
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project-states', 'KAN'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['issues', 'KAN', {}] });
  });

  it('renders and toggles skip_loaded_sequence_numbers checkbox in general settings tab', async () => {
    let patchedBody: Record<string, unknown> | null = null;

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url: string = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return [];
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'GET') {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Platform Core',
          description_markdown: 'Core project',
          modules_enabled: false,
          skip_loaded_sequence_numbers: false,
          is_project_admin: true,
        };
      }
      if (url.includes('/api/v1/projects/KAN') && m === 'PATCH') {
        patchedBody = JSON.parse(String((options as { body?: string }).body)) as Record<string, unknown>;
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Platform Core',
          description_markdown: 'Core project',
          modules_enabled: false,
          skip_loaded_sequence_numbers: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    const skipCheckbox = await screen.findByTestId<HTMLInputElement>(
      'project-skip-loaded-seq-checkbox',
    );
    expect(skipCheckbox).toBeDefined();
    expect(skipCheckbox.checked).toBe(false);

    // Toggle skip_loaded_sequence_numbers
    fireEvent.click(skipCheckbox);
    expect(skipCheckbox.checked).toBe(true);

    const saveBtn = screen.getByTestId('save-general-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText('Project settings saved successfully.')).toBeDefined();
    });

    expect(patchedBody).toEqual({
      name: 'Platform Core',
      description_markdown: 'Core project',
      modules_enabled: false,
      skip_loaded_sequence_numbers: true,
      auto_archive_days: null,
    });
  });

  describe('Progressive Disclosure (KB-ADVANCED-DISCLOSURE-03 / KAN-369)', () => {
    it('Positive case 1: ProjectSettingsPage renders basic settings and collapses WIP limits and numbering policies', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        const url: string = path;
        if (
          url.includes('/api/v1/projects/KAN') &&
          !url.includes('/states') &&
          !url.includes('/labels') &&
          !url.includes('/modules') &&
          !url.includes('/members')
        ) {
          return {
            id: 'p-1',
            identifier: 'KAN',
            name: 'Platform Core',
            description_markdown: 'Core project description',
            modules_enabled: true,
            skip_loaded_sequence_numbers: true,
            auto_archive_days: 14,
            is_project_admin: true,
          };
        }
        if (url.includes('/states')) {
          return [
            {
              id: 'st-1',
              name: 'Backlog',
              group: 'backlog',
              color_hex: '#6b7280',
              sort_order: 0,
              is_default: true,
              wip_soft_limit: 5,
              wip_hard_limit: 10,
            },
            {
              id: 'st-2',
              name: 'Done',
              group: 'completed',
              color_hex: '#10b981',
              sort_order: 1,
              is_default: false,
              wip_soft_limit: null,
              wip_hard_limit: null,
            },
          ];
        }
        if (url.includes('/labels')) {
          return [
            { id: 'lbl-1', name: 'Frontend', color_hex: '#3b82f6', exclusive_group: 'layer' },
          ];
        }
        if (url.includes('/modules')) {
          return [{ id: 'm-1', name: 'Auth' }];
        }
        return [];
      });

      renderComponent('KAN');

      // 1. General Settings tab renders primary fields by default
      expect(await screen.findByTestId('project-name-input')).toBeDefined();
      expect(screen.getByTestId('project-desc-input')).toBeDefined();
      expect(screen.getByTestId('project-modules-checkbox')).toBeDefined();

      // 2. Advanced Project Options section is collapsed by default
      const generalAdvSection = screen.getByTestId<HTMLDetailsElement>('project-general-advanced-section');
      expect(generalAdvSection.open).toBe(false);
      expect(screen.getByTestId('project-general-advanced-section-toggle').getAttribute('aria-expanded')).toBe('false');

      // Toggle open
      fireEvent.click(screen.getByTestId('project-general-advanced-section-toggle'));
      expect(generalAdvSection.open).toBe(true);
      expect(screen.getByTestId('project-skip-loaded-seq-checkbox')).toBeDefined();
      expect(screen.getByTestId('project-auto-archive-input')).toBeDefined();

      // 3. Workflow States tab renders primary fields and collapses WIP limits and sort order
      fireEvent.click(screen.getByTestId('tab-states'));
      expect(await screen.findByTestId('state-name-input')).toBeDefined();
      expect(screen.getByTestId('state-group-select')).toBeDefined();
      expect(screen.getByTestId('state-color-input')).toBeDefined();
      expect(screen.getByTestId('state-default-checkbox')).toBeDefined();
      expect(screen.getByTestId('create-state-btn')).toBeDefined();

      // Active WIP limits override badge is displayed
      expect(screen.getByTestId('wip-overrides-active-badge').textContent).toContain('1 custom WIP limit active');

      // Advanced state limits section is collapsed by default
      const stateAdvSection = screen.getByTestId<HTMLDetailsElement>('state-advanced-section');
      expect(stateAdvSection.open).toBe(false);
      expect(screen.getByTestId('state-advanced-section-toggle').getAttribute('aria-expanded')).toBe('false');

      // Toggle open
      fireEvent.click(screen.getByTestId('state-advanced-section-toggle'));
      expect(stateAdvSection.open).toBe(true);
      expect(screen.getByTestId('state-sort-order-input')).toBeDefined();
      expect(screen.getByTestId('state-wip-soft-input')).toBeDefined();
      expect(screen.getByTestId('state-wip-hard-input')).toBeDefined();

      // 4. Labels tab collapses exclusive group
      fireEvent.click(screen.getByTestId('tab-labels'));
      expect(await screen.findByTestId('label-name-input')).toBeDefined();
      expect(screen.getByTestId('label-color-input')).toBeDefined();
      const labelAdvSection = screen.getByTestId<HTMLDetailsElement>('label-advanced-section');
      expect(labelAdvSection.open).toBe(false);

      // Toggle open
      fireEvent.click(screen.getByTestId('label-advanced-section-toggle'));
      expect(labelAdvSection.open).toBe(true);
      expect(screen.getByTestId('label-exclusive-group-input')).toBeDefined();

      // 5. Roles tab navigation
      fireEvent.click(screen.getByTestId('tab-roles'));
      expect(await screen.findByTestId('project-roles-section')).toBeDefined();
    });

    it('renders normalized help hints and default values on project settings (KAN-394)', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        const url: string = path;
        const m = method.toUpperCase();

        if ((url === '/api/v1/projects/KAN' || url.endsWith('/api/v1/projects/KAN')) && m === 'GET') {
          return {
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            is_project_admin: true,
            modules_enabled: true,
            skip_loaded_sequence_numbers: true,
          };
        }
        if (url.includes('/api/v1/projects/KAN/modules')) return [];
        if (url.includes('/api/v1/projects/KAN/states')) return [];
        if (url.includes('/api/v1/projects/KAN/labels')) return [];
        return {};
      });

      renderComponent('KAN');

      const nameHint = await screen.findByTestId('proj-name-help');
      fireEvent.focus(nameHint);
      expect(screen.getByTestId('proj-name-help-popover').textContent).toContain('Default:');
      expect(screen.getByTestId('proj-name-help-popover').textContent).toContain('My Project');
      fireEvent.blur(nameHint);

      const modulesHint = screen.getByTestId('proj-modules-help');
      fireEvent.focus(modulesHint);
      expect(screen.getByTestId('proj-modules-help-popover').textContent).toContain('Enabled (true)');
      fireEvent.blur(modulesHint);

      // Expand advanced section
      fireEvent.click(screen.getByTestId('project-general-advanced-section-toggle'));

      const skipHint = screen.getByTestId('proj-skip-seq-help');
      fireEvent.focus(skipHint);
      expect(screen.getByTestId('proj-skip-seq-help-popover').textContent).toContain('Inherits Workspace Default (Enabled)');
      fireEvent.blur(skipHint);

      const autoArchiveHint = screen.getByTestId('proj-auto-archive-help');
      fireEvent.focus(autoArchiveHint);
      expect(screen.getByTestId('proj-auto-archive-help-popover').textContent).toContain('Disabled (blank; e.g. 30 days)');
    });

    it('silently ignores Aal2StepUpCancelledError during save with zero role="alert" banners (KAN-404)', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        const url: string = path;
        const m = method.toUpperCase();
        if (url.includes('/api/v1/auth/me')) {
          return { id: 'admin-1', is_server_admin: true, is_workspace_admin: true };
        }
        if (url.includes('/api/v1/projects/KAN') && m === 'PATCH') {
          throw new clientModule.Aal2StepUpCancelledError();
        }
        if (url.includes('/api/v1/projects/KAN/cycles')) return [];
        if (url.includes('/api/v1/projects/KAN/modules')) return [];
        if (url.includes('/api/v1/projects/KAN/states')) return [];
        if (url.includes('/api/v1/projects/KAN/labels')) return [];
        if (url.includes('/api/v1/projects/KAN/members')) return [];
        if (url.includes('/api/v1/projects/KAN')) {
          return { id: 'p1', identifier: 'KAN', name: 'My Project', is_project_admin: true };
        }
        return {};
      });

      renderComponent('KAN');
      const saveBtn = await screen.findByTestId('save-general-btn');
      fireEvent.click(saveBtn);
      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
      });
    });
  });
});
