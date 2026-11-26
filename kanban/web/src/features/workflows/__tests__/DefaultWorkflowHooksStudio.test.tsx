// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { DefaultWorkflowHooksStudio } from '../DefaultWorkflowHooksStudio';
import { HookPipelineRow } from '../HookPipelineRow';
import { WorkflowStudioPage } from '../WorkflowStudioPage';
import * as api from '../api';

const MOCK_SYSTEM_TEMPLATE: api.DefaultWorkflowHook = {
  id: 'template-sys-1',
  scope_kind: 'system',
  workspace_id: null,
  name: 'default-reality-checker',
  from_state_name: null,
  to_state_name: 'Done',
  hook_kind: 'agent_interceptor',
  sort_rank: 100,
  is_enabled: true,
  wasm_module_sha256: null,
  agent_definition_id: null,
  agent_slug: 'reality-checker',
  allowed_mutable_fields: ['labels'],
  failure_policy: 'fail_closed',
  timeout_ms: 60000,
  max_rework_attempts: 3,
  created_by: null,
  created_at: '2026-11-26T12:00:00Z',
  updated_at: '2026-11-26T12:00:00Z',
};

const MOCK_WORKSPACE_TEMPLATE: api.DefaultWorkflowHook = {
  id: 'template-ws-1',
  scope_kind: 'workspace',
  workspace_id: 'ws-1234',
  name: 'ws-custom-gate',
  from_state_name: 'In Review',
  to_state_name: 'Done',
  hook_kind: 'wasm_validator',
  sort_rank: 50,
  is_enabled: false,
  wasm_module_sha256: null,
  agent_definition_id: null,
  agent_slug: null,
  allowed_mutable_fields: [],
  failure_policy: 'fail_open_warn',
  timeout_ms: null,
  max_rework_attempts: 3,
  created_by: null,
  created_at: '2026-11-26T12:00:00Z',
  updated_at: '2026-11-26T12:00:00Z',
};

