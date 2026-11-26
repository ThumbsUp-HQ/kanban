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
import * as apiClient from '../../../api/client';

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
          hook_kind: 'wasm_sync',
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

  it('switches hook kind to wasm_validator and submits wasm_module_sha256', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([]);
    const createSpy = vi.spyOn(api, 'createDefaultWorkflowHook').mockResolvedValue({
      ...MOCK_SYSTEM_TEMPLATE,
      id: 'template-wasm-1',
      hook_kind: 'wasm_validator',
      wasm_module_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
      agent_slug: null,
    });

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('create-default-hook-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-default-hook-btn'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();

    // Fill common fields
    fireEvent.change(screen.getByTestId('template-name-input'), { target: { value: 'custom-wasm-guard' } });
    fireEvent.change(screen.getByTestId('template-to-state-input'), { target: { value: 'Done' } });

    // Switch hook kind to wasm_validator
    fireEvent.change(screen.getByTestId('template-hook-kind-select'), {
      target: { value: 'wasm_validator' },
    });

    // Verify wasm input is shown and agent input is hidden
    expect(screen.getByTestId('template-wasm-sha-input')).toBeDefined();
    expect(screen.queryByTestId('template-agent-slug-input')).toBeNull();

    // Fill wasm sha
    fireEvent.change(screen.getByTestId('template-wasm-sha-input'), {
      target: { value: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968' },
    });

    fireEvent.click(screen.getByTestId('save-template-btn'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'custom-wasm-guard',
          hook_kind: 'wasm_sync',
          wasm_module_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
          agent: null,
          agent_slug: null,
        }),
        undefined,
      );
    });
  });

  it('switches hook kind to builtin and submits selected builtin sha', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([]);
    const createSpy = vi.spyOn(api, 'createDefaultWorkflowHook').mockResolvedValue({
      ...MOCK_SYSTEM_TEMPLATE,
      id: 'template-builtin-1',
      hook_kind: 'builtin',
      wasm_module_sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
      agent_slug: null,
    });

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      expect(screen.getByTestId('create-default-hook-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-default-hook-btn'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();

    // Fill common fields
    fireEvent.change(screen.getByTestId('template-name-input'), { target: { value: 'builtin-sec-guard' } });
    fireEvent.change(screen.getByTestId('template-to-state-input'), { target: { value: 'Done' } });

    // Switch hook kind to builtin
    fireEvent.change(screen.getByTestId('template-hook-kind-select'), {
      target: { value: 'builtin' },
    });

    // Verify builtin select is shown and agent input is hidden
    const builtinSelect = screen.getByTestId<HTMLSelectElement>('template-builtin-select');
    expect(builtinSelect).toBeDefined();
    expect(screen.queryByTestId('template-agent-slug-input')).toBeNull();

    // Change to security-invariant-validator
    fireEvent.change(builtinSelect, {
      target: { value: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874' },
    });

    fireEvent.click(screen.getByTestId('save-template-btn'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'builtin-sec-guard',
          hook_kind: 'builtin',
          wasm_module_sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
          agent: null,
          agent_slug: null,
        }),
        undefined,
      );
    });
  });

  it('renders error alert banner and suppresses empty notice when fetchDefaultWorkflowHooks fails', async () => {
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockRejectedValue(
      new Error('HTTP 403: Administrative role required'),
    );

    renderStudio({ scopeKind: 'system' });

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain('HTTP 403: Administrative role required');
    });

    // Ensure misleading empty notice is NOT shown when error occurred
    expect(screen.queryByTestId('empty-templates-notice')).toBeNull();
  });

  it('covers edit flows across agent_async, wasm_sync, and builtin templates plus Escape and error branches', async () => {
    const wasmTemplate: api.DefaultWorkflowHook = {
      ...MOCK_WORKSPACE_TEMPLATE,
      id: 'tpl-wasm-edit',
      hook_kind: 'wasm_sync',
      wasm_module_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
      max_rework_attempts: 0,
    };
    const builtinTemplate: api.DefaultWorkflowHook = {
      ...MOCK_SYSTEM_TEMPLATE,
      id: 'tpl-builtin-edit',
      hook_kind: 'builtin',
      agent_slug: null,
      wasm_module_sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
    };
    vi.spyOn(api, 'fetchDefaultWorkflowHooks').mockResolvedValue([
      { ...MOCK_SYSTEM_TEMPLATE, hook_kind: 'agent_async' },
      wasmTemplate,
      builtinTemplate,
    ]);
    const updateSpy = vi.spyOn(api, 'updateDefaultWorkflowHook').mockResolvedValue(MOCK_SYSTEM_TEMPLATE);
    const deleteSpy = vi.spyOn(api, 'deleteDefaultWorkflowHook').mockRejectedValue(new Error('Delete blocked'));

    renderStudio({ scopeKind: 'workspace', workspaceId: 'ws-1234', showSubnav: true });

    await waitFor(() => {
      expect(screen.getByTestId('template-edit-btn-template-sys-1')).toBeDefined();
    });

    // 1. Edit agent_async template & close via Escape
    fireEvent.click(screen.getByTestId('template-edit-btn-template-sys-1'));
    expect(screen.getByTestId('template-dialog')).toBeDefined();
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(screen.getByTestId('template-dialog')).toBeDefined();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('template-dialog')).toBeNull();

    const submitDialogForm = () => {
      const formEl = screen.getByTestId('template-dialog').querySelector('form');
      if (!formEl) throw new Error('Expected template dialog form');
      fireEvent.submit(formEl);
    };

    // 2. Edit agent_async template & test required validation errors + successful save
    fireEvent.click(screen.getByTestId('template-edit-btn-template-sys-1'));
    fireEvent.change(screen.getByTestId('template-name-input'), { target: { value: '   ' } });
    submitDialogForm();
    expect(screen.getByRole('alert').textContent).toContain('Template name is required');

    fireEvent.change(screen.getByTestId('template-name-input'), { target: { value: 'valid-name' } });
    fireEvent.change(screen.getByTestId('template-to-state-input'), { target: { value: '   ' } });
    submitDialogForm();
    expect(screen.getByRole('alert').textContent).toContain('Target state is required');

    fireEvent.change(screen.getByTestId('template-to-state-input'), { target: { value: 'Done' } });
    fireEvent.change(screen.getByTestId('template-agent-slug-input'), { target: { value: '@@@' } });
    submitDialogForm();
    expect(screen.getByRole('alert').textContent).toContain('Agent slug is required');

    fireEvent.change(screen.getByTestId('template-agent-slug-input'), { target: { value: '@qa-bot' } });
    fireEvent.change(screen.getByTestId('template-from-state-input'), { target: { value: '*' } });
    fireEvent.change(screen.getByTestId('template-timeout-input'), { target: { value: '' } });
    fireEvent.change(screen.getByTestId('template-policy-select'), { target: { value: 'fail_open_warn' } });
    fireEvent.change(screen.getByTestId('template-sort-rank-input'), { target: { value: '40' } });
    fireEvent.change(screen.getByTestId('template-rework-input'), { target: { value: '5' } });
    submitDialogForm();

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'template-sys-1',
        expect.objectContaining({
          hook_kind: 'agent_async',
          agent_slug: 'qa-bot',
          from_state_name: null,
          timeout_ms: null,
          failure_policy: 'fail_open_warn',
        }),
        'ws-1234',
      );
    });

    // 3. Edit wasm_sync template (empty wasm validation + save)
    fireEvent.click(screen.getByTestId('template-edit-btn-tpl-wasm-edit'));
    fireEvent.change(screen.getByTestId('template-wasm-sha-input'), { target: { value: '   ' } });
    submitDialogForm();
    expect(screen.getByRole('alert').textContent).toContain('Wasm module SHA-256 is required');

    fireEvent.change(screen.getByTestId('template-wasm-sha-input'), {
      target: { value: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968' },
    });
    submitDialogForm();
    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'tpl-wasm-edit',
        expect.objectContaining({ hook_kind: 'wasm_sync' }),
        'ws-1234',
      );
    });

    // 4. Edit builtin template & save
    fireEvent.click(screen.getByTestId('template-edit-btn-tpl-builtin-edit'));
    submitDialogForm();
    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'tpl-builtin-edit',
        expect.objectContaining({ hook_kind: 'builtin' }),
        'ws-1234',
      );
    });

    // 5. Toggle error & Delete cancel + error
    updateSpy.mockRejectedValueOnce(new Error('Toggle rejected'));
    fireEvent.click(screen.getByTestId('template-toggle-template-sys-1'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Toggle rejected');
    });

    vi.spyOn(window, 'confirm').mockReturnValueOnce(false);
    fireEvent.click(screen.getByTestId('template-delete-btn-template-sys-1'));
    expect(deleteSpy).not.toHaveBeenCalled();

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    fireEvent.click(screen.getByTestId('template-delete-btn-template-sys-1'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Delete blocked');
    });
  });

  it('covers default workflow hooks API client functions across system and workspace scopes', async () => {
    const fetchSpy = vi.spyOn(apiClient, 'apiFetch');

    // 1. fetchDefaultWorkflowHooks: system, workspace, unfiltered, and non-array fallback
    fetchSpy.mockResolvedValueOnce([MOCK_SYSTEM_TEMPLATE, MOCK_WORKSPACE_TEMPLATE]);
    const sysOnly = await api.fetchDefaultWorkflowHooks('system');
    expect(sysOnly).toHaveLength(1);
    expect(fetchSpy).toHaveBeenLastCalledWith('GET', '/api/v1/admin/default-workflow-hooks?scope_kind=system');

    fetchSpy.mockResolvedValueOnce([MOCK_WORKSPACE_TEMPLATE]);
    const wsOnly = await api.fetchDefaultWorkflowHooks('workspace', 'ws-1234');
    expect(wsOnly).toHaveLength(1);
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'GET',
      '/api/v1/workspaces/ws-1234/default-workflow-hooks?include_system=false',
    );

    fetchSpy.mockResolvedValueOnce([MOCK_SYSTEM_TEMPLATE, MOCK_WORKSPACE_TEMPLATE]);
    const allWs = await api.fetchDefaultWorkflowHooks(undefined, 'ws-1234');
    expect(allWs).toHaveLength(2);
    expect(fetchSpy).toHaveBeenLastCalledWith('GET', '/api/v1/workspaces/ws-1234/default-workflow-hooks');

    fetchSpy.mockResolvedValueOnce(null);
    expect(await api.fetchDefaultWorkflowHooks()).toEqual([]);

    // 2. createDefaultWorkflowHook: system vs workspace
    fetchSpy.mockResolvedValueOnce(MOCK_SYSTEM_TEMPLATE);
    await api.createDefaultWorkflowHook({
      name: 'sys-tpl',
      scope_kind: 'system',
      to_state_name: 'Done',
      hook_kind: 'agent_async',
    });
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/admin/default-workflow-hooks',
      expect.any(Object),
    );

    fetchSpy.mockResolvedValueOnce(MOCK_WORKSPACE_TEMPLATE);
    await api.createDefaultWorkflowHook(
      {
        name: 'ws-tpl',
        scope_kind: 'workspace',
        workspace_id: 'ws-1234',
        to_state_name: 'Done',
        hook_kind: 'wasm_sync',
      },
      'ws-1234',
    );
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/workspaces/ws-1234/default-workflow-hooks',
      expect.any(Object),
    );

    // 3. updateDefaultWorkflowHook & deleteDefaultWorkflowHook: system vs workspace
    fetchSpy.mockResolvedValueOnce(MOCK_SYSTEM_TEMPLATE);
    await api.updateDefaultWorkflowHook('tpl-1', { is_enabled: false });
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'PATCH',
      '/api/v1/admin/default-workflow-hooks/tpl-1',
      expect.any(Object),
    );

    fetchSpy.mockResolvedValueOnce(MOCK_WORKSPACE_TEMPLATE);
    await api.updateDefaultWorkflowHook('tpl-2', { is_enabled: true }, 'ws-1234');
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'PATCH',
      '/api/v1/workspaces/ws-1234/default-workflow-hooks/tpl-2',
      expect.any(Object),
    );

    fetchSpy.mockResolvedValueOnce(undefined);
    await api.deleteDefaultWorkflowHook('tpl-1');
    expect(fetchSpy).toHaveBeenLastCalledWith('DELETE', '/api/v1/admin/default-workflow-hooks/tpl-1');

    fetchSpy.mockResolvedValueOnce(undefined);
    await api.deleteDefaultWorkflowHook('tpl-2', 'ws-1234');
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'DELETE',
      '/api/v1/workspaces/ws-1234/default-workflow-hooks/tpl-2',
    );

    // 4. syncDefaultWorkflowHooks: array vs non-array
    fetchSpy.mockResolvedValueOnce([{ id: 'h1' }]);
    expect(await api.syncDefaultWorkflowHooks('KAN')).toHaveLength(1);
    fetchSpy.mockResolvedValueOnce(null);
    expect(await api.syncDefaultWorkflowHooks('KAN')).toEqual([]);
  });
});