describe('DefaultWorkflowHooksStudio & Inherited Hook Controls (KAN-438)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    vi.restoreAllMocks();
  });

  function renderStudio(props: {
    scopeKind?: 'system' | 'workspace';
    workspaceId?: string;
    showSubnav?: boolean;
  } = {}) {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DefaultWorkflowHooksStudio
            scopeKind={props.scopeKind ?? 'system'}
            workspaceId={props.workspaceId}
            showSubnav={props.showSubnav ?? false}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('renders system default hooks list with template details and badges', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([MOCK_SYSTEM_TEMPLATE]);

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('default-workflow-hooks-studio')).toBeDefined();
    });

    expect(screen.getByText(/System-Wide Default Workflow Hooks/i)).toBeDefined();
    expect(screen.getByTestId('template-row-template-sys-1')).toBeDefined();
    expect(screen.getByTestId('template-name-template-sys-1').textContent).toBe('default-reality-checker');
    expect(screen.getByTestId('template-transition-template-sys-1').textContent).toContain('* Any State');
    expect(screen.getByTestId('template-transition-template-sys-1').textContent).toContain('Done');
    expect(screen.getByText('@reality-checker')).toBeDefined();
    expect(screen.getByText('Fail-Closed')).toBeDefined();
  });

  it('renders empty notice when no templates are configured', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([]);

    renderStudio({ scopeKind: 'workspace', workspaceId: 'ws-1234' });

    await waitFor(() => {
      expect(screen.getByTestId('empty-templates-notice')).toBeDefined();
    });
    expect(screen.getByText(/No Default Workflow Hook Templates/i)).toBeDefined();
  });

  it('opens create modal, enforces client-side timeout validation, and creates template', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([]);
    const createSpy = vi.spyOn(api, 'createDefaultWorkflowHook').mockResolvedValue({
      ...MOCK_SYSTEM_TEMPLATE,
      id: 'template-sys-new',
      name: 'new-gate',
    });

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('create-default-hook-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-default-hook-btn'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();

    // Fill form fields
    fireEvent.change(screen.getByTestId('template-name-input'), { target: { value: 'new-gate' } });
    fireEvent.change(screen.getByTestId('template-to-state-input'), { target: { value: 'Done' } });

    // Test invalid timeout < 1000
    fireEvent.change(screen.getByTestId('template-timeout-input'), { target: { value: '500' } });
    const dialogForm = screen.getByRole('dialog').querySelector('form');
    expect(dialogForm).not.toBeNull();
    if (dialogForm) {
      fireEvent.submit(dialogForm);
    }

    await waitFor(() => {
      expect(screen.getByText(/Timeout must be between 1000 and 600000 ms/i)).toBeDefined();
    });
    expect(createSpy).not.toHaveBeenCalled();

    // Correct timeout to valid value
    fireEvent.change(screen.getByTestId('template-timeout-input'), { target: { value: '120000' } });
    if (dialogForm) {
      fireEvent.submit(dialogForm);
    }

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'new-gate',
          scope_kind: 'system',
          to_state_name: 'Done',
          timeout_ms: 120000,
        }),
        undefined,
      );
    });
  });

  it('opens edit dialog, modifies template, and updates successfully', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([MOCK_WORKSPACE_TEMPLATE]);
    const updateSpy = vi.spyOn(api, 'updateDefaultWorkflowHook').mockResolvedValue({
      ...MOCK_WORKSPACE_TEMPLATE,
      name: 'ws-custom-gate-updated',
    });

    renderStudio({ scopeKind: 'workspace', workspaceId: 'ws-1234' });

    await waitFor(() => {
      expect(screen.getByTestId('template-edit-btn-template-ws-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('template-edit-btn-template-ws-1'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();

    fireEvent.change(screen.getByTestId('template-name-input'), {
      target: { value: 'ws-custom-gate-updated' },
    });
    fireEvent.click(screen.getByTestId('save-template-btn'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'template-ws-1',
        expect.objectContaining({
          name: 'ws-custom-gate-updated',
        }),
        'ws-1234',
      );
    });
  });

  it('toggles template status on checkbox click', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([MOCK_SYSTEM_TEMPLATE]);
    const updateSpy = vi.spyOn(api, 'updateDefaultWorkflowHook').mockResolvedValue({
      ...MOCK_SYSTEM_TEMPLATE,
      is_enabled: false,
    });

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('template-toggle-template-sys-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('template-toggle-template-sys-1'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'template-sys-1',
        { is_enabled: false },
        undefined,
      );
    });
  });

  it('deletes template after user confirmation', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([MOCK_SYSTEM_TEMPLATE]);
    const deleteSpy = vi.spyOn(api, 'deleteDefaultWorkflowHook').mockResolvedValue();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('template-delete-btn-template-sys-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('template-delete-btn-template-sys-1'));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('template-sys-1', undefined);
    });
  });

  it('HookPipelineRow displays Inherited from Default badge and allows Detach', () => {
    const onDetachMock = vi.fn();
    const onEditMock = vi.fn();
    const onToggleMock = vi.fn();

    const inheritedHook: api.WorkflowHook = {
      id: 'hook-inherited-42',
      name: 'reality-checker-gate',
      from_state: 'In Review',
      to_state: 'Done',
      hook_kind: 'agent_interceptor',
      sort_rank: '100',
      failure_policy: 'fail_closed',
      manifest_sha256: 'abc123456789',
      is_enabled: true,
      inherited_from_template_id: 'template-sys-1',
      inherited_from_scope: 'system',
    };

    render(
      <HookPipelineRow
        hook={inheritedHook}
        index={0}
        total={1}
        projectKey="PROJ"
        onDetach={onDetachMock}
        onEdit={onEditMock}
        onToggle={onToggleMock}
      />,
    );

    // Verify badge
    const badge = screen.getByTestId('hook-inherited-badge-hook-inherited-42');
    expect(badge).toBeDefined();
    expect(badge.textContent).toBe('Inherited from Default');

    // Verify Detach button is enabled and works (project-level removal)
    const detachBtn = screen.getByRole('button', { name: /Detach reality-checker-gate/i });
    expect(detachBtn).toBeDefined();
    fireEvent.click(detachBtn);
    expect(onDetachMock).toHaveBeenCalledWith('hook-inherited-42');

    // Verify Edit button is enabled
    const editBtn = screen.getByRole('button', { name: /Edit reality-checker-gate/i });
    expect(editBtn).toBeDefined();
    fireEvent.click(editBtn);
    expect(onEditMock).toHaveBeenCalledWith(inheritedHook);
  });

  it('WorkflowStudioPage provides Sync Default Hooks button that invokes API', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue([]);
    const syncSpy = vi.spyOn(api, 'syncDefaultWorkflowHooks').mockResolvedValue([
      {
        id: 'hook-synced-1',
        name: 'synced-template',
        from_state: null,
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '100',
        failure_policy: 'fail_closed',
        manifest_sha256: 'def456',
        is_enabled: true,
        inherited_from_template_id: 'template-sys-1',
      },
    ]);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/NEWP/settings/workflows']}>
          <WorkflowStudioPage projectKeyOverride="NEWP" isAdmin={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('sync-default-hooks-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('sync-default-hooks-btn'));

    await waitFor(() => {
      expect(syncSpy).toHaveBeenCalledWith('NEWP');
      expect(screen.getByTestId('sync-defaults-status')).toBeDefined();
      expect(screen.getByTestId('sync-defaults-status').textContent).toContain('Successfully synced 1 default hook template(s).');
    });
  });

  it('handles edit round-trip for agent_async and wasm_sync preserving exact hook kinds', async () => {
    const wasmTemplate: api.DefaultWorkflowHook = {
      ...MOCK_WORKSPACE_TEMPLATE,
      id: 'template-ws-wasm',
      hook_kind: 'wasm_sync',
    };
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([wasmTemplate]);
    const updateSpy = vi.spyOn(api, 'updateDefaultWorkflowHook').mockResolvedValue({
      ...wasmTemplate,
      timeout_ms: 30000,
    });

    renderStudio({ scopeKind: 'workspace', workspaceId: 'ws-1234' });

    await waitFor(() => {
      expect(screen.getByTestId('template-edit-btn-template-ws-wasm')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('template-edit-btn-template-ws-wasm'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();

    const kindSelect = screen.getByTestId<HTMLSelectElement>('template-hook-kind-select');
    expect(kindSelect.value).toBe('wasm_validator');

    fireEvent.change(screen.getByTestId('template-timeout-input'), {
      target: { value: '30000' },
    });
    fireEvent.click(screen.getByTestId('save-template-btn'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'template-ws-wasm',
        expect.objectContaining({
          hook_kind: 'wasm_validator',
          timeout_ms: 30000,
        }),
        'ws-1234',
      );
    });
  });

  it('renders danger alert with role=alert when syncDefaultWorkflowHooks fails', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue([]);
    vi.spyOn(api, 'syncDefaultWorkflowHooks').mockRejectedValue(new Error('Network sync error'));

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/NEWP/settings/workflows']}>
          <WorkflowStudioPage projectKeyOverride="NEWP" isAdmin={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('sync-default-hooks-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('sync-default-hooks-btn'));

    await waitFor(() => {
      const alert = screen.getByTestId('sync-defaults-status');
      expect(alert).toBeDefined();
      expect(alert.getAttribute('role')).toBe('alert');
      expect(alert.className).toContain('workflow-alert-danger');
      expect(alert.textContent).toContain('Network sync error');
    });
  });
});
